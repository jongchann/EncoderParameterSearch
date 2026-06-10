from typing import Any

from backend.models.enums import TrialStatus
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class TrialNotFoundError(Exception):
    pass


class TrialService:
    def __init__(self, store: MetadataStore, artifact_store: ArtifactStore) -> None:
        self.store = store
        self.artifact_store = artifact_store

    def upload_result(
        self,
        session_id: str,
        trial_id: str,
        metadata: dict[str, Any],
        artifact_bytes: bytes,
    ) -> dict[str, Any]:
        trial = self._require_trial(session_id, trial_id)
        applied_params = metadata["applied_params"]
        applied_params_unknown = metadata.get("applied_params_unknown", [])
        encoder_log = metadata.get("encoder_log", {})

        artifact_path = self.artifact_store.save_trial_result(
            session_id=session_id,
            trial_id=trial_id,
            artifact_bytes=artifact_bytes,
            requested_params=trial["requested_params"],
            applied_params=applied_params,
            encoder_log=encoder_log,
        )

        self.store.update(
            "trials",
            "trial_id",
            trial_id,
            {
                "status": TrialStatus.UPLOADED.value,
                "applied_params": applied_params,
                "applied_params_unknown": applied_params_unknown,
                "artifact_path": str(artifact_path),
            },
        )

        return {
            "trial_id": trial_id,
            "status": TrialStatus.UPLOADED.value,
            "artifact_path": str(artifact_path),
        }

    def mark_failure(
        self,
        session_id: str,
        trial_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        trial = self._require_trial(session_id, trial_id)

        self.store.update(
            "trials",
            "trial_id",
            trial_id,
            {
                "status": TrialStatus.FAILED.value,
                "error_code": payload["error_code"],
                "error_message": payload["error_message"],
            },
        )
        if trial.get("optimizer_trial_id"):
            self.store.update(
                "optimizer_recommendations",
                "optimizer_trial_id",
                trial["optimizer_trial_id"],
                {"status": "failed"},
            )

        return {"trial_id": trial_id, "status": TrialStatus.FAILED.value}

    def _require_trial(self, session_id: str, trial_id: str) -> dict[str, Any]:
        trial = self.store.get("trials", "trial_id", trial_id)
        if trial is None or trial["session_id"] != session_id:
            raise TrialNotFoundError(trial_id)
        return trial
