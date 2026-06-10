from typing import Any


MVP_EXCLUDED_PARAMETERS = {
    "qp_min": "MVP excludes QP controls until codec support is validated.",
    "qp_max": "MVP excludes QP controls until codec support is validated.",
    "b_frame_count": "MVP excludes B-frame controls until codec support is validated.",
    "bitrate_mode": "MVP excludes bitrate mode from the default search space.",
    "vendor_extensions": "MVP excludes vendor extensions from the default search space.",
}


class ConstraintFilter:
    def build_rejection_decisions(
        self,
        session_id: str,
        capability: dict[str, Any],
    ) -> list[dict[str, str]]:
        decisions = [
            {
                "session_id": session_id,
                "parameter_name": parameter_name,
                "decision": "rejected",
                "reason": reason,
                "source_type": "adr_rule",
                "source_ref": "adr_001",
            }
            for parameter_name, reason in MVP_EXCLUDED_PARAMETERS.items()
        ]

        vendor_keys = capability.get("vendor_keys", [])
        for vendor_key in vendor_keys:
            decisions.append(
                {
                    "session_id": session_id,
                    "parameter_name": f"vendor_extensions.{vendor_key}",
                    "decision": "rejected",
                    "reason": "Vendor extension keys are not part of the default MVP search space.",
                    "source_type": "capability",
                    "source_ref": vendor_key,
                }
            )

        if not capability.get("profiles"):
            decisions.append(
                {
                    "session_id": session_id,
                    "parameter_name": "profile",
                    "decision": "rejected",
                    "reason": "Capability payload did not report supported profiles.",
                    "source_type": "capability",
                    "source_ref": "profiles",
                }
            )

        return decisions

    def accepts_recommendation(
        self,
        recommended_params: dict[str, Any],
        search_space_parameters: dict[str, Any],
    ) -> bool:
        for parameter_name, value in recommended_params.items():
            if parameter_name not in search_space_parameters:
                return False

            domain = search_space_parameters[parameter_name]
            domain_type = domain["type"]
            if domain_type in {"integer", "number"}:
                if value < domain["min"] or value > domain["max"]:
                    return False
            elif domain_type == "categorical":
                if value not in domain["values"]:
                    return False
            else:
                return False

        return set(search_space_parameters).issubset(set(recommended_params))
