import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.models.enums import SessionStatus, TrialStatus
from backend.storage.metadata_store import MetadataStore


class MetadataSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_schema_initializes_all_step_02_tables(self) -> None:
        expected_tables = {
            "schema_migrations",
            "sessions",
            "devices",
            "capabilities",
            "search_spaces",
            "constraint_decisions",
            "trials",
            "observations",
            "optimizer_recommendations",
            "report_metadata",
            "rag_outputs",
            "aiops_events",
        }

        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()

        self.assertTrue(expected_tables.issubset({row[0] for row in rows}))

    def test_session_crud(self) -> None:
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

        session = self.store.get("sessions", "session_id", "sess_001")
        self.assertIsNotNone(session)
        self.assertEqual(session["status"], "created")

        self.store.update(
            "sessions",
            "session_id",
            "sess_001",
            {"status": SessionStatus.READY.value, "search_space_version": 1},
        )
        updated = self.store.get("sessions", "session_id", "sess_001")
        self.assertEqual(updated["status"], "ready")
        self.assertEqual(updated["search_space_version"], 1)

        self.store.delete("sessions", "session_id", "sess_001")
        self.assertIsNone(self.store.get("sessions", "session_id", "sess_001"))

    def test_device_crud(self) -> None:
        self.store.create(
            "devices",
            {
                "device_id": "dev_001",
                "model": "android-device",
                "android_version": "14",
                "soc_vendor": "unknown",
            },
        )

        device = self.store.get("devices", "device_id", "dev_001")
        self.assertEqual(device["model"], "android-device")

        self.store.delete("devices", "device_id", "dev_001")
        self.assertIsNone(self.store.get("devices", "device_id", "dev_001"))

    def test_capability_json_round_trip(self) -> None:
        self._create_device()

        self.store.create(
            "capabilities",
            {
                "capability_id": "cap_001",
                "device_id": "dev_001",
                "codec_name": "OMX.example.avc.encoder",
                "mime_type": "video/avc",
                "profiles": ["baseline", "main"],
                "bitrate_modes": ["cbr", "vbr"],
                "supports_b_frame": 0,
                "vendor_keys": ["vendor.example.key"],
                "raw_payload": {"codec": {"profiles": ["baseline", "main"]}},
            },
        )

        capability = self.store.get("capabilities", "capability_id", "cap_001")
        self.assertEqual(capability["profiles"], ["baseline", "main"])
        self.assertEqual(capability["raw_payload"]["codec"]["profiles"], ["baseline", "main"])

    def test_search_space_json_round_trip(self) -> None:
        self._create_session()

        self.store.create(
            "search_spaces",
            {
                "search_space_version": 1,
                "session_id": "sess_001",
                "parameters": {
                    "bitrate_kbps": {"type": "int", "min": 1000, "max": 12000},
                    "profile": {"type": "categorical", "values": ["baseline"]},
                },
                "created_from": ["adr_rule", "capability"],
            },
        )

        search_space = self.store.get("search_spaces", "session_id", "sess_001")
        self.assertEqual(search_space["parameters"]["profile"]["values"], ["baseline"])
        self.assertEqual(search_space["created_from"], ["adr_rule", "capability"])

    def test_constraint_decision_crud(self) -> None:
        self._create_session()

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

        decision = self.store.get("constraint_decisions", "decision_id", "decision_001")
        self.assertEqual(decision["decision"], "rejected")

    def test_trial_json_round_trip(self) -> None:
        self._create_session()

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
                "applied_params_unknown": ["profile"],
                "optimizer_trial_id": "opt_001",
                "search_space_version": 1,
            },
        )

        trial = self.store.get("trials", "trial_id", "trial_001")
        self.assertEqual(trial["requested_params"]["bitrate_kbps"], 4000)
        self.assertEqual(trial["applied_params_unknown"], ["profile"])

    def test_observation_crud(self) -> None:
        self._create_trial()

        self.store.create(
            "observations",
            {
                "observation_id": "obs_001",
                "trial_id": "trial_001",
                "bitrate_kbps": 3980.5,
                "vmaf": 92.1,
                "evaluation_log_path": "artifacts/sess_001/trials/trial_001/eval.json",
                "is_baseline": 1,
            },
        )

        observation = self.store.get("observations", "observation_id", "obs_001")
        self.assertEqual(observation["vmaf"], 92.1)
        self.assertEqual(observation["is_baseline"], 1)

    def test_optimizer_recommendation_json_round_trip(self) -> None:
        self._create_session()

        self.store.create(
            "optimizer_recommendations",
            {
                "optimizer_trial_id": "opt_001",
                "session_id": "sess_001",
                "search_space_version": 1,
                "recommended_params": {"bitrate_kbps": 4000},
                "status": "accepted",
                "metadata": {"phase": "cold_start", "seed": 42},
            },
        )

        recommendation = self.store.get(
            "optimizer_recommendations",
            "optimizer_trial_id",
            "opt_001",
        )
        self.assertEqual(recommendation["recommended_params"], {"bitrate_kbps": 4000})
        self.assertEqual(recommendation["metadata"]["phase"], "cold_start")

    def test_report_metadata_json_round_trip(self) -> None:
        self._create_session()

        self.store.create(
            "report_metadata",
            {
                "report_id": "report_001",
                "session_id": "sess_001",
                "report_path": "artifacts/sess_001/report.md",
                "metadata": {"format": "markdown", "sections": ["pareto_set"]},
            },
        )

        report = self.store.get("report_metadata", "report_id", "report_001")
        self.assertEqual(report["metadata"]["sections"], ["pareto_set"])

    def test_rag_output_json_round_trip(self) -> None:
        self._create_session()

        self.store.create(
            "rag_outputs",
            {
                "rag_output_id": "rag_001",
                "session_id": "sess_001",
                "trial_id": None,
                "output_type": "constraint_candidate",
                "payload": {
                    "parameter_name": "b_frame_count",
                    "candidate_decision": "rejected",
                    "reason": "Capability did not confirm support.",
                },
                "sources": [
                    {
                        "source_id": "capability:sess_001",
                        "source_type": "capability",
                    }
                ],
                "prompt_version": "constraint_candidate_v1",
                "retrieval_snapshot_path": "artifacts/sess_001/rag/snapshot.json",
                "status": "recorded",
            },
        )

        rag_output = self.store.get("rag_outputs", "rag_output_id", "rag_001")
        self.assertEqual(rag_output["payload"]["parameter_name"], "b_frame_count")
        self.assertEqual(rag_output["sources"][0]["source_id"], "capability:sess_001")

    def test_aiops_event_json_round_trip(self) -> None:
        self._create_session()

        self.store.create(
            "aiops_events",
            {
                "event_id": "aiops_001",
                "session_id": "sess_001",
                "component": "rag",
                "event_type": "guardrail_passed",
                "severity": "info",
                "payload": {
                    "prompt_version": "constraint_candidate_v1",
                    "source_count": 1,
                },
            },
        )

        event = self.store.get("aiops_events", "event_id", "aiops_001")
        self.assertEqual(event["payload"]["source_count"], 1)

    def test_documented_status_enums_are_available(self) -> None:
        self.assertEqual(
            {status.value for status in SessionStatus},
            {"created", "ready", "running", "completed", "failed"},
        )
        self.assertEqual(
            {status.value for status in TrialStatus},
            {"pending", "assigned", "uploaded", "evaluated", "failed"},
        )

    def _create_session(self) -> None:
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

    def _create_device(self) -> None:
        self.store.create(
            "devices",
            {
                "device_id": "dev_001",
                "model": "android-device",
                "android_version": "14",
                "soc_vendor": "unknown",
            },
        )

    def _create_trial(self) -> None:
        self._create_session()
        self.store.create(
            "trials",
            {
                "trial_id": "trial_001",
                "session_id": "sess_001",
                "trial_index": 1,
                "status": TrialStatus.ASSIGNED.value,
                "requested_params": {"bitrate_kbps": 4000},
                "applied_params": {},
                "applied_params_unknown": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
