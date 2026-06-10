import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.models.enums import SessionStatus, TrialStatus
from backend.services.optimizer_service import OptimizerService
from backend.storage.metadata_store import MetadataStore


class OptimizerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.optimizer = OptimizerService(self.store, seed=7)
        self._create_ready_session()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_first_five_cold_start_recommendations_are_unique(self) -> None:
        recommendations = [
            self.optimizer.recommend_next("sess_001")["recommended_params"]
            for _ in range(5)
        ]

        self.assertEqual(len(recommendations), 5)
        self.assertEqual(
            len({self._params_key(params) for params in recommendations}),
            5,
        )

    def test_recommendation_is_stored_with_required_metadata(self) -> None:
        recommendation = self.optimizer.recommend_next("sess_001")

        stored = self.store.get(
            "optimizer_recommendations",
            "optimizer_trial_id",
            recommendation["optimizer_trial_id"],
        )

        self.assertEqual(stored["recommended_params"], recommendation["recommended_params"])
        self.assertEqual(stored["status"], "accepted")
        self.assertEqual(
            stored["metadata"],
            {
                "phase": "cold_start",
                "seed": 7,
                "search_space_version": 1,
            },
        )

    def test_new_recommendation_can_be_generated_after_observation_is_added(self) -> None:
        recommendation = self.optimizer.recommend_next("sess_001")
        self._create_evaluated_trial("trial_001", recommendation["recommended_params"])

        next_recommendation = self.optimizer.recommend_next("sess_001")

        self.assertNotEqual(
            recommendation["recommended_params"],
            next_recommendation["recommended_params"],
        )

    def test_failed_parameters_are_avoided(self) -> None:
        failed_params = {
            "bitrate_kbps": 1000,
            "i_frame_interval_sec": 1,
            "profile": "baseline",
        }
        self._create_failed_trial("trial_001", failed_params)

        recommendation = self.optimizer.recommend_next("sess_001")

        self.assertNotEqual(recommendation["recommended_params"], failed_params)

    def test_recommendations_are_inside_active_search_space(self) -> None:
        for _ in range(8):
            recommendation = self.optimizer.recommend_next("sess_001")
            params = recommendation["recommended_params"]

            self.assertGreaterEqual(params["bitrate_kbps"], 1000)
            self.assertLessEqual(params["bitrate_kbps"], 12000)
            self.assertGreaterEqual(params["i_frame_interval_sec"], 1)
            self.assertLessEqual(params["i_frame_interval_sec"], 5)
            self.assertIn(params["profile"], ["baseline", "main"])

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

    def _create_evaluated_trial(self, trial_id: str, params: dict[str, object]) -> None:
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": "sess_001",
                "trial_index": 1,
                "status": TrialStatus.EVALUATED.value,
                "requested_params": params,
                "applied_params": params,
                "applied_params_unknown": [],
                "search_space_version": 1,
            },
        )
        self.store.create(
            "observations",
            {
                "observation_id": "obs_001",
                "trial_id": trial_id,
                "bitrate_kbps": 3900,
                "vmaf": 92.0,
                "is_baseline": 0,
            },
        )

    def _create_failed_trial(self, trial_id: str, params: dict[str, object]) -> None:
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": "sess_001",
                "trial_index": 1,
                "status": TrialStatus.FAILED.value,
                "requested_params": params,
                "applied_params": {},
                "applied_params_unknown": [],
                "search_space_version": 1,
                "error_code": "CONFIGURE_FAILED",
                "error_message": "configure failed",
            },
        )

    def _params_key(self, params: dict[str, object]) -> str:
        return "|".join(f"{key}={params[key]}" for key in sorted(params))


if __name__ == "__main__":
    unittest.main()
