from itertools import product
from typing import Any
from uuid import uuid4

from backend.models.enums import TrialStatus
from backend.storage.metadata_store import MetadataStore


DEFAULT_SEED = 42


class NoRecommendationAvailableError(Exception):
    pass


class OptimizerService:
    def __init__(self, store: MetadataStore, seed: int = DEFAULT_SEED) -> None:
        self.store = store
        self.seed = seed

    def recommend_next(self, session_id: str) -> dict[str, Any]:
        search_space = self._active_search_space(session_id)
        candidates = self._candidate_params(search_space["parameters"])
        used_params = self._used_parameter_keys(session_id)

        for candidate in candidates:
            if self._params_key(candidate) not in used_params:
                optimizer_trial_id = f"opt_{uuid4().hex[:12]}"
                metadata = {
                    "phase": "cold_start",
                    "seed": self.seed,
                    "search_space_version": search_space["search_space_version"],
                }
                self.store.create(
                    "optimizer_recommendations",
                    {
                        "optimizer_trial_id": optimizer_trial_id,
                        "session_id": session_id,
                        "search_space_version": search_space["search_space_version"],
                        "recommended_params": candidate,
                        "status": "accepted",
                        "metadata": metadata,
                    },
                )
                return {
                    "optimizer_trial_id": optimizer_trial_id,
                    "recommended_params": candidate,
                    "metadata": metadata,
                }

        raise NoRecommendationAvailableError("No unused recommendation is available.")

    def _active_search_space(self, session_id: str) -> dict[str, Any]:
        session = self.store.get("sessions", "session_id", session_id)
        if session is None or session["search_space_version"] is None:
            raise NoRecommendationAvailableError("Active search space is required.")

        search_spaces = self.store.list("search_spaces", "session_id", session_id)
        for search_space in search_spaces:
            if search_space["search_space_version"] == session["search_space_version"]:
                return search_space

        raise NoRecommendationAvailableError("Active search space was not found.")

    def _candidate_params(self, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        bitrates = self._sample_numeric(parameters["bitrate_kbps"], integer=True)
        intervals = self._sample_numeric(parameters["i_frame_interval_sec"], integer=False)
        profiles = parameters.get("profile", {}).get("values", [None])

        candidates = []
        for bitrate, interval, profile in product(bitrates, intervals, profiles):
            candidate: dict[str, Any] = {
                "bitrate_kbps": bitrate,
                "i_frame_interval_sec": interval,
            }
            if profile is not None:
                candidate["profile"] = profile
            candidates.append(candidate)

        return self._broad_first_order(candidates, bitrates, intervals)

    def _sample_numeric(self, domain: dict[str, Any], integer: bool) -> list[int | float]:
        minimum = domain["min"]
        maximum = domain["max"]
        midpoint = (minimum + maximum) / 2
        values: list[int | float] = [minimum, midpoint, maximum]
        if integer:
            values = [int(round(value)) for value in values]
        return list(dict.fromkeys(values))

    def _broad_first_order(
        self,
        candidates: list[dict[str, Any]],
        bitrates: list[int | float],
        intervals: list[int | float],
    ) -> list[dict[str, Any]]:
        preferred_points = [
            (bitrates[0], intervals[0]),
            (bitrates[-1], intervals[-1]),
            (bitrates[len(bitrates) // 2], intervals[len(intervals) // 2]),
            (bitrates[0], intervals[-1]),
            (bitrates[-1], intervals[0]),
        ]
        ordered: list[dict[str, Any]] = []

        for bitrate, interval in preferred_points:
            ordered.extend(
                candidate
                for candidate in candidates
                if candidate["bitrate_kbps"] == bitrate
                and candidate["i_frame_interval_sec"] == interval
            )

        ordered.extend(candidate for candidate in candidates if candidate not in ordered)
        return ordered

    def _used_parameter_keys(self, session_id: str) -> set[str]:
        used = {
            self._params_key(recommendation["recommended_params"])
            for recommendation in self.store.list(
                "optimizer_recommendations",
                "session_id",
                session_id,
            )
        }

        for trial in self.store.list("trials", "session_id", session_id):
            if trial["status"] == TrialStatus.FAILED.value:
                used.add(self._params_key(trial["requested_params"]))

        for trial in self.store.list_trials_with_observations(session_id):
            used.add(self._params_key(trial["requested_params"]))

        return used

    def _params_key(self, params: dict[str, Any]) -> str:
        return "|".join(f"{key}={params[key]}" for key in sorted(params))
