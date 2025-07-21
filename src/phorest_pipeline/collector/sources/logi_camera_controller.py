import datetime
import time
from pathlib import Path

import cv2
import numpy as np

from phorest_pipeline.collector.continuous_capture_logic import RESOLUTION
from phorest_pipeline.shared.config import (
    CAMERA_BRIGHTNESS,
    CAMERA_CONTRAST,
    CAMERA_EXPOSURE,
    CAMERA_INDEX,
    CAMERA_TRANFORM,
)
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='data_source.log')

BUFFER_CLEAR_UP_FRAMES = 5
RESOLUTION = (640, 480)

GAIN_VALUE = 32  # Low value to reduce noise


def camera_controller(data_dir: Path, savename: Path = None, resolution: tuple = None) -> tuple[int, str, dict | None]:
    """
    Controls camera, captures image, saves, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
        status_code: 0 for success, 1 for error.
        message: Status message string.
        metadata_dict: Dictionary with capture details on success, None on failure.
    """
    logger.info('[CAMERA] --- Starting Logitech Camera Controller ---')
    cap = None
    filepath = None
    metadata_dict = None

    if resolution:
        global RESOLUTION
        RESOLUTION = resolution

    try:
        logger.info(f'[CAMERA] Opening camera {CAMERA_INDEX}...')
        cap = cv2.VideoCapture(CAMERA_INDEX)

        if not cap.isOpened():
            return (1, f'[CAMERA] [ERROR] Could not open camera at index {CAMERA_INDEX}.', None)
        logger.info(f'[CAMERA] Camera {CAMERA_INDEX} opened.')
        time.sleep(0.1)

        # --- Camera Settings ---
        logger.info('[CAMERA] Configuring camera settings...')
        # 0. Set resolution and image format
        logger.info('[CAMERA] Attempting to set resolution')
        success = cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
        success = success and cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
        if not success:
            logger.error(f'[CAMERA] Failed to set the RESOLUTION to: {RESOLUTION[0]}x{RESOLUTION[1]}')
        else:
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            if width != RESOLUTION[0] or height != RESOLUTION[1]:
                logger.error(f'[CAMERA] Camera resolution not set correctly: {width}x{height}')
        logger.info('[CAMERA] Camera resolution set')

        # 1. Disable Auto Exposure
        success = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        if not success:
            logger.error('[CAMERA] Could not set CAP_PROP_AUTO_EXPOSURE to manual')
        else:
            current = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
            if current != 1:
                logger.error('[CAMERA] Auto exposure mode not set')
        # 2. Disable Auto White Balance
        success = cap.set(cv2.CAP_PROP_AUTO_WB, 0)
        if not success:
            logger.error('[CAMERA] Could not disable CAP_PROP_AUTO_WB')
        else:
            # Set fixed White Balance Temperature: white_balance_temperature
            wb_temp_default = 4000
            success = cap.set(cv2.CAP_PROP_WB_TEMPERATURE, wb_temp_default)
            if not success:
                logger.error(f'[CAMERA] Could not set CAP_PROP_WB_TEMPERATURE to {wb_temp_default}.')
            else:
                current = cap.get(cv2.CAP_PROP_WB_TEMPERATURE)
                if current != wb_temp_default:
                    logger.error('[CAMERA] CAP_PROP_WB_TEMPERATURE not set')
        # 3. Set fixed Gain: gain
        success = cap.set(cv2.CAP_PROP_GAIN, GAIN_VALUE)
        if not success:
            logger.error(f'[CAMERA] Could not set CAP_PROP_GAIN to {GAIN_VALUE}.')
        else:
            current = cap.get(cv2.CAP_PROP_GAIN)
            if current != GAIN_VALUE:
                logger.error('[CAMERA] CAP_PROP_GAIN not set')

        # 4. Set Exposure: exposure
        success = cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)
        if not success:
            logger.error(f'[CAMERA] Could not set CAP_PROP_EXPOSURE to {CAMERA_EXPOSURE}.')
        else:
            current = cap.get(cv2.CAP_PROP_EXPOSURE)
            if current != CAMERA_EXPOSURE:
                logger.error('[CAMERA] CAP_PROP_EXPOSURE not set')

        # 5. Set Brightness: brightness
        success = cap.set(cv2.CAP_PROP_BRIGHTNESS, CAMERA_BRIGHTNESS)
        if not success:
            logger.error(f'[CAMERA] Could not set CAP_PROP_BRIGHTNESS to {CAMERA_BRIGHTNESS}.')
        else:
            current = cap.get(cv2.CAP_PROP_BRIGHTNESS)
            if current != CAMERA_BRIGHTNESS:
                logger.error('[CAMERA] CAP_PROP_BRIGHTNESS not set')

        # 6. Set Contrast: contrast
        success = cap.set(cv2.CAP_PROP_CONTRAST, CAMERA_CONTRAST)
        if not success:
            logger.error(f'[CAMERA] Could not set CAP_PROP_CONTRAST to {CAMERA_CONTRAST}.')
        else:
            current = cap.get(cv2.CAP_PROP_CONTRAST)
            if current != CAMERA_CONTRAST:
                logger.error('[CAMERA] CAP_PROP_CONTRAST not set')

        # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        # time.sleep(0.2) # Allow time for settings to apply
        logger.info('[CAMERA] Camera configuration complete.')

        # --- Clear camera buffer ---
        logger.info(f'[CAMERA] Clearing camera buffer with {BUFFER_CLEAR_UP_FRAMES} captures...')
        for i in range(BUFFER_CLEAR_UP_FRAMES):
            ret, _ = cap.read()  # Read and discard the frame
            if not ret:
                logger.warning(f'[CAMERA] Warm-up frame {i + 1} capture failed. Continuing...')
                time.sleep(0.5)
            else:
                time.sleep(0.1)
        logger.info('[CAMERA] Warm-up complete.')

        logger.info('[CAMERA] Taking image ...')
        ret, frame_raw = cap.read()  # Read the frame (BGR format)
        capture_timestamp = datetime.datetime.now()

        if not ret or frame_raw is None:
            return (1, '[CAMERA] [ERROR] Failed to capture frame.', None)
        else:
            original_dtype = str(frame_raw.dtype)
            logger.info(f'[CAMERA] Raw frame captured. Shape: {frame_raw.shape}, dtype: {original_dtype}')

            # --- Convert to Grayscale (if needed) ---
            if (
                len(frame_raw.shape) == 3 and frame_raw.shape[2] == 3
            ):  # Check if it's a 3-channel image (like BGR)
                logger.info('[CAMERA] Converting color frame to grayscale...')
                frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
            elif len(frame_raw.shape) == 2:  # Already grayscale (or single channel)
                logger.info('[CAMERA] Frame is already single channel (assuming grayscale).')
                frame_gray_intermediate = frame_raw
            else:
                # Handle other unexpected formats (e.g., 4 channels, YUV) - basic approach:
                logger.warning(
                    f'[CAMERA] Unexpected frame shape {frame_raw.shape}. Attempting conversion assuming BGR source.'
                )
                try:
                    frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
                except cv2.error as cvt_err:
                    error_msg = f'[CAMERA] [ERROR] Cannot convert frame shape {frame_raw.shape} to grayscale: {cvt_err}'
                    return (1, error_msg, None)

            # --- Convert to 8-bit ---
            frame_gray_8bit = None
            logger.info('[CAMERA] Converting to 8-bit grayscale (target dtype: uint8)...')
            if frame_gray_intermediate.dtype == np.uint8:
                logger.info('[CAMERA] Frame is already 8-bit.')
                frame_gray_8bit = frame_gray_intermediate
            else:
                source_dtype = frame_gray_intermediate.dtype
                logger.info(f'[CAMERA] Frame is {source_dtype}, using cv2.normalize to scale to 8-bit...')
                try:
                    frame_gray_8bit = cv2.normalize(
                        frame_gray_intermediate,
                        None,  # type: ignore
                        0,
                        255,
                        cv2.NORM_MINMAX,
                        dtype=cv2.CV_8U,
                    )
                    logger.info('[CAMERA] Normalization successful.')
                except cv2.error as norm_err:
                    error_msg = f'[CAMERA] [ERROR] Failed to normalize frame with dtype {source_dtype}: {norm_err}'
                    return (1, error_msg, None)
            # --- End normalization ---

            logger.info('[CAMERA] Frame captured.')
            logger.info(f'      Shape: {frame_gray_8bit.shape}')
            logger.info(f'      dtype: {frame_gray_8bit.dtype}')
            logger.info(f'      Min/Max value: {frame_gray_8bit.min()}/{frame_gray_8bit.max()}')
            if frame_gray_8bit.max() == 0:
                logger.info('[CAMERA] [WARN] Captured frame all black (max pixel value is 0)!')

            # --- Apply Image Transform ---
            logger.info(f'[CAMERA] Applying image transform: {CAMERA_TRANFORM}...')
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

            logger.info(f'[CAMERA] Saving image to {filepath} ...')
            saved = cv2.imwrite(str(filepath), frame_gray_8bit)  # Use original BGR frame

            if saved:
                logger.info('[CAMERA] Image saved.')
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
            logger.info(f'[CAMERA] Camera {CAMERA_INDEX} released.')
        logger.info('[CAMERA] --- Camera Controller Done ---')
