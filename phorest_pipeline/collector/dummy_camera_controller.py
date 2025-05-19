import datetime
from pathlib import Path

import cv2
import numpy as np

from phorest_pipeline.shared.cameras import CameraTransform
from phorest_pipeline.shared.config import CAMERA_TRANFORM

DUMMY_IMAGE_PATH = Path('phorest_pipeline/collector/dummy_image.tif')


def camera_controller(data_dir: Path, savename: Path = None) -> tuple[int, str, dict | None]:
    """
    Dummy camera controller, copies dummy image, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
        status_code: 0 for success, 1 for error.
        message: Status message string.
        metadata_dict: Dictionary with capture details on success, None on failure.
    """
    print('[CAMERA] --- Starting Dummy Camera Controller ---')
    filepath = None
    metadata_dict = None

    try:
        print('[CAMERA] Loading image ...')
        frame_raw = cv2.imread(DUMMY_IMAGE_PATH.as_posix(), cv2.IMREAD_UNCHANGED)
        capture_timestamp = datetime.datetime.now()

        if frame_raw is None:
            return (1, '[CAMERA] [ERROR] Failed to load image.', None)
        else:
            original_dtype = str(frame_raw.dtype)
            print(
                f'[CAMERA] Raw image loaded. Shape: {frame_raw.shape}, dtype: {original_dtype}'
            )

            # --- Convert to Grayscale (if needed) ---
            if (
                len(frame_raw.shape) == 3 and frame_raw.shape[2] == 3
            ):  # Check if it's a 3-channel image (like BGR)
                print('[CAMERA] Converting color image to grayscale...')
                frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
            elif len(frame_raw.shape) == 2:  # Already grayscale (or single channel)
                print('[CAMERA] Image is already single channel (assuming grayscale).')
                frame_gray_intermediate = frame_raw
            else:
                # Handle other unexpected formats (e.g., 4 channels, YUV) - basic approach:
                print(
                    f'[CAMERA] [WARN] Unexpected image shape {frame_raw.shape}. Attempting conversion assuming BGR source.'
                )
                try:
                    frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
                except cv2.error as cvt_err:
                    error_msg = f'[CAMERA] [ERROR] Cannot convert image shape {frame_raw.shape} to grayscale: {cvt_err}'
                    return (1, error_msg, None)

            # --- Convert to 8-bit ---
            frame_gray_8bit = None
            print('[CAMERA] Converting to 8-bit grayscale (target dtype: uint8)...')
            if frame_gray_intermediate.dtype == np.uint8:
                print('[CAMERA] Image is already 8-bit.')
                frame_gray_8bit = frame_gray_intermediate
            else:
                source_dtype = frame_gray_intermediate.dtype
                print(
                    f'[CAMERA] Image is {source_dtype}, using cv2.normalize to scale to 8-bit...'
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
                    error_msg = f'[CAMERA] [ERROR] Failed to normalize image with dtype {source_dtype}: {norm_err}'
                    return (1, error_msg, None)
            # --- End normalization ---

            print('[CAMERA] Image loaded.')
            print(f'      Shape: {frame_gray_8bit.shape}')
            print(f'      dtype: {frame_gray_8bit.dtype}')
            print(f'      Min/Max value: {frame_gray_8bit.min()}/{frame_gray_8bit.max()}')
            if frame_gray_8bit.max() == 0:
                print('[CAMERA] [WARN] Loaded image all black (max pixel value is 0)!')

            # --- Apply Image Transform ---
            print(f'[CAMERA] Applying image transform: {CAMERA_TRANFORM}...')
            frame_gray_8bit = CAMERA_TRANFORM.apply_transform(frame_gray_8bit)

            # --- Save the 8-bit Grayscale Frame ---
            if not savename:
                filename = (
                    f'image_{capture_timestamp.strftime("%Y%m%d_%H%M%S_%f")}_cam{CAMERA_INDEX}.png'
                )
            else:
                filename = savename
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
                    'camera_index': 'DUMMY',
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
        print('[CAMERA] --- Camera Controller Done ---')
