# src/process_pipeline/shared/communication_methods.py
from enum import Enum, auto


class CommunicationMethod(Enum):
    CVS_PLOT = auto()
    OPC_UA = auto()
