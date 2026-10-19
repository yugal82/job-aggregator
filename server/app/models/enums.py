from enum import Enum


class SourceType(str, Enum):
    OFFICIAL = "official"
    ATS = "ats"
    BOARD = "board"


class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    ACTIVE = "ACTIVE"
    UPDATED = "UPDATED"
    CLOSED = "CLOSED"


class SyncPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SyncRunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
