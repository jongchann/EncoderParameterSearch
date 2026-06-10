import subprocess
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from backend.models.enums import TrialStatus
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class EvaluationError(Exception):
    pass


class TrialNotEvaluableError(Exception):
    pass


class Evaluator(Protocol):
    def evaluate(self, artifact_path: Path, trial: dict[str, Any]) -> dict[str, Any]:
        pass


class MockEvaluator:
    def evaluate(self, artifact_path: Path, trial: dict[str, Any]) -> dict[str, Any]:
        bitrate_kbps = self._bitrate_from_trial(trial, artifact_path)
        vmaf = max(60.0, min(99.0, 82.0 + bitrate_kbps / 1200.0))
        return {
            "bitrate_kbps": round(bitrate_kbps, 3),
            "vmaf": round(vmaf, 3),
            "log": {
                "mode": "mock",
                "artifact_size_bytes": artifact_path.stat().st_size,
            },
        }

    def _bitrate_from_trial(self, trial: dict[str, Any], artifact_path: Path) -> float:
        applied_bitrate = trial["applied_params"].get("bitrate_kbps")
        requested_bitrate = trial["requested_params"].get("bitrate_kbps")
        if applied_bitrate is not None:
            return float(applied_bitrate)
        if requested_bitrate is not None:
            return float(requested_bitrate)
        return float(artifact_path.stat().st_size * 8)


class RealEvaluator:
    def __init__(
        self,
        reference_video_path: Path,
        ffmpeg_binary: str = "ffmpeg",
    ) -> None:
        self.reference_video_path = reference_video_path
        self.ffmpeg_binary = ffmpeg_binary

    def evaluate(self, artifact_path: Path, trial: dict[str, Any]) -> dict[str, Any]:
        command = [
            self.ffmpeg_binary,
            "-i",
            str(artifact_path),
            "-i",
            str(self.reference_video_path),
            "-lavfi",
            "libvmaf",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise EvaluationError(
                {
                    "mode": "real",
                    "command": command,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": str(error),
                }
            ) from error
        log = {
            "mode": "real",
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if completed.returncode != 0:
            raise EvaluationError(log)

        raise EvaluationError({**log, "detail": "Real VMAF parsing is not implemented."})


class EvaluationService:
    def __init__(
        self,
        store: MetadataStore,
        artifact_store: ArtifactStore,
        evaluator: Evaluator,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.evaluator = evaluator

    def evaluate_trial(self, session_id: str, trial_id: str) -> dict[str, Any]:
        trial = self._require_trial(session_id, trial_id)
        artifact_path = Path(trial["artifact_path"] or "")

        if not artifact_path.exists():
            return self._record_evaluation_failure(
                session_id,
                trial_id,
                trial,
                {
                    "mode": "missing_artifact",
                    "artifact_path": str(artifact_path),
                    "error": "Uploaded artifact does not exist.",
                },
            )

        try:
            result = self.evaluator.evaluate(artifact_path, trial)
        except EvaluationError as error:
            detail = error.args[0] if error.args else {"error": "Evaluation failed."}
            if not isinstance(detail, dict):
                detail = {"error": str(detail)}
            return self._record_evaluation_failure(session_id, trial_id, trial, detail)

        evaluation_log_path = self.artifact_store.save_evaluation_log(
            session_id,
            trial_id,
            result["log"],
        )
        observation_id = f"obs_{uuid4().hex[:12]}"
        self.store.create(
            "observations",
            {
                "observation_id": observation_id,
                "trial_id": trial_id,
                "bitrate_kbps": result["bitrate_kbps"],
                "vmaf": result["vmaf"],
                "evaluation_log_path": str(evaluation_log_path),
                "is_baseline": 0,
            },
        )
        self.store.update(
            "trials",
            "trial_id",
            trial_id,
            {"status": TrialStatus.EVALUATED.value},
        )
        if trial.get("optimizer_trial_id"):
            self.store.update(
                "optimizer_recommendations",
                "optimizer_trial_id",
                trial["optimizer_trial_id"],
                {"status": "evaluated"},
            )

        return {
            "trial_id": trial_id,
            "status": TrialStatus.EVALUATED.value,
            "observation_id": observation_id,
            "bitrate_kbps": result["bitrate_kbps"],
            "vmaf": result["vmaf"],
            "evaluation_log_path": str(evaluation_log_path),
        }

    def _record_evaluation_failure(
        self,
        session_id: str,
        trial_id: str,
        trial: dict[str, Any],
        log: dict[str, Any],
    ) -> dict[str, Any]:
        log_path = self.artifact_store.save_evaluation_log(session_id, trial_id, log)
        self.store.update(
            "trials",
            "trial_id",
            trial_id,
            {
                "status": TrialStatus.FAILED.value,
                "error_code": "EVALUATION_FAILED",
                "error_message": str(log.get("error") or log.get("stderr") or "Evaluation failed."),
            },
        )
        if trial.get("optimizer_trial_id"):
            self.store.update(
                "optimizer_recommendations",
                "optimizer_trial_id",
                trial["optimizer_trial_id"],
                {"status": "failed"},
            )

        return {
            "trial_id": trial_id,
            "status": TrialStatus.FAILED.value,
            "evaluation_log_path": str(log_path),
        }

    def _require_trial(self, session_id: str, trial_id: str) -> dict[str, Any]:
        trial = self.store.get("trials", "trial_id", trial_id)
        if trial is None or trial["session_id"] != session_id:
            raise TrialNotEvaluableError(trial_id)
        return trial
