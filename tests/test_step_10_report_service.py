import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from backend.models.enums import SessionStatus, TrialStatus
from backend.server import make_handler
from backend.services.report_service import REPORT_TEMPLATE_VERSION, ReportService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class ReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = ReportService(self.store, ArtifactStore(self.root))
        self._create_session_data()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_pareto_set_excludes_dominated_observations(self) -> None:
        report = self.service.generate_report("sess_001")

        pareto_trial_ids = {item["trial_id"] for item in report["pareto_set"]}

        self.assertIn("trial_001", pareto_trial_ids)
        self.assertIn("trial_003", pareto_trial_ids)
        self.assertNotIn("trial_002", pareto_trial_ids)

    def test_report_includes_baseline_comparison(self) -> None:
        report = self.service.generate_report("sess_001")

        comparison = report["baseline_comparison"]

        self.assertEqual(comparison["baseline_trial_id"], "trial_001")
        self.assertEqual(comparison["bd_rate"], "insufficient_points")
        self.assertTrue(comparison["rows"])

    def test_markdown_report_is_saved_with_required_sections(self) -> None:
        report = self.service.generate_report("sess_001")

        report_path = Path(report["report_path"])
        markdown = report_path.read_text()

        self.assertTrue(report_path.exists())
        self.assertIn("## Report Version Metadata", markdown)
        self.assertIn("## Trust Level Summary", markdown)
        self.assertIn("## Raw Metrics", markdown)
        self.assertIn("## Deterministic Results", markdown)
        self.assertIn("## AI-assisted Narrative", markdown)
        self.assertIn("AI-assisted Narrative: not available", markdown)
        self.assertIn("## Pareto Set", markdown)
        self.assertIn("## Baseline Comparison", markdown)
        self.assertIn("## Audit Trail", markdown)
        self.assertIn("## Optimizer Recommendation Audit Trail", markdown)
        self.assertIn("## Failed Trial Summary", markdown)

    def test_report_metadata_is_stored(self) -> None:
        report = self.service.generate_report("sess_001")

        metadata = self.store.list("report_metadata", "session_id", "sess_001")
        final_reports = [
            row for row in metadata if row["metadata"].get("type") == "final_report"
        ]

        self.assertEqual(len(final_reports), 1)
        self.assertEqual(final_reports[0]["report_path"], report["report_path"])
        self.assertEqual(
            final_reports[0]["metadata"]["report_template_version"],
            REPORT_TEMPLATE_VERSION,
        )
        self.assertEqual(final_reports[0]["metadata"]["search_space_version"], 1)
        self.assertEqual(final_reports[0]["metadata"]["evaluator_mode"], "mock")
        self.assertEqual(final_reports[0]["metadata"]["rag_status"], "not_available")
        self.assertEqual(final_reports[0]["metadata"]["source_less_narrative_count"], 0)
        self.assertEqual(
            final_reports[0]["metadata"]["trust_level_counts"],
            {
                "raw_metric": 3,
                "deterministic_derived_result": 2,
                "ai_assisted_narrative": 0,
            },
        )

    def test_http_get_report_works(self) -> None:
        with _ServerContext(self.database_path) as client:
            response = client.get_json("/sessions/sess_001/report")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["session_id"], "sess_001")
        self.assertTrue(Path(response.body["report_path"]).exists())
        self.assertIn("pareto_set", response.body)
        self.assertIn("baseline_comparison", response.body)
        self.assertEqual(
            response.body["metadata"]["report_template_version"],
            REPORT_TEMPLATE_VERSION,
        )

    def _create_session_data(self) -> None:
        self.store.create(
            "sessions",
            {
                "session_id": "sess_001",
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.COMPLETED.value,
                "search_space_version": 1,
                "baseline_trial_id": "trial_001",
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
                },
                "created_from": ["adr_rule", "capability"],
            },
        )
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
        for index, bitrate, vmaf, is_baseline in [
            (1, 4000, 90.0, 1),
            (2, 5000, 89.0, 0),
            (3, 6000, 94.0, 0),
        ]:
            self._create_evaluated_trial(index, bitrate, vmaf, is_baseline)
        self._create_failed_trial()

    def _create_evaluated_trial(
        self,
        index: int,
        bitrate_kbps: float,
        vmaf: float,
        is_baseline: int,
    ) -> None:
        trial_id = f"trial_{index:03d}"
        optimizer_trial_id = f"opt_{index:03d}"
        requested_params = {"bitrate_kbps": int(bitrate_kbps), "i_frame_interval_sec": 2}
        evaluation_log_path = self.root / "sess_001" / "trials" / trial_id / "evaluation_log.json"
        evaluation_log_path.parent.mkdir(parents=True, exist_ok=True)
        evaluation_log_path.write_text(json.dumps({"mode": "mock"}))
        self.store.create(
            "optimizer_recommendations",
            {
                "optimizer_trial_id": optimizer_trial_id,
                "session_id": "sess_001",
                "search_space_version": 1,
                "recommended_params": requested_params,
                "status": "evaluated",
                "metadata": {"phase": "cold_start", "seed": 42, "search_space_version": 1},
            },
        )
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": "sess_001",
                "trial_index": index,
                "status": TrialStatus.EVALUATED.value,
                "requested_params": requested_params,
                "applied_params": requested_params,
                "applied_params_unknown": [],
                "optimizer_trial_id": optimizer_trial_id,
                "search_space_version": 1,
            },
        )
        self.store.update(
            "optimizer_recommendations",
            "optimizer_trial_id",
            optimizer_trial_id,
            {"trial_id": trial_id},
        )
        self.store.create(
            "observations",
            {
                "observation_id": f"obs_{index:03d}",
                "trial_id": trial_id,
                "bitrate_kbps": bitrate_kbps,
                "vmaf": vmaf,
                "evaluation_log_path": str(evaluation_log_path),
                "is_baseline": is_baseline,
            },
        )

    def _create_failed_trial(self) -> None:
        self.store.create(
            "trials",
            {
                "trial_id": "trial_failed",
                "session_id": "sess_001",
                "trial_index": 4,
                "status": TrialStatus.FAILED.value,
                "requested_params": {"bitrate_kbps": 12000},
                "applied_params": {},
                "applied_params_unknown": [],
                "search_space_version": 1,
                "error_code": "CONFIGURE_FAILED",
                "error_message": "configure failed",
            },
        )


class JsonResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.body = body


class _ServerClient:
    def __init__(self, port: int) -> None:
        self.port = port

    def get_json(self, path: str) -> JsonResponse:
        connection = HTTPConnection("127.0.0.1", self.port)
        connection.request("GET", path)
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
