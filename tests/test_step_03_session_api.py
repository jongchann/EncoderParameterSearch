import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from backend.models.enums import SessionStatus, TrialStatus
from backend.server import make_handler
from backend.services.session_service import SessionNotReadyError, SessionService
from backend.storage.metadata_store import MetadataStore


class SessionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = SessionService(self.store)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_session_starts_as_created(self) -> None:
        response = self.service.create_session(
            {
                "input_video_id": "sample_001",
                "target_mime": "video/avc",
                "target_codec": "auto",
            }
        )

        session = self.store.get("sessions", "session_id", response["session_id"])
        self.assertEqual(response["status"], SessionStatus.CREATED.value)
        self.assertEqual(session["status"], SessionStatus.CREATED.value)

    def test_get_session_includes_trial_counts_and_search_space_version(self) -> None:
        self._create_session("sess_001")
        self._create_trial("trial_001", TrialStatus.ASSIGNED.value)
        self._create_trial("trial_002", TrialStatus.EVALUATED.value)
        self._create_trial("trial_003", TrialStatus.FAILED.value)
        self.store.update(
            "sessions",
            "session_id",
            "sess_001",
            {"search_space_version": 2},
        )

        session = self.service.get_session("sess_001")

        self.assertEqual(session["trial_count"], 3)
        self.assertEqual(session["evaluated_trial_count"], 1)
        self.assertEqual(session["failed_trial_count"], 1)
        self.assertEqual(session["current_search_space_version"], 2)

    def test_get_constraints_returns_session_decisions(self) -> None:
        self._create_session("sess_001")
        self.store.create(
            "constraint_decisions",
            {
                "decision_id": "decision_001",
                "session_id": "sess_001",
                "parameter_name": "vendor_extensions",
                "decision": "rejected",
                "reason": "MVP excludes vendor extensions",
                "source_type": "adr_rule",
                "source_ref": "adr_001",
            },
        )

        response = self.service.get_constraints("sess_001")

        self.assertEqual(response["session_id"], "sess_001")
        self.assertEqual(len(response["constraints"]), 1)
        self.assertEqual(response["constraints"][0]["decision"], "rejected")

    def test_next_trial_before_capability_registration_is_clear_error(self) -> None:
        self._create_session("sess_001")

        with self.assertRaisesRegex(
            SessionNotReadyError,
            "Capability registration is required",
        ):
            self.service.get_next_trial("sess_001")

    def test_http_create_and_read_session(self) -> None:
        with self._server() as client:
            created = client.request_json(
                "POST",
                "/sessions",
                {
                    "input_video_id": "sample_001",
                    "target_mime": "video/avc",
                    "target_codec": "auto",
                },
            )
            read = client.request_json("GET", f"/sessions/{created.body['session_id']}")

        self.assertEqual(created.status, 201)
        self.assertEqual(created.body["status"], "created")
        self.assertEqual(read.status, 200)
        self.assertEqual(read.body["trial_count"], 0)
        self.assertIsNone(read.body["current_search_space_version"])

    def test_http_constraints_endpoint(self) -> None:
        self._create_session("sess_001")

        with self._server() as client:
            response = client.request_json("GET", "/sessions/sess_001/constraints")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, {"session_id": "sess_001", "constraints": []})

    def test_http_next_trial_before_capability_registration_returns_409(self) -> None:
        self._create_session("sess_001")

        with self._server() as client:
            response = client.request_json("GET", "/sessions/sess_001/trials/next")

        self.assertEqual(response.status, 409)
        self.assertEqual(
            response.body,
            {
                "detail": "Capability registration is required before trial generation.",
            },
        )

    def _create_session(self, session_id: str) -> None:
        self.store.create(
            "sessions",
            {
                "session_id": session_id,
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.CREATED.value,
            },
        )

    def _create_trial(self, trial_id: str, status: str) -> None:
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": "sess_001",
                "trial_index": int(trial_id.rsplit("_", 1)[1]),
                "status": status,
                "requested_params": {"bitrate_kbps": 4000},
                "applied_params": {},
                "applied_params_unknown": [],
            },
        )

    def _server(self) -> "_ServerContext":
        return _ServerContext(self.database_path)


class JsonResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body


class _ServerClient:
    def __init__(self, port: int) -> None:
        self.port = port

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> JsonResponse:
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"

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
