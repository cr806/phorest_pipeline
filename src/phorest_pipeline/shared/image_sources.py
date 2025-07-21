# src/process_pipeline/shared/iamge_sources.py
from enum import Enum, auto

import cv2


class ImageSourceType(Enum):
    LOGITECH = auto()
    ARGUS = auto()
    TIS = auto()
    HAWKEYE = auto()
    DUMMY = auto()
    FILE_IMPORTER = auto()


class ImageTransform(Enum):
    NONE = 0
    HORIZONTAL_FLIP = 1
    VERTICAL_FLIP = 2
    ROTATE_90_CLOCKWISE = 3
    ROTATE_90_COUNTERCLOCKWISE = 4
    ROTATE_180 = 5

    def apply_transform(self, image):
        if self == ImageTransform.HORIZONTAL_FLIP:
            return cv2.flip(image, 1)
        elif self == ImageTransform.VERTICAL_FLIP:
            return cv2.flip(image, 0)
        elif self == ImageTransform.ROTATE_90_CLOCKWISE:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif self == ImageTransform.ROTATE_90_COUNTERCLOCKWISE:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif self == ImageTransform.ROTATE_180:
            return cv2.rotate(image, cv2.ROTATE_180)
        else:
            return image
