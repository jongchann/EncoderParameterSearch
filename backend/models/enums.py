from enum import StrEnum


class SessionStatus(StrEnum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrialStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    UPLOADED = "uploaded"
    EVALUATED = "evaluated"
    FAILED = "failed"
