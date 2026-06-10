import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.models.enums import SessionStatus, TrialStatus
from backend.services.baseline_service import BaselineSelectionError, BaselineService
from backend.storage.metadata_store import MetadataStore


class BaselineSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.service = BaselineService(self.store)
        self._create_session()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_selects_first_android_default_trial_as_baseline(self) -> None:
        self._create_evaluated_trial(
            "trial_001",
            "obs_001",
            {"bitrate_kbps": 1000},
            bitrate_kbps=1000,
        )
        self._create_evaluated_trial(
            "trial_002",
            "obs_002",
            {"bitrate_kbps": 3000, "preset": "android_default"},
            bitrate_kbps=3000,
        )
        self._create_evaluated_trial(
            "trial_003",
            "obs_003",
            {"bitrate_kbps": 5000, "preset": "android_default"},
            bitrate_kbps=5000,
        )

        response = self.service.select_baseline("sess_001")

        session = self.store.get("sessions", "session_id", "sess_001")
        baseline = self.store.get("observations", "observation_id", "obs_002")
        other = self.store.get("observations", "observation_id", "obs_003")

        self.assertEqual(response["baseline_trial_id"], "trial_002")
        self.assertEqual(session["baseline_trial_id"], "trial_002")
        self.assertEqual(baseline["is_baseline"], 1)
        self.assertEqual(other["is_baseline"], 0)
        self.assertIn("Android default", response["reason"])

    def test_selects_cold_start_trial_closest_to_center_bitrate(self) -> None:
        self._create_evaluated_trial(
            "trial_001",
            "obs_001",
            {"bitrate_kbps": 1000},
            bitrate_kbps=1000,
            optimizer_trial_id="opt_001",
        )
        self._create_evaluated_trial(
            "trial_002",
            "obs_002",
            {"bitrate_kbps": 6500},
            bitrate_kbps=6500,
            optimizer_trial_id="opt_002",
        )
        self._create_evaluated_trial(
            "trial_003",
            "obs_003",
            {"bitrate_kbps": 12000},
            bitrate_kbps=12000,
            optimizer_trial_id="opt_003",
        )

        response = self.service.select_baseline("sess_001")

        self.assertEqual(response["baseline_trial_id"], "trial_002")
        self.assertIn("center bitrate", response["reason"])

    def test_stores_baseline_selection_reason(self) -> None:
        self._create_evaluated_trial(
            "trial_001",
            "obs_001",
            {"bitrate_kbps": 6500},
            bitrate_kbps=6500,
            optimizer_trial_id="opt_001",
        )

        response = self.service.select_baseline("sess_001")

        metadata = self.store.list("report_metadata", "session_id", "sess_001")

        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]["metadata"]["type"], "baseline_selection")
        self.assertEqual(metadata[0]["metadata"]["baseline_trial_id"], "trial_001")
        self.assertEqual(metadata[0]["metadata"]["reason"], response["reason"])

    def test_cannot_complete_session_without_baseline_observation(self) -> None:
        self._create_evaluated_trial(
            "trial_001",
            "obs_001",
            {"bitrate_kbps": 6500},
            bitrate_kbps=6500,
        )

        with self.assertRaisesRegex(BaselineSelectionError, "Baseline observation"):
            self.service.complete_session("sess_001")

    def test_completed_session_has_baseline_trial_id(self) -> None:
        self._create_evaluated_trial(
            "trial_001",
            "obs_001",
            {"bitrate_kbps": 6500},
            bitrate_kbps=6500,
            optimizer_trial_id="opt_001",
        )

        self.service.select_baseline("sess_001")
        response = self.service.complete_session("sess_001")

        session = self.store.get("sessions", "session_id", "sess_001")

        self.assertEqual(response["status"], SessionStatus.COMPLETED.value)
        self.assertEqual(session["status"], SessionStatus.COMPLETED.value)
        self.assertEqual(session["baseline_trial_id"], "trial_001")

    def _create_session(self) -> None:
        self.store.create(
            "sessions",
            {
                "session_id": "sess_001",
                "input_video_id": "sample_001",
                "target_codec": "auto",
                "target_mime": "video/avc",
                "status": SessionStatus.RUNNING.value,
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
                },
                "created_from": ["adr_rule", "capability"],
            },
        )

    def _create_evaluated_trial(
        self,
        trial_id: str,
        observation_id: str,
        requested_params: dict[str, object],
        bitrate_kbps: float,
        optimizer_trial_id: str | None = None,
    ) -> None:
        if optimizer_trial_id is not None:
            self.store.create(
                "optimizer_recommendations",
                {
                    "optimizer_trial_id": optimizer_trial_id,
                    "session_id": "sess_001",
                    "search_space_version": 1,
                    "recommended_params": requested_params,
                    "status": "evaluated",
                    "metadata": {
                        "phase": "cold_start",
                        "seed": 42,
                        "search_space_version": 1,
                    },
                },
            )
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": "sess_001",
                "trial_index": int(trial_id.rsplit("_", 1)[1]),
                "status": TrialStatus.EVALUATED.value,
                "requested_params": requested_params,
                "applied_params": requested_params,
                "applied_params_unknown": [],
                "optimizer_trial_id": optimizer_trial_id,
                "search_space_version": 1,
            },
        )
        if optimizer_trial_id is not None:
            self.store.update(
                "optimizer_recommendations",
                "optimizer_trial_id",
                optimizer_trial_id,
                {"trial_id": trial_id},
            )
        self.store.create(
            "observations",
            {
                "observation_id": observation_id,
                "trial_id": trial_id,
                "bitrate_kbps": bitrate_kbps,
                "vmaf": 90.0,
                "evaluation_log_path": "",
                "is_baseline": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
