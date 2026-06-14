from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.models.enums import SessionStatus, TrialStatus
from backend.storage.metadata_store import MetadataStore


class BaselineSelectionError(Exception):
    pass


MIN_COMPLETION_EVALUATED_TRIALS = 15


class BaselineService:
    def __init__(self, store: MetadataStore) -> None:
        self.store = store

    def select_baseline(self, session_id: str) -> dict[str, Any]:
        session = self.store.get("sessions", "session_id", session_id)
        if session is None:
            raise BaselineSelectionError("Session not found.")

        observations = self.store.list_observations_for_session(session_id)
        if not observations:
            raise BaselineSelectionError("At least one evaluated observation is required.")

        selected, reason = self._select_observation(session, observations)
        self._mark_baseline(session_id, selected["trial_id"], selected["observation_id"])
        self._store_selection_reason(session_id, selected["trial_id"], reason)

        return {
            "session_id": session_id,
            "baseline_trial_id": selected["trial_id"],
            "baseline_observation_id": selected["observation_id"],
            "reason": reason,
        }

    def complete_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.get("sessions", "session_id", session_id)
        if session is None:
            raise BaselineSelectionError("Session not found.")
        if session["baseline_trial_id"] is None:
            raise BaselineSelectionError("Baseline observation is required before completion.")

        observations = self.store.list_observations_for_session(session_id)
        if not any(
            observation["trial_id"] == session["baseline_trial_id"]
            and observation["is_baseline"] == 1
            for observation in observations
        ):
            raise BaselineSelectionError("Baseline observation is required before completion.")

        evaluated_count = self.store.count_trials_by_status(
            session_id,
            TrialStatus.EVALUATED.value,
        )
        if evaluated_count < MIN_COMPLETION_EVALUATED_TRIALS:
            raise BaselineSelectionError(
                f"At least {MIN_COMPLETION_EVALUATED_TRIALS} evaluated trials are required "
                "before completion."
            )
        if not self._has_final_report(session_id):
            raise BaselineSelectionError("Final report is required before completion.")

        completed_at = datetime.now(timezone.utc).isoformat()
        self.store.update(
            "sessions",
            "session_id",
            session_id,
            {
                "status": SessionStatus.COMPLETED.value,
                "completed_at": completed_at,
            },
        )
        return {
            "session_id": session_id,
            "status": SessionStatus.COMPLETED.value,
            "completed_at": completed_at,
        }

    def _select_observation(
        self,
        session: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], str]:
        for observation in sorted(observations, key=lambda item: item["created_at"]):
            requested_params = observation["requested_params"]
            if requested_params.get("preset") == "android_default" or requested_params.get(
                "is_default"
            ):
                return observation, "Selected first Android default encoder settings trial."

        center_bitrate = self._center_bitrate(session)
        cold_start_observations = [
            observation
            for observation in observations
            if observation.get("optimizer_metadata", {}).get("phase") == "cold_start"
        ]
        candidates = cold_start_observations or observations
        selected = min(
            candidates,
            key=lambda observation: abs(observation["bitrate_kbps"] - center_bitrate),
        )
        return selected, "Selected evaluated cold-start trial closest to center bitrate."

    def _center_bitrate(self, session: dict[str, Any]) -> float:
        version = session["search_space_version"]
        for search_space in self.store.list("search_spaces", "session_id", session["session_id"]):
            if search_space["search_space_version"] == version:
                bitrate_domain = search_space["parameters"]["bitrate_kbps"]
                return (bitrate_domain["min"] + bitrate_domain["max"]) / 2
        return 6500.0

    def _mark_baseline(
        self,
        session_id: str,
        trial_id: str,
        observation_id: str,
    ) -> None:
        for observation in self.store.list_observations_for_session(session_id):
            self.store.update(
                "observations",
                "observation_id",
                observation["observation_id"],
                {"is_baseline": 1 if observation["observation_id"] == observation_id else 0},
            )
        self.store.update(
            "sessions",
            "session_id",
            session_id,
            {"baseline_trial_id": trial_id},
        )

    def _store_selection_reason(
        self,
        session_id: str,
        trial_id: str,
        reason: str,
    ) -> None:
        self.store.create(
            "report_metadata",
            {
                "report_id": f"baseline_{uuid4().hex[:12]}",
                "session_id": session_id,
                "report_path": "",
                "metadata": {
                    "type": "baseline_selection",
                    "baseline_trial_id": trial_id,
                    "reason": reason,
                },
            },
        )

    def _has_final_report(self, session_id: str) -> bool:
        return any(
            report["metadata"].get("type") == "final_report"
            for report in self.store.list("report_metadata", "session_id", session_id)
        )
