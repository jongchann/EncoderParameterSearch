import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.models.enums import SessionStatus
from backend.services.report_service import ReportService
from backend.services.rag_output_service import RagOutputService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class RagGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = RagOutputService(self.store)
        self._create_session()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_valid_constraint_candidate_is_recorded_with_guardrail_event(self) -> None:
        response = self.service.record_output(
            session_id="sess_001",
            output_type="constraint_candidate",
            payload=self._constraint_candidate_payload(),
            sources=self._sources(),
            prompt_version="constraint_candidate_v1",
            retrieval_snapshot_path="artifacts/sess_001/rag/snapshots/rag_001.json",
        )

        rag_output = self.store.get(
            "rag_outputs",
            "rag_output_id",
            response["rag_output_id"],
        )
        event = self.store.get("aiops_events", "event_id", response["aiops_event_id"])

        self.assertEqual(response["status"], "recorded")
        self.assertIsNone(response["validation_error"])
        self.assertEqual(rag_output["status"], "recorded")
        self.assertEqual(rag_output["payload"]["parameter_name"], "b_frame_count")
        self.assertEqual(event["event_type"], "guardrail_passed")
        self.assertEqual(event["payload"]["source_count"], 1)

    def test_source_less_constraint_candidate_is_ignored_and_not_applied(self) -> None:
        response = self.service.record_output(
            session_id="sess_001",
            output_type="constraint_candidate",
            payload=self._constraint_candidate_payload(),
            sources=[],
            prompt_version="constraint_candidate_v1",
            retrieval_snapshot_path="artifacts/sess_001/rag/snapshots/rag_001.json",
        )

        rag_output = self.store.get(
            "rag_outputs",
            "rag_output_id",
            response["rag_output_id"],
        )
        event = self.store.get("aiops_events", "event_id", response["aiops_event_id"])

        self.assertEqual(response["status"], "ignored")
        self.assertIn("source reference", response["validation_error"])
        self.assertEqual(rag_output["status"], "ignored")
        self.assertEqual(event["event_type"], "guardrail_blocked")
        self.assertEqual(self.store.count("constraint_decisions", "session_id", "sess_001"), 0)
        self.assertEqual(self.store.count("search_spaces", "session_id", "sess_001"), 1)

    def test_schema_invalid_rag_output_is_ignored_with_aiops_event(self) -> None:
        response = self.service.record_output(
            session_id="sess_001",
            output_type="failure_analysis",
            payload={"trial_id": "trial_001", "failure_type": "CONFIGURE_FAILED"},
            sources=self._sources(),
            prompt_version="failure_analysis_v1",
            retrieval_snapshot_path="artifacts/sess_001/rag/snapshots/rag_002.json",
        )

        rag_output = self.store.get(
            "rag_outputs",
            "rag_output_id",
            response["rag_output_id"],
        )
        event = self.store.get("aiops_events", "event_id", response["aiops_event_id"])

        self.assertEqual(response["status"], "ignored")
        self.assertIn("candidate_causes", response["validation_error"])
        self.assertEqual(rag_output["payload"]["validation_error"], response["validation_error"])
        self.assertEqual(event["severity"], "warning")
        self.assertEqual(event["payload"]["validation_error"], response["validation_error"])

    def test_report_metadata_uses_recorded_rag_report_section(self) -> None:
        self.service.record_output(
            session_id="sess_001",
            output_type="report_section",
            payload={
                "facts": [],
                "derived_results": [],
                "interpretation": "B-frame support should remain excluded for this session.",
            },
            sources=self._sources(),
            prompt_version="report_section_v1",
            retrieval_snapshot_path="artifacts/sess_001/rag/snapshots/rag_003.json",
        )

        report = ReportService(self.store, ArtifactStore(self.root)).generate_report("sess_001")

        self.assertEqual(report["metadata"]["prompt_version"], "report_section_v1")
        self.assertEqual(
            report["metadata"]["retrieval_snapshot_path"],
            "artifacts/sess_001/rag/snapshots/rag_003.json",
        )
        self.assertEqual(report["metadata"]["rag_status"], "available")
        self.assertEqual(report["metadata"]["rag_output_count"], 1)
        self.assertEqual(report["metadata"]["source_less_narrative_count"], 0)
        self.assertEqual(
            report["metadata"]["trust_level_counts"]["ai_assisted_narrative"],
            1,
        )
        self.assertIn("B-frame support should remain excluded", report["markdown"])

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

    def _constraint_candidate_payload(self) -> dict[str, object]:
        return {
            "parameter_name": "b_frame_count",
            "candidate_decision": "rejected",
            "reason": "Capability discovery did not confirm B-frame support.",
        }

    def _sources(self) -> list[dict[str, object]]:
        return [
            {
                "source_id": "capability:sess_001",
                "source_type": "capability",
                "title": "Mock capability",
            }
        ]


if __name__ == "__main__":
    unittest.main()
