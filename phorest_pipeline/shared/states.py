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


class CommunicatorState(Enum):
    IDLE = auto()
    WAITING_FOR_RESULTS = auto()
    COMMUNICATING = auto()


class CompressorState(Enum):
    IDLE = 'IDLE'
    CHECKING = 'CHECKING'
    COMPRESSING = 'COMPRESSING'
    WAITING = 'WAITING'
