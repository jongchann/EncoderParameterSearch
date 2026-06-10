import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.models.enums import SessionStatus, TrialStatus
from backend.services.evaluation_service import (
    EvaluationService,
    MockEvaluator,
    RealEvaluator,
)
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class EvaluationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "metadata.sqlite3"
        self.store = MetadataStore(self.database_path)
        self.artifact_store = ArtifactStore(self.root)
        self.service = EvaluationService(
            self.store,
            self.artifact_store,
            MockEvaluator(),
        )
        self._create_session()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_missing_artifact_is_recorded_as_evaluation_failure(self) -> None:
        self._create_uploaded_trial("trial_001", self.root / "missing.h264")

        response = self.service.evaluate_trial("sess_001", "trial_001")

        trial = self.store.get("trials", "trial_id", "trial_001")
        log = json.loads(Path(response["evaluation_log_path"]).read_text())

        self.assertEqual(response["status"], TrialStatus.FAILED.value)
        self.assertEqual(trial["status"], TrialStatus.FAILED.value)
        self.assertEqual(trial["error_code"], "EVALUATION_FAILED")
        self.assertEqual(log["mode"], "missing_artifact")

    def test_mock_evaluator_creates_observation_and_marks_trial_evaluated(self) -> None:
        artifact_path = self._write_artifact("trial_001", b"encoded-bytes")
        self._create_uploaded_trial("trial_001", artifact_path)

        response = self.service.evaluate_trial("sess_001", "trial_001")

        trial = self.store.get("trials", "trial_id", "trial_001")
        observation = self.store.get(
            "observations",
            "observation_id",
            response["observation_id"],
        )

        self.assertEqual(response["status"], TrialStatus.EVALUATED.value)
        self.assertEqual(trial["status"], TrialStatus.EVALUATED.value)
        self.assertEqual(observation["bitrate_kbps"], 4000.0)
        self.assertGreater(observation["vmaf"], 0)
        self.assertTrue(Path(observation["evaluation_log_path"]).exists())

    def test_mock_evaluator_supports_15_trial_lifecycle(self) -> None:
        for index in range(1, 16):
            trial_id = f"trial_{index:03d}"
            artifact_path = self._write_artifact(trial_id, f"encoded-{index}".encode())
            self._create_uploaded_trial(trial_id, artifact_path, trial_index=index)

            self.service.evaluate_trial("sess_001", trial_id)

        self.assertEqual(self.store.count("observations"), 15)
        self.assertEqual(
            self.store.count_trials_by_status("sess_001", TrialStatus.EVALUATED.value),
            15,
        )

    def test_real_evaluator_preserves_logs_on_failure(self) -> None:
        artifact_path = self._write_artifact("trial_001", b"not-real-video")
        self._create_uploaded_trial("trial_001", artifact_path)
        service = EvaluationService(
            self.store,
            self.artifact_store,
            RealEvaluator(
                reference_video_path=self.root / "reference.y4m",
                ffmpeg_binary="definitely-missing-ffmpeg",
            ),
        )

        response = service.evaluate_trial("sess_001", "trial_001")

        trial = self.store.get("trials", "trial_id", "trial_001")
        log = json.loads(Path(response["evaluation_log_path"]).read_text())

        self.assertEqual(response["status"], TrialStatus.FAILED.value)
        self.assertEqual(trial["status"], TrialStatus.FAILED.value)
        self.assertEqual(log["mode"], "real")
        self.assertIn("command", log)
        self.assertNotEqual(log["returncode"], 0)

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

    def _create_uploaded_trial(
        self,
        trial_id: str,
        artifact_path: Path,
        trial_index: int = 1,
    ) -> None:
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": "sess_001",
                "trial_index": trial_index,
                "status": TrialStatus.UPLOADED.value,
                "requested_params": {
                    "bitrate_kbps": 4000,
                    "i_frame_interval_sec": 2,
                    "profile": "baseline",
                },
                "applied_params": {
                    "bitrate_kbps": 4000,
                    "i_frame_interval_sec": 2,
                },
                "applied_params_unknown": ["profile"],
                "artifact_path": str(artifact_path),
                "search_space_version": 1,
            },
        )

    def _write_artifact(self, trial_id: str, content: bytes) -> Path:
        trial_directory = self.root / "sess_001" / "trials" / trial_id
        trial_directory.mkdir(parents=True, exist_ok=True)
        artifact_path = trial_directory / "output.h264"
        artifact_path.write_bytes(content)
        return artifact_path


if __name__ == "__main__":
    unittest.main()
