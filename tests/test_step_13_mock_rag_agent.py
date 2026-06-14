import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.models.enums import SessionStatus, TrialStatus
from backend.services.mock_rag_agent_service import (
    MOCK_RETRIEVAL_CORPUS_VERSION,
    REPORT_PROMPT_VERSION,
    MockRagAgentService,
)
from backend.services.report_service import ReportService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class MockRagAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.artifact_store = ArtifactStore(self.root)
        self.service = MockRagAgentService(self.store, self.artifact_store)
        self._create_session()
        self._create_trial()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_mock_report_section_records_snapshot_and_aiops_versions(self) -> None:
        response = self.service.generate_report_section("sess_001")

        rag_output = self.store.get(
            "rag_outputs",
            "rag_output_id",
            response["rag_output_id"],
        )
        event = self.store.get("aiops_events", "event_id", response["aiops_event_id"])
        snapshot_path = Path(rag_output["retrieval_snapshot_path"])
        snapshot = json.loads(snapshot_path.read_text())

        self.assertEqual(response["status"], "recorded")
        self.assertTrue(snapshot_path.exists())
        self.assertEqual(snapshot["retrieval_corpus_version"], MOCK_RETRIEVAL_CORPUS_VERSION)
        self.assertTrue(snapshot["sources"])
        self.assertEqual(event["event_type"], "guardrail_passed")
        self.assertEqual(
            event["payload"]["retrieval_corpus_version"],
            MOCK_RETRIEVAL_CORPUS_VERSION,
        )

    def test_mock_generator_records_supported_output_types(self) -> None:
        constraint = self.service.generate_constraint_candidate("sess_001", "b_frame_count")
        failure = self.service.generate_failure_analysis(
            "sess_001",
            "trial_001",
            "CONFIGURE_FAILED",
        )
        report = self.service.generate_report_section("sess_001")

        self.assertEqual(constraint["status"], "recorded")
        self.assertEqual(failure["status"], "recorded")
        self.assertEqual(report["status"], "recorded")
        self.assertEqual(self.store.count("rag_outputs", "session_id", "sess_001"), 3)
        self.assertEqual(self.store.count("aiops_events", "session_id", "sess_001"), 3)

    def test_report_metadata_includes_mock_rag_corpus_version(self) -> None:
        self.service.generate_report_section("sess_001")

        report = ReportService(self.store, self.artifact_store).generate_report("sess_001")

        self.assertEqual(report["metadata"]["prompt_version"], REPORT_PROMPT_VERSION)
        self.assertEqual(
            report["metadata"]["retrieval_corpus_version"],
            MOCK_RETRIEVAL_CORPUS_VERSION,
        )
        self.assertEqual(report["metadata"]["rag_status"], "available")
        self.assertIn(MOCK_RETRIEVAL_CORPUS_VERSION, report["markdown"])
        self.assertIn("mock RAG summary", report["markdown"])

    def _create_session(self) -> None:
        self.store.create(
            "sessions",
            {
                "session_id": "sess_001",
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.READY.value,
                "search_space_version": 1,
                "baseline_trial_id": None,
            },
        )
        self.store.create(
            "search_spaces",
            {
                "session_id": "sess_001",
                "search_space_version": 1,
                "parameters": {
                    "bitrate_kbps": {"type": "integer", "min": 1000, "max": 12000}
                },
                "created_from": ["adr_rule", "capability"],
            },
        )

    def _create_trial(self) -> None:
        self.store.create(
            "trials",
            {
                "trial_id": "trial_001",
                "session_id": "sess_001",
                "trial_index": 1,
                "status": TrialStatus.FAILED.value,
                "requested_params": {"bitrate_kbps": 4000},
                "applied_params": {},
                "applied_params_unknown": [],
                "search_space_version": 1,
                "error_code": "CONFIGURE_FAILED",
                "error_message": "configure failed",
            },
        )


if __name__ == "__main__":
    unittest.main()
