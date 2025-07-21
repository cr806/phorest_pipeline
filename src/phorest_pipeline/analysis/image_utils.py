from pathlib import Path

import cv2


def load_template(template_path):
    message = "at function load_template"
    try:
        if not isinstance(template_path, Path):
            raise TypeError("Template path must be a Path object.")
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found at: {template_path}")
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            return (None, f"[ERROR] Error loading template {message}: cv2.imread returned None.")
        return (template, None)
    except FileNotFoundError as e:
        return (None, f"[ERROR] Error loading template {message}: {e}")
    except TypeError as e:
        return (None, f"[ERROR] Error loading template {message}: {e}")
    except cv2.error as e:
        return (None, f"[ERROR] OpenCV error loading template {message}: {e}")
    except Exception as e:
        return (
            None,
            f"[ERROR] An unexpected error occurred while loading the template {message}: {e}",
        )


def load_image_and_normalise(image_path):
    message = "at function load_image_and_normalise"
    try:
        if not isinstance(image_path, Path):
            raise TypeError("Image path must be a path.")
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found at: {image_path}")
        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if image is None:
            return (None, f"[ERROR] Error loading image {message}: cv2.imread returned None.")
        image = cv2.normalize(
            image,
            None,
            0,
            255,
            cv2.NORM_MINMAX,
            dtype=cv2.CV_8U,  # type: ignore
        )
        if len(image.shape) > 2:  # Check if the image has more than one channel
            try:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            except cv2.error as e:
                return (
                    None,
                    f"[ERROR] Error converting image to greyscale {message}: OpenCV error - {e}",
                )
            except Exception as e:
                return (
                    None,
                    f"[ERROR] An unexpected error occurred during greyscale conversion {message}: {e}",
                )
        return (image, None)
    except FileNotFoundError as e:
        return (None, f"[ERROR] Error loading image {message}: {e}")
    except TypeError as e:
        return (None, f"[ERROR] Error loading image {message}: {e}")
    except cv2.error as e:
        return (None, f"[ERROR] Error loading image {message}: OpenCV error - {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred {message}: {e}")