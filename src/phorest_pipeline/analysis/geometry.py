import math

import cv2
import numpy as np


def angle_between_points(v1, v2):
    """Calculates the signed angle in degrees between the line connecting two vectors
    and the positive x-axis.

    Args:
        v1: (x1, y1)
        v2: (x2, y2)

    Returns:
        Angle in degrees, positive for counter-clockwise rotation from the
        positive x-axis to the line segment from point1 to point2.
    """
    x1, y1 = v1
    x2, y2 = v2

    dx = x2 - x1
    dy = y2 - y1

    return math.degrees(math.atan2(dy, dx))  # Angle relative to positive x-axis


def calculate_distance(v1, v2):
    """Calculates the Euclidean distance between two points in 2D space.

    Args:
      v1: A tuple or list representing the first point (x1, y1).
      v1: A tuple or list representing the second point (x2, y2).

    Returns:
      The Euclidean distance between the two points.
    """
    x1, y1 = v1
    x2, y2 = v2

    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def rotate_image(image, rotation_angle):
    message = "at function rotate_image"
    if not isinstance(image, np.ndarray):
        return (None, f"[ERROR] Input 'image' must be a NumPy array {message}.")
    if not isinstance(rotation_angle, (int, float)):
        return (None, f"[ERROR] Input 'rotation_angle' must be a number {message}.")

    try:
        # Calculate the center of rotation
        h, w = image.shape[:2]  # Handle both grayscale and color images
        center = (w / 2, h / 2)

        # Get the rotation matrix
        rotation_matrix = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)

        # Apply the rotation
        rotated_image = cv2.warpAffine(image, rotation_matrix, (w, h))

        return (rotated_image, None)
    except cv2.error as e:
        return (None, f"[ERROR] OpenCV error during image rotation {message}: {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during image rotation {message}: {e}")
