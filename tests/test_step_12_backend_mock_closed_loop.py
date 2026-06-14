import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from backend.models.enums import SessionStatus, TrialStatus
from backend.server import make_handler
from backend.services.baseline_service import BaselineService
from backend.services.report_service import ReportService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class BackendMockClosedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_http_mock_loop_can_complete_after_15_evaluated_trials(self) -> None:
        with _ServerContext(self.database_path) as client:
            created = client.post_json(
                "/sessions",
                {
                    "input_video_id": "sample_001",
                    "target_codec": "auto",
                    "target_mime": "video/avc",
                },
            )
            session_id = created.body["session_id"]

            capability = client.post_json(
                f"/sessions/{session_id}/capabilities",
                self._capability_payload(),
            )

            for _ in range(15):
                assignment = client.request_json(
                    "GET",
                    f"/sessions/{session_id}/trials/next",
                )
                trial_id = assignment.body["trial_id"]
                requested_params = assignment.body["requested_params"]

                upload = client.post_multipart_result(
                    f"/sessions/{session_id}/trials/{trial_id}/result",
                    self._result_metadata(requested_params),
                    f"encoded-{trial_id}".encode("utf-8"),
                )

                self.assertEqual(upload.status, 200)
                self.assertEqual(upload.body["status"], TrialStatus.EVALUATED.value)

        baseline_service = BaselineService(self.store)
        report_service = ReportService(self.store, ArtifactStore(self.root))
        baseline = baseline_service.select_baseline(session_id)
        report = report_service.generate_report(session_id)
        completed = baseline_service.complete_session(session_id)

        session = self.store.get("sessions", "session_id", session_id)

        self.assertEqual(created.status, 201)
        self.assertEqual(capability.status, 201)
        self.assertEqual(self.store.count("observations"), 15)
        self.assertEqual(
            self.store.count_trials_by_status(session_id, TrialStatus.EVALUATED.value),
            15,
        )
        self.assertEqual(completed["status"], SessionStatus.COMPLETED.value)
        self.assertEqual(session["status"], SessionStatus.COMPLETED.value)
        self.assertEqual(session["baseline_trial_id"], baseline["baseline_trial_id"])
        self.assertIsNotNone(session["completed_at"])
        self.assertTrue(Path(report["report_path"]).exists())

    def _capability_payload(self) -> dict[str, object]:
        return {
            "device": {
                "model": "MockDevice",
                "android_version": "15",
                "soc_vendor": "mock",
            },
            "codec": {
                "codec_name": "mock-avc",
                "mime_type": "video/avc",
                "profiles": ["baseline", "main"],
                "bitrate_modes": ["cbr"],
                "supports_b_frame": False,
                "vendor_keys": [],
            },
        }

    def _result_metadata(self, requested_params: dict[str, object]) -> dict[str, object]:
        applied_params = {
            key: value for key, value in requested_params.items() if key != "profile"
        }
        return {
            "applied_params": applied_params,
            "applied_params_unknown": ["profile"] if "profile" in requested_params else [],
            "encoder_log": {"mode": "backend_mock_closed_loop"},
        }


class JsonResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body


class _ServerClient:
    def __init__(self, port: int) -> None:
        self.port = port

    def request_json(self, method: str, path: str) -> JsonResponse:
        return self._request(method, path, b"", {})

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
