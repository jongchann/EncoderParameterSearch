from typing import Literal, TypedDict


class HealthResponse(TypedDict):
    status: Literal["ok"]


def health_check() -> HealthResponse:
    return {"status": "ok"}
