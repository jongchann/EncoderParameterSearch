import sqlite3
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.api.health import health_check
from backend.server import RequestHandler
from backend.storage.sqlite import initialize_database
from http.server import ThreadingHTTPServer
from threading import Thread


class SkeletonTests(unittest.TestCase):
    def test_health_check_returns_ok(self) -> None:
        self.assertEqual(health_check(), {"status": "ok"})

    def test_initialize_database_creates_empty_metadata_store(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "metadata.sqlite3"

            initialize_database(database_path)

            self.assertTrue(database_path.exists())
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchone()
            self.assertEqual(row, (1,))

    def test_project_scripts_use_virtual_environment(self) -> None:
        project_root = Path(__file__).resolve().parents[1]

        run_server = (project_root / "scripts" / "run_server.sh").read_text()
        test_script = (project_root / "scripts" / "test.sh").read_text()

        self.assertIn(".venv/bin/python -m backend.server", run_server)
        self.assertIn(".venv/bin/python -m unittest", test_script)

    def test_health_endpoint_returns_ok_json(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            connection = HTTPConnection("127.0.0.1", server.server_port)
            connection.request("GET", "/health")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(body, '{"status": "ok"}')


if __name__ == "__main__":
    unittest.main()
