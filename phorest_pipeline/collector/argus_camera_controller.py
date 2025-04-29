import datetime
import time
from pathlib import Path

import cv2
import numpy as np

from phorest_pipeline.shared.config import (
    CAMERA_BRIGHTNESS,
    CAMERA_INDEX,
)

BUFFER_CLEAR_UP_FRAMES = 5


def camera_controller(data_dir: Path) -> tuple[int, str, dict | None]:
    """
    Controls camera, captures image, saves, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
        status_code: 0 for success, 1 for error.
        message: Status message string.
        metadata_dict: Dictionary with capture details on success, None on failure.
    """
    print('[CAMERA] --- Starting Camera Controller ---')
    cap = None
    filepath = None
    metadata_dict = None

    try:
        print(f'[CAMERA] Opening camera {CAMERA_INDEX}...')
        cap = cv2.VideoCapture(CAMERA_INDEX)

        if not cap.isOpened():
            return (1, f'[CAMERA] [ERROR] Could not open camera at index {CAMERA_INDEX}.', None)
        print(f'[CAMERA] Camera {CAMERA_INDEX} opened.')
        time.sleep(0.1)

        # --- Camera Settings ---
        # 1. Set Brightness: brightness
        success = cap.set(cv2.CAP_PROP_BRIGHTNESS, CAMERA_BRIGHTNESS)
        if not success:
            print(f'[CAMERA] [ERROR] Could not set CAP_PROP_BRIGHTNESS to {CAMERA_BRIGHTNESS}.')
        else:
            current = cap.get(cv2.CAP_PROP_BRIGHTNESS)
            if current != CAMERA_BRIGHTNESS:
                print('[CAMERA] [ERROR] CAP_PROP_BRIGHTNESS not set')

        # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        # time.sleep(0.2) # Allow time for settings to apply
        print('[CAMERA] Camera configuration complete.')

        # --- Clear camera buffer ---
        print(f'[CAMERA] Clearing camera buffer with {BUFFER_CLEAR_UP_FRAMES} captures...')
        for i in range(BUFFER_CLEAR_UP_FRAMES):
            ret, _ = cap.read()  # Read and discard the frame
            if not ret:
                print(f'[CAMERA] [WARN] Warm-up frame {i + 1} capture failed. Continuing...')
                time.sleep(0.5)
            else:
                time.sleep(0.1)
        print('[CAMERA] Warm-up complete.')

        print('[CAMERA] Taking image ...')
        ret, frame_raw = cap.read()  # Read the frame
        frame_raw = frame_raw.astype(np.uint16)
        frame_raw = np.bitwise_and(frame_raw, 0x0FFF)
        capture_timestamp = datetime.datetime.now()

        if not ret or frame_raw is None:
            return (1, '[CAMERA] [ERROR] Failed to capture frame.', None)
        else:
            original_dtype = str(frame_raw.dtype)
            print(
                f'[CAMERA] Raw frame captured. Shape: {frame_raw.shape}, dtype: {original_dtype}'
            )

            # --- Convert to Grayscale (if needed) ---
            if (
                len(frame_raw.shape) == 3 and frame_raw.shape[2] == 3
            ):  # Check if it's a 3-channel image (like BGR)
                print('[CAMERA] Converting color frame to grayscale...')
                frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
            elif len(frame_raw.shape) == 2:  # Already grayscale (or single channel)
                print('[CAMERA] Frame is already single channel (assuming grayscale).')
                frame_gray_intermediate = frame_raw
            else:
                # Handle other unexpected formats (e.g., 4 channels, YUV) - basic approach:
                print(
                    f'[CAMERA] [WARN] Unexpected frame shape {frame_raw.shape}. Attempting conversion assuming BGR source.'
                )
                try:
                    frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
                except cv2.error as cvt_err:
                    error_msg = f'[CAMERA] [ERROR] Cannot convert frame shape {frame_raw.shape} to grayscale: {cvt_err}'
                    return (1, error_msg, None)

            # --- Convert to 8-bit ---
            frame_gray_8bit = None
            print('[CAMERA] Converting to 8-bit grayscale (target dtype: uint8)...')
            if frame_gray_intermediate.dtype == np.uint8:
                print('[CAMERA] Frame is already 8-bit.')
                frame_gray_8bit = frame_gray_intermediate
            else:
                source_dtype = frame_gray_intermediate.dtype
                print(
                    f'[CAMERA] Frame is {source_dtype}, using cv2.normalize to scale to 8-bit...'
                )
                try:
                    frame_gray_8bit = cv2.normalize(
                        frame_gray_intermediate,
                        None,  # type: ignore
                        0,
                        255,
                        cv2.NORM_MINMAX,
                        dtype=cv2.CV_8U,
                    )
                    print('[CAMERA] Normalization successful.')
                except cv2.error as norm_err:
                    error_msg = f'[CAMERA] [ERROR] Failed to normalize frame with dtype {source_dtype}: {norm_err}'
                    return (1, error_msg, None)
            # --- End normalization ---

            print('[CAMERA] Frame captured.')
            print(f'      Shape: {frame_gray_8bit.shape}')
            print(f'      dtype: {frame_gray_8bit.dtype}')
            print(f'      Min/Max value: {frame_gray_8bit.min()}/{frame_gray_8bit.max()}')
            if frame_gray_8bit.max() == 0:
                print('[CAMERA] [WARN] Captured frame all black (max pixel value is 0)!')

            # --- Save the 8-bit Grayscale Frame ---
            filename = (
                f'image_{capture_timestamp.strftime("%Y%m%d_%H%M%S_%f")}_cam{CAMERA_INDEX}.png'
            )
            filepath = Path(data_dir, filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)  # Ensure data_dir exists

            print(f'[CAMERA] Saving image to {filepath} ...')
            saved = cv2.imwrite(str(filepath), frame_gray_8bit)  # Use original BGR frame

            if saved:
                print('[CAMERA] Image saved.')
                metadata_dict = {
                    'type': 'image',
                    'filename': filename,
                    'filepath': filepath.parent.resolve().as_posix(),
                    'timestamp_iso': capture_timestamp.isoformat(),
                    'camera_index': CAMERA_INDEX,
                    'error_flag': False,
                    'error_message': None,
                }
                return (
                    0,
                    f'[CAMERA] Image captured successfully and saved to {filename}.',
                    metadata_dict,
                )
            else:
                return (1, f'[CAMERA] [ERROR] Failed to save image to {filepath}.', None)

    except Exception as e:
        return (1, f'[CAMERA] [ERROR] Unexpected error: {e}', None)
    finally:
        if cap is not None and cap.isOpened():
            cap.release()
            print(f'[CAMERA] Camera {CAMERA_INDEX} released.')
        print('[CAMERA] --- Camera Controller Done ---')
