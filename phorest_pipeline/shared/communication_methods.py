# src/process_pipeline/shared/cameras.py
from enum import Enum, auto


class CommunicationMethod(Enum):
    CVS_PLOT = auto()
    OPC_UA = auto()
