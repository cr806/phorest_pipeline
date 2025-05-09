# src/process_pipeline/shared/cameras.py
from enum import Enum, auto


class CameraType(Enum):
    LOGITECH = auto()
    ARGUS = auto()
    TIS = auto()
    DUMMY = auto()
