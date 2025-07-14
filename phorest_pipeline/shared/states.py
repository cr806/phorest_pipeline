# src/process_pipeline/shared/states.py
from enum import Enum, auto


class CollectorState(Enum):
    IDLE = auto()
    WAITING_TO_RUN = auto()
    COLLECTING = auto()
    FATAL_ERROR = auto()


class ProcessorState(Enum):
    IDLE = auto()
    WAITING_FOR_DATA = auto()
    PROCESSING = auto()
    FATAL_ERROR = auto()


class CommunicatorState(Enum):
    IDLE = auto()
    WAITING_FOR_RESULTS = auto()
    COMMUNICATING = auto()
    FATAL_ERROR = auto()


class CompressorState(Enum):
    IDLE = auto()
    CHECKING = auto()
    COMPRESSING_IMAGES = auto()
    WAITING_TO_RUN = auto()


class BackupState(Enum):
    IDLE = auto()
    BACKUP_FILES = auto()
    WAITING_TO_RUN = auto()


class SyncerState(Enum):
    IDLE = auto()
    SYNCING_FILES = auto()
    WAITING_TO_RUN = auto()
