import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from backend.models.enums import SessionStatus, TrialStatus
from backend.server import make_handler
from backend.services.session_service import (
    RecommendationRejectedError,
    SessionNotReadyError,
    SessionService,
)
from backend.storage.metadata_store import MetadataStore


class TrialAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = SessionService(self.store)
        self._create_ready_session()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_next_trial_creates_assigned_trial(self) -> None:
        response = self.service.get_next_trial("sess_001")

        trial = self.store.get("trials", "trial_id", response["trial_id"])

        self.assertEqual(trial["status"], TrialStatus.ASSIGNED.value)
        self.assertEqual(trial["requested_params"], response["requested_params"])

    def test_trial_stores_optimizer_trial_id_and_search_space_version(self) -> None:
        response = self.service.get_next_trial("sess_001")
        trial = self.store.get("trials", "trial_id", response["trial_id"])
        recommendation = self.store.get(
            "optimizer_recommendations",
            "optimizer_trial_id",
            trial["optimizer_trial_id"],
        )

        self.assertIsNotNone(trial["optimizer_trial_id"])
        self.assertEqual(trial["search_space_version"], 1)
        self.assertEqual(recommendation["trial_id"], response["trial_id"])

    def test_next_trial_moves_session_to_running(self) -> None:
        self.service.get_next_trial("sess_001")

        session = self.store.get("sessions", "session_id", "sess_001")

        self.assertEqual(session["status"], SessionStatus.RUNNING.value)

    def test_running_session_can_receive_another_trial(self) -> None:
        first = self.service.get_next_trial("sess_001")
        second = self.service.get_next_trial("sess_001")

        self.assertNotEqual(first["trial_id"], second["trial_id"])
        self.assertNotEqual(first["requested_params"], second["requested_params"])
        self.assertEqual(self.store.count("trials", "session_id", "sess_001"), 2)

    def test_completed_session_cannot_receive_trial(self) -> None:
        self.store.update(
            "sessions",
            "session_id",
            "sess_001",
            {"status": SessionStatus.COMPLETED.value},
        )

        with self.assertRaisesRegex(SessionNotReadyError, "ready or running"):
            self.service.get_next_trial("sess_001")

    def test_rejected_recommendation_is_not_sent_to_client(self) -> None:
        service = SessionService(
            self.store,
            optimizer_service=_InvalidOptimizer(self.store),
        )

        with self.assertRaisesRegex(RecommendationRejectedError, "rejected"):
            service.get_next_trial("sess_001")

        recommendation = self.store.get(
            "optimizer_recommendations",
            "optimizer_trial_id",
            "opt_invalid",
        )
        self.assertEqual(recommendation["status"], "rejected")
        self.assertEqual(self.store.count("trials", "session_id", "sess_001"), 0)

    def test_http_next_trial_returns_assignment(self) -> None:
        with _ServerContext(self.database_path) as client:
            response = client.request_json("GET", "/sessions/sess_001/trials/next")

        trial = self.store.get("trials", "trial_id", response.body["trial_id"])

        self.assertEqual(response.status, 200)
        self.assertEqual(trial["status"], "assigned")
        self.assertEqual(response.body["requested_params"], trial["requested_params"])

    def _create_ready_session(self) -> None:
        self.store.create(
            "sessions",
            {
                "session_id": "sess_001",
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.READY.value,
                "search_space_version": 1,
            },
        )
        self.store.create(
            "search_spaces",
            {
                "session_id": "sess_001",
                "search_space_version": 1,
                "parameters": {
                    "bitrate_kbps": {"type": "integer", "min": 1000, "max": 12000},
                    "i_frame_interval_sec": {"type": "number", "min": 1, "max": 5},
                    "profile": {
                        "type": "categorical",
                        "values": ["baseline", "main"],
                    },
                },
                "created_from": ["adr_rule", "capability"],
            },
        )


class _InvalidOptimizer:
    def __init__(self, store: MetadataStore) -> None:
        self.store = store

    def recommend_next(self, session_id: str) -> dict[str, object]:
        recommended_params = {
            "bitrate_kbps": 999999,
            "i_frame_interval_sec": 1,
            "profile": "baseline",
        }
        self.store.create(
            "optimizer_recommendations",
            {
                "optimizer_trial_id": "opt_invalid",
                "session_id": session_id,
                "search_space_version": 1,
                "recommended_params": recommended_params,
                "status": "accepted",
                "metadata": {
                    "phase": "test",
                    "seed": 0,
                    "search_space_version": 1,
                },
            },
        )
        return {
            "optimizer_trial_id": "opt_invalid",
            "recommended_params": recommended_params,
            "metadata": {},
        }


class JsonResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body


class _ServerClient:
    def __init__(self, port: int) -> None:
        self.port = port

    def request_json(self, method: str, path: str) -> JsonResponse:
        connection = HTTPConnection("127.0.0.1", self.port)
        connection.request(method, path)
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
