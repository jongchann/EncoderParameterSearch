from typing import Any


class SearchSpaceBuilder:
    def build(self, capability: dict[str, Any]) -> dict[str, Any]:
        profiles = list(capability.get("profiles", []))
        parameters: dict[str, Any] = {
            "bitrate_kbps": {"type": "integer", "min": 1000, "max": 12000},
            "i_frame_interval_sec": {"type": "number", "min": 1, "max": 5},
        }

        if profiles:
            parameters["profile"] = {
                "type": "categorical",
                "values": profiles,
            }

        return {
            "parameters": parameters,
            "created_from": ["adr_rule", "capability"],
        }
