import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from backend.models.enums import SessionStatus
from backend.server import make_handler
from backend.services.session_service import SessionService
from backend.storage.metadata_store import MetadataStore


class CapabilityRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = SessionService(self.store)
        self.store.create(
            "sessions",
            {
                "session_id": "sess_001",
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.CREATED.value,
            },
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_capability_registration_creates_search_space_version(self) -> None:
        response = self.service.register_capability("sess_001", self._capability_payload())

        session = self.store.get("sessions", "session_id", "sess_001")
        search_space = self.store.get("search_spaces", "session_id", "sess_001")

        self.assertEqual(response["search_space_version"], 1)
        self.assertEqual(session["search_space_version"], 1)
        self.assertEqual(search_space["search_space_version"], 1)
        self.assertEqual(
            search_space["parameters"],
            {
                "bitrate_kbps": {"type": "integer", "min": 1000, "max": 12000},
                "i_frame_interval_sec": {"type": "number", "min": 1, "max": 5},
                "profile": {"type": "categorical", "values": ["baseline", "main"]},
            },
        )

    def test_unsupported_parameters_and_vendor_keys_are_stored_as_rejections(self) -> None:
        self.service.register_capability("sess_001", self._capability_payload())

        decisions = self.store.list("constraint_decisions", "session_id", "sess_001")
        rejected_parameters = {decision["parameter_name"] for decision in decisions}

        self.assertIn("qp_min", rejected_parameters)
        self.assertIn("qp_max", rejected_parameters)
        self.assertIn("b_frame_count", rejected_parameters)
        self.assertIn("bitrate_mode", rejected_parameters)
        self.assertIn("vendor_extensions", rejected_parameters)
        self.assertIn("vendor_extensions.vendor.example.key", rejected_parameters)

    def test_capability_registration_moves_session_to_ready(self) -> None:
        self.service.register_capability("sess_001", self._capability_payload())

        session = self.store.get("sessions", "session_id", "sess_001")

        self.assertEqual(session["status"], SessionStatus.READY.value)

    def test_profile_uses_capability_values_only(self) -> None:
        payload = self._capability_payload()
        payload["codec"]["profiles"] = ["baseline"]

        self.service.register_capability("sess_001", payload)

        search_space = self.store.get("search_spaces", "session_id", "sess_001")
        self.assertEqual(search_space["parameters"]["profile"]["values"], ["baseline"])

    def test_missing_profiles_are_rejected_and_not_added_to_search_space(self) -> None:
        payload = self._capability_payload()
        payload["codec"]["profiles"] = []

        self.service.register_capability("sess_001", payload)

        search_space = self.store.get("search_spaces", "session_id", "sess_001")
        decisions = self.store.list("constraint_decisions", "session_id", "sess_001")

        self.assertNotIn("profile", search_space["parameters"])
        self.assertIn("profile", {decision["parameter_name"] for decision in decisions})

    def test_http_capability_registration_returns_ready_session(self) -> None:
        with _ServerContext(self.database_path) as client:
            response = client.request_json(
                "POST",
                "/sessions/sess_001/capabilities",
                self._capability_payload(),
            )

        session = self.store.get("sessions", "session_id", "sess_001")

        self.assertEqual(response.status, 201)
        self.assertEqual(response.body["status"], "ready")
        self.assertEqual(response.body["search_space_version"], 1)
        self.assertEqual(session["status"], "ready")

    def _capability_payload(self) -> dict[str, object]:
        return {
            "device": {
                "model": "android-device",
                "android_version": "14",
                "soc_vendor": "unknown",
            },
            "codec": {
                "codec_name": "OMX.example.avc.encoder",
                "mime_type": "video/avc",
                "profiles": ["baseline", "main"],
                "bitrate_modes": ["cbr", "vbr"],
                "supports_b_frame": False,
                "vendor_keys": ["vendor.example.key"],
            },
            "raw_payload": {"source": "unit-test"},
        }


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
        payload: dict[str, object],
    ) -> JsonResponse:
        body = json.dumps(payload)
        connection = HTTPConnection("127.0.0.1", self.port)
        connection.request(
            method,
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
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
