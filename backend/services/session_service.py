from typing import Any
from uuid import uuid4

from backend.models.enums import SessionStatus, TrialStatus
from backend.services.constraint_filter import ConstraintFilter
from backend.services.optimizer_service import NoRecommendationAvailableError, OptimizerService
from backend.services.search_space_builder import SearchSpaceBuilder
from backend.storage.metadata_store import MetadataStore


class SessionNotFoundError(Exception):
    pass


class SessionNotReadyError(Exception):
    pass


class RecommendationRejectedError(Exception):
    pass


class SessionService:
    def __init__(
        self,
        store: MetadataStore,
        constraint_filter: ConstraintFilter | None = None,
        search_space_builder: SearchSpaceBuilder | None = None,
        optimizer_service: OptimizerService | None = None,
    ) -> None:
        self.store = store
        self.constraint_filter = constraint_filter or ConstraintFilter()
        self.search_space_builder = search_space_builder or SearchSpaceBuilder()
        self.optimizer_service = optimizer_service or OptimizerService(store)

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = f"sess_{uuid4().hex[:12]}"
        values = {
            "session_id": session_id,
            "input_video_id": payload["input_video_id"],
            "target_codec": payload.get("target_codec", "auto"),
            "target_mime": payload["target_mime"],
            "status": SessionStatus.CREATED.value,
        }

        self.store.create("sessions", values)
        return {"session_id": session_id, "status": SessionStatus.CREATED.value}

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.get("sessions", "session_id", session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        return {
            **session,
            "trial_count": self.store.count("trials", "session_id", session_id),
            "evaluated_trial_count": self.store.count_trials_by_status(
                session_id,
                TrialStatus.EVALUATED.value,
            ),
            "failed_trial_count": self.store.count_trials_by_status(
                session_id,
                TrialStatus.FAILED.value,
            ),
            "current_search_space_version": session["search_space_version"],
        }

    def get_constraints(self, session_id: str) -> dict[str, Any]:
        self._require_session(session_id)
        decisions = self.store.list("constraint_decisions", "session_id", session_id)
        return {"session_id": session_id, "constraints": decisions}

    def register_capability(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_session(session_id)
        device_payload = payload["device"]
        codec_payload = payload["codec"]
        raw_payload = payload.get("raw_payload", payload)

        device_id = f"dev_{uuid4().hex[:12]}"
        capability_id = f"cap_{uuid4().hex[:12]}"
        search_space_version = self._next_search_space_version(session_id)

        self.store.create(
            "devices",
            {
                "device_id": device_id,
                "model": device_payload["model"],
                "android_version": device_payload["android_version"],
                "soc_vendor": device_payload.get("soc_vendor", "unknown"),
            },
        )
        self.store.create(
            "capabilities",
            {
                "capability_id": capability_id,
                "device_id": device_id,
                "codec_name": codec_payload["codec_name"],
                "mime_type": codec_payload["mime_type"],
                "profiles": codec_payload.get("profiles", []),
                "bitrate_modes": codec_payload.get("bitrate_modes", []),
                "supports_b_frame": 1 if codec_payload.get("supports_b_frame") else 0,
                "vendor_keys": codec_payload.get("vendor_keys", []),
                "raw_payload": raw_payload,
            },
        )

        search_space = self.search_space_builder.build(codec_payload)
        self.store.create(
            "search_spaces",
            {
                "search_space_version": search_space_version,
                "session_id": session_id,
                "parameters": search_space["parameters"],
                "created_from": search_space["created_from"],
            },
        )

        for decision in self.constraint_filter.build_rejection_decisions(
            session_id,
            codec_payload,
        ):
            self.store.create(
                "constraint_decisions",
                {
                    "decision_id": f"decision_{uuid4().hex[:12]}",
                    **decision,
                },
            )

        self.store.update(
            "sessions",
            "session_id",
            session_id,
            {
                "status": SessionStatus.READY.value,
                "search_space_version": search_space_version,
            },
        )

        return {
            "session_id": session_id,
            "status": SessionStatus.READY.value,
            "device_id": device_id,
            "capability_id": capability_id,
            "search_space_version": search_space_version,
            "search_space": search_space["parameters"],
        }

    def get_next_trial(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if session["status"] == SessionStatus.CREATED.value:
            raise SessionNotReadyError(
                "Capability registration is required before trial generation."
            )
        if session["status"] not in {
            SessionStatus.READY.value,
            SessionStatus.RUNNING.value,
        }:
            raise SessionNotReadyError("Only ready or running sessions can receive trials.")

        try:
            recommendation = self.optimizer_service.recommend_next(session_id)
        except NoRecommendationAvailableError as error:
            raise SessionNotReadyError(str(error)) from error

        search_space = self._active_search_space(session_id, session["search_space_version"])
        if not self.constraint_filter.accepts_recommendation(
            recommendation["recommended_params"],
            search_space["parameters"],
        ):
            self.store.update(
                "optimizer_recommendations",
                "optimizer_trial_id",
                recommendation["optimizer_trial_id"],
                {"status": "rejected"},
            )
            raise RecommendationRejectedError(
                "Optimizer recommendation was rejected by constraints."
            )

        trial_id = f"trial_{uuid4().hex[:12]}"
        self.store.create(
            "trials",
            {
                "trial_id": trial_id,
                "session_id": session_id,
                "trial_index": self.store.count("trials", "session_id", session_id) + 1,
                "status": TrialStatus.ASSIGNED.value,
                "requested_params": recommendation["recommended_params"],
                "applied_params": {},
                "applied_params_unknown": [],
                "optimizer_trial_id": recommendation["optimizer_trial_id"],
                "search_space_version": search_space["search_space_version"],
            },
        )
        self.store.update(
            "optimizer_recommendations",
            "optimizer_trial_id",
            recommendation["optimizer_trial_id"],
            {"trial_id": trial_id},
        )
        self.store.update(
            "sessions",
            "session_id",
            session_id,
            {"status": SessionStatus.RUNNING.value},
        )

        return {
            "trial_id": trial_id,
            "requested_params": recommendation["recommended_params"],
        }

    def _require_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.get("sessions", "session_id", session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def _next_search_space_version(self, session_id: str) -> int:
        return self.store.count("search_spaces", "session_id", session_id) + 1

    def _active_search_space(
        self,
        session_id: str,
        search_space_version: int | None,
    ) -> dict[str, Any]:
        if search_space_version is None:
            raise SessionNotReadyError("Active search space is required.")

        for search_space in self.store.list("search_spaces", "session_id", session_id):
            if search_space["search_space_version"] == search_space_version:
                return search_space

        raise SessionNotReadyError("Active search space was not found.")
