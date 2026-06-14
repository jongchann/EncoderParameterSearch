import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from backend.models.enums import SessionStatus, TrialStatus
from backend.server import make_handler
from backend.services.trial_service import TrialService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class TrialResultUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = TrialService(self.store, ArtifactStore(self.root))
        self._create_assigned_trial()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_upload_result_stores_artifact_on_disk(self) -> None:
        response = self.service.upload_result(
            "sess_001",
            "trial_001",
            self._result_metadata(),
            b"encoded-bytes",
        )

        artifact_path = Path(response["artifact_path"])

        self.assertTrue(artifact_path.exists())
        self.assertEqual(artifact_path.read_bytes(), b"encoded-bytes")
        self.assertEqual(
            artifact_path,
            self.root / "sess_001" / "trials" / "trial_001" / "output.h264",
        )

    def test_requested_applied_and_unknown_params_are_stored_separately(self) -> None:
        self.service.upload_result(
            "sess_001",
            "trial_001",
            self._result_metadata(),
            b"encoded-bytes",
        )

        trial = self.store.get("trials", "trial_id", "trial_001")
        requested_path = self.root / "sess_001" / "trials" / "trial_001" / "requested_params.json"
        applied_path = self.root / "sess_001" / "trials" / "trial_001" / "applied_params.json"

        self.assertEqual(trial["status"], TrialStatus.UPLOADED.value)
        self.assertEqual(trial["requested_params"]["bitrate_kbps"], 4000)
        self.assertEqual(trial["applied_params"]["bitrate_kbps"], 3980)
        self.assertEqual(trial["applied_params_unknown"], ["profile"])
        self.assertEqual(json.loads(requested_path.read_text())["bitrate_kbps"], 4000)
        self.assertEqual(json.loads(applied_path.read_text())["bitrate_kbps"], 3980)

    def test_failed_trial_does_not_fail_session_and_marks_recommendation_failed(self) -> None:
        response = self.service.mark_failure(
            "sess_001",
            "trial_001",
            {
                "error_code": "CONFIGURE_FAILED",
                "error_message": "MediaCodec configure failed",
            },
        )

        session = self.store.get("sessions", "session_id", "sess_001")
        trial = self.store.get("trials", "trial_id", "trial_001")
        recommendation = self.store.get(
            "optimizer_recommendations",
            "optimizer_trial_id",
            "opt_001",
        )

        self.assertEqual(response["status"], TrialStatus.FAILED.value)
        self.assertEqual(session["status"], SessionStatus.RUNNING.value)
        self.assertEqual(trial["status"], TrialStatus.FAILED.value)
        self.assertEqual(trial["error_code"], "CONFIGURE_FAILED")
        self.assertEqual(recommendation["status"], "failed")

    def test_http_multipart_result_upload(self) -> None:
        with _ServerContext(self.database_path) as client:
            response = client.post_multipart_result(
                "/sessions/sess_001/trials/trial_001/result",
                self._result_metadata(),
                b"encoded-bytes",
            )

        trial = self.store.get("trials", "trial_id", "trial_001")
        observations = self.store.list_observations_for_session("sess_001")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["status"], "evaluated")
        self.assertEqual(response.body["bitrate_kbps"], 3980.0)
        self.assertEqual(trial["status"], "evaluated")
        self.assertTrue(Path(trial["artifact_path"]).exists())
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["trial_id"], "trial_001")

    def test_http_failure_upload(self) -> None:
        with _ServerContext(self.database_path) as client:
            response = client.post_json(
                "/sessions/sess_001/trials/trial_001/failure",
                {
                    "error_code": "CONFIGURE_FAILED",
                    "error_message": "MediaCodec configure failed",
                },
            )

        trial = self.store.get("trials", "trial_id", "trial_001")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["status"], "failed")
        self.assertEqual(trial["error_message"], "MediaCodec configure failed")

    def _create_assigned_trial(self) -> None:
        self.store.create(
            "sessions",
            {
                "session_id": "sess_001",
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.RUNNING.value,
                "search_space_version": 1,
            },
        )
        self.store.create(
            "optimizer_recommendations",
            {
                "optimizer_trial_id": "opt_001",
                "session_id": "sess_001",
                "search_space_version": 1,
                "recommended_params": {"bitrate_kbps": 4000},
                "status": "accepted",
                "metadata": {
                    "phase": "cold_start",
                    "seed": 42,
                    "search_space_version": 1,
                },
            },
        )
        self.store.create(
            "trials",
            {
                "trial_id": "trial_001",
                "session_id": "sess_001",
                "trial_index": 1,
                "status": TrialStatus.ASSIGNED.value,
                "requested_params": {
                    "bitrate_kbps": 4000,
                    "i_frame_interval_sec": 2,
                    "profile": "baseline",
                },
                "applied_params": {},
                "applied_params_unknown": [],
                "optimizer_trial_id": "opt_001",
                "search_space_version": 1,
            },
        )
        self.store.update(
            "optimizer_recommendations",
            "optimizer_trial_id",
            "opt_001",
            {"trial_id": "trial_001"},
        )

    def _result_metadata(self) -> dict[str, object]:
        return {
            "applied_params": {
                "bitrate_kbps": 3980,
                "i_frame_interval_sec": 2,
            },
            "applied_params_unknown": ["profile"],
            "encoder_log": {"frames": 30},
        }


class JsonResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body


class _ServerClient:
    def __init__(self, port: int) -> None:
        self.port = port

    def post_json(self, path: str, payload: dict[str, object]) -> JsonResponse:
        body = json.dumps(payload).encode("utf-8")
        return self._request(
            "POST",
            path,
            body,
            {"Content-Type": "application/json"},
        )

    def post_multipart_result(
        self,
        path: str,
        metadata: dict[str, object],
        artifact: bytes,
    ) -> JsonResponse:
        boundary = "test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="metadata"\r\n'
            "Content-Type: application/json\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="artifact"; filename="output.h264"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + artifact + f"\r\n--{boundary}--\r\n".encode("utf-8")

        return self._request(
            "POST",
            path,
            body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    def _request(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> JsonResponse:
        connection = HTTPConnection("127.0.0.1", self.port)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = json.loads(response.read().decode("utf-8"))
        connection.close()
        return JsonResponse(response.status, response_body)


class _ServerContext:
    def __init__(self, database_path: Path) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(database_path))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _ServerClient:
        self.thread.start()
        return _ServerClient(self.server.server_port)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
