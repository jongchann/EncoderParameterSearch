from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from backend.api.health import health_check
from backend.api.multipart import MultipartParseError, parse_multipart
from backend.config import get_settings
from backend.services.session_service import (
    RecommendationRejectedError,
    SessionNotFoundError,
    SessionNotReadyError,
    SessionService,
)
from backend.services.evaluation_service import (
    EvaluationService,
    MockEvaluator,
    TrialNotEvaluableError,
)
from backend.services.report_service import ReportError, ReportService
from backend.services.trial_service import TrialNotFoundError, TrialService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore
from backend.storage.sqlite import initialize_database


class RequestHandler(BaseHTTPRequestHandler):
    database_path: Path = get_settings().database_path
    artifact_root: Path = get_settings().artifact_root

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json(200, health_check())
            return

        parts = self._path_parts(path)
        if len(parts) == 2 and parts[0] == "sessions":
            self._handle_get_session(parts[1])
            return

        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "constraints":
            self._handle_get_constraints(parts[1])
            return

        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "report":
            self._handle_get_report(parts[1])
            return

        if (
            len(parts) == 4
            and parts[0] == "sessions"
            and parts[2] == "trials"
            and parts[3] == "next"
        ):
            self._handle_get_next_trial(parts[1])
            return

        self._send_json(404, {"detail": "Not Found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/sessions":
            self._handle_create_session()
            return

        parts = self._path_parts(path)
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "capabilities":
            self._handle_register_capability(parts[1])
            return

        if (
            len(parts) == 5
            and parts[0] == "sessions"
            and parts[2] == "trials"
            and parts[4] == "result"
        ):
            self._handle_upload_trial_result(parts[1], parts[3])
            return

        if (
            len(parts) == 5
            and parts[0] == "sessions"
            and parts[2] == "trials"
            and parts[4] == "failure"
        ):
            self._handle_trial_failure(parts[1], parts[3])
            return

        self._send_json(404, {"detail": "Not Found"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_create_session(self) -> None:
        try:
            payload = self._read_json()
            response = self._session_service().create_session(payload)
        except (KeyError, json.JSONDecodeError):
            self._send_json(400, {"detail": "Invalid session request."})
            return

        self._send_json(201, response)

    def _handle_get_session(self, session_id: str) -> None:
        try:
            response = self._session_service().get_session(session_id)
        except SessionNotFoundError:
            self._send_json(404, {"detail": "Session not found."})
            return

        self._send_json(200, response)

    def _handle_get_constraints(self, session_id: str) -> None:
        try:
            response = self._session_service().get_constraints(session_id)
        except SessionNotFoundError:
            self._send_json(404, {"detail": "Session not found."})
            return

        self._send_json(200, response)

    def _handle_register_capability(self, session_id: str) -> None:
        try:
            payload = self._read_json()
            response = self._session_service().register_capability(session_id, payload)
        except SessionNotFoundError:
            self._send_json(404, {"detail": "Session not found."})
            return
        except (KeyError, json.JSONDecodeError, TypeError):
            self._send_json(400, {"detail": "Invalid capability request."})
            return

        self._send_json(201, response)

    def _handle_get_next_trial(self, session_id: str) -> None:
        try:
            response = self._session_service().get_next_trial(session_id)
        except SessionNotFoundError:
            self._send_json(404, {"detail": "Session not found."})
            return
        except SessionNotReadyError as error:
            self._send_json(409, {"detail": str(error)})
            return
        except RecommendationRejectedError as error:
            self._send_json(409, {"detail": str(error)})
            return

        self._send_json(200, response)

    def _handle_get_report(self, session_id: str) -> None:
        try:
            response = self._report_service().generate_report(session_id)
        except ReportError:
            self._send_json(404, {"detail": "Session not found."})
            return

        self._send_json(
            200,
            {
                "session_id": response["session_id"],
                "pareto_set": response["pareto_set"],
                "baseline_comparison": response["baseline_comparison"],
                "report_path": response["report_path"],
                "metadata": response["metadata"],
            },
        )

    def _handle_upload_trial_result(self, session_id: str, trial_id: str) -> None:
        try:
            parts = parse_multipart(
                self.headers.get("Content-Type", ""),
                self._read_body(),
            )
            metadata = json.loads(parts["metadata"].decode("utf-8"))
            upload_response = self._trial_service().upload_result(
                session_id,
                trial_id,
                metadata,
                parts["artifact"],
            )
            evaluation_response = self._evaluation_service().evaluate_trial(
                session_id,
                trial_id,
            )
            response = {
                **upload_response,
                **evaluation_response,
                "artifact_path": upload_response["artifact_path"],
            }
        except TrialNotFoundError:
            self._send_json(404, {"detail": "Trial not found."})
            return
        except TrialNotEvaluableError:
            self._send_json(404, {"detail": "Trial not evaluable."})
            return
        except (KeyError, json.JSONDecodeError, MultipartParseError, TypeError):
            self._send_json(400, {"detail": "Invalid trial result upload."})
            return

        self._send_json(200, response)

    def _handle_trial_failure(self, session_id: str, trial_id: str) -> None:
        try:
            response = self._trial_service().mark_failure(
                session_id,
                trial_id,
                self._read_json(),
            )
        except TrialNotFoundError:
            self._send_json(404, {"detail": "Trial not found."})
            return
        except (KeyError, json.JSONDecodeError, TypeError):
            self._send_json(400, {"detail": "Invalid trial failure request."})
            return

        self._send_json(200, response)

    def _read_json(self) -> dict[str, object]:
        body = self._read_body()
        if not body:
            return {}
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("Expected JSON object", "", 0)
        return payload

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(content_length)

    def _send_json(self, status_code: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _session_service(self) -> SessionService:
        return SessionService(MetadataStore(self.database_path))

    def _trial_service(self) -> TrialService:
        return TrialService(
            MetadataStore(self.database_path),
            ArtifactStore(self.artifact_root),
        )

    def _evaluation_service(self) -> EvaluationService:
        return EvaluationService(
            MetadataStore(self.database_path),
            ArtifactStore(self.artifact_root),
            MockEvaluator(),
        )

    def _report_service(self) -> ReportService:
        return ReportService(
            MetadataStore(self.database_path),
            ArtifactStore(self.artifact_root),
        )

    def _path_parts(self, path: str) -> list[str]:
        return [part for part in path.split("/") if part]


def make_handler(database_path: Path) -> type[RequestHandler]:
    class ConfiguredRequestHandler(RequestHandler):
        pass

    ConfiguredRequestHandler.database_path = database_path
    ConfiguredRequestHandler.artifact_root = database_path.parent
    return ConfiguredRequestHandler


def run() -> None:
    settings = get_settings()
    initialize_database(settings.database_path)

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), make_handler(settings.database_path))
    print(f"Serving on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
