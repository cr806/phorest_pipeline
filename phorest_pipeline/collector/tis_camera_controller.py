import datetime
import time
from pathlib import Path

import cv2
import numpy as np

from phorest_pipeline.shared.config import (
    CAMERA_TRANFORM,
    CAMERA_EXPOSURE,
    CAMERA_INDEX,
)
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='camera.log')

BUFFER_CLEAR_UP_FRAMES = 5

RESOLTION = (4000, 3000)
IMAGE_FORMAT = 'GREY'
GAIN_VALUE = 32  # Low value to reduce noise
CAMERA_BRIGHTNESS = 500


def camera_controller(data_dir: Path, savename: Path = None) -> tuple[int, str, dict | None]:
    """
    Controls camera, captures image, saves, returns status and metadata dict.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
        status_code: 0 for success, 1 for error.
        message: Status message string.
        metadata_dict: Dictionary with capture details on success, None on failure.
    """
    logger.info('--- Starting Argus Camera Controller ---')

    cap = None
    filepath = None
    metadata_dict = None

    try:
        logger.info(f'Opening camera {CAMERA_INDEX}...')
        cap = cv2.VideoCapture(CAMERA_INDEX)
        
        if not cap.isOpened():
            retry_count = 0
            while not cap.isOpened() and retry_count < 5:
                logger.warning(f'Camera {CAMERA_INDEX} not opened. Retrying...')
                time.sleep(0.5)
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if cap.isOpened():
                    break
                retry_count += 1
            if not cap.isOpened():
                return (1, f'[CAMERA] [ERROR] Could not open camera at index {CAMERA_INDEX}.', None)
        logger.info(f'Camera {CAMERA_INDEX} opened.')
        time.sleep(0.1)

        # --- Camera Settings ---
        # 0. Set resolution and image format
        logger.info('Attempting to set resolution')
        success = cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLTION[0])
        success = success and cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLTION[1])
        if not success:
            logger.error(f'Failed to set the RESOLUTION to: {RESOLTION[0]}x{RESOLTION[1]}')
        else:
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            if width != RESOLTION[0] or height != RESOLTION[1]:
                logger.error(f'Camera resolution not set correctly: {width}x{height}')
        logger.info('Camera resolution set')
        
        logger.info('Attempting to set image format')
        fourcc = cv2.VideoWriter_fourcc(*IMAGE_FORMAT)
        success = cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        if not success:
            logger.error(f'Failed to set the IMAGE_FORMAT to: {IMAGE_FORMAT}')
        else:
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            fourcc_str = (
                chr((fourcc & 0xFF))
                + chr((fourcc >> 8) & 0xFF)
                + chr((fourcc >> 16) & 0xFF)
                + chr((fourcc >> 24) & 0xFF)
            )

            if fourcc_str != IMAGE_FORMAT:
                logger.error(f'Camera image format not set correctly: {fourcc_str}')
        logger.info('Camera image format set')

        logger.info('Attempting to set camera auto exposure to manual')
        success = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        if not success:
            return (1, f'[CAMERA] [ERROR] Could not set CAP_PROP_AUTO_EXPOSURE to manual', None)
        else:
            current = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
            if current != 1:
                return (1, f'[CAMERA] [ERROR] Could not set CAP_PROP_AUTO_EXPOSURE to manual', None)
        logger.info('Camera auto exposure set to manual')
        
        # 1. Set Brightness: brightness
        success = cap.set(cv2.CAP_PROP_BRIGHTNESS, CAMERA_BRIGHTNESS)
        if not success:
            logger.error(f'Could not set CAP_PROP_BRIGHTNESS to {CAMERA_BRIGHTNESS}.')
        else:
            current = cap.get(cv2.CAP_PROP_BRIGHTNESS)
            if current != CAMERA_BRIGHTNESS:
                logger.error('CAP_PROP_BRIGHTNESS not set')
        
        # 2. Set fixed Gain: gain
        success = cap.set(cv2.CAP_PROP_GAIN, GAIN_VALUE)
        if not success:
            logger.error(f'Could not set CAP_PROP_GAIN to {GAIN_VALUE}.')
        else:
            current = cap.get(cv2.CAP_PROP_GAIN)
            if current != GAIN_VALUE:
                logger.error('CAP_PROP_GAIN not set')

        logger.info('Camera configuration complete.')

        # 3. Set Exposure: exposure
        success = cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)
        if not success:
            logger.error(f'Could not set CAP_PROP_EXPOSURE to {CAMERA_EXPOSURE}.')
        else:
            current = cap.get(cv2.CAP_PROP_EXPOSURE)
            if current != CAMERA_EXPOSURE:
                logger.error('CAP_PROP_EXPOSURE not set')

        # --- Clear camera buffer ---
        logger.info(f'Clearing camera buffer with {BUFFER_CLEAR_UP_FRAMES} captures...')
        for i in range(BUFFER_CLEAR_UP_FRAMES):
            ret, _ = cap.read()  # Read and discard the frame
            if not ret:
                logger.warning(f'Warm-up frame {i + 1} capture failed. Continuing...')
                time.sleep(0.5)
            else:
                time.sleep(0.1)
        logger.info('Warm-up complete.')

        logger.info('Taking image ...')
        ret, frame_raw = cap.read()  # Read the frame
        frame_raw = frame_raw.astype(np.uint16)
        frame_raw = np.bitwise_and(frame_raw, 0x0FFF)
        capture_timestamp = datetime.datetime.now()

        if not ret or frame_raw is None:
            return (1, '[CAMERA] [ERROR] Failed to capture frame.', None)
        else:
            original_dtype = str(frame_raw.dtype)
            logger.info(
                f'Raw frame captured. Shape: {frame_raw.shape}, dtype: {original_dtype}'
            )

            # --- Convert to Grayscale (if needed) ---
            if (
                len(frame_raw.shape) == 3 and frame_raw.shape[2] == 3
            ):  # Check if it's a 3-channel image (like BGR)
                logger.info('Converting color frame to grayscale...')
                frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
            elif len(frame_raw.shape) == 2:  # Already grayscale (or single channel)
                logger.info('Frame is already single channel (assuming grayscale).')
                frame_gray_intermediate = frame_raw
            else:
                # Handle other unexpected formats (e.g., 4 channels, YUV) - basic approach:
                logger.warning(
                    f'Unexpected frame shape {frame_raw.shape}. Attempting conversion assuming BGR source.'
                )
                try:
                    frame_gray_intermediate = cv2.cvtColor(frame_raw, cv2.COLOR_BGR2GRAY)
                except cv2.error as cvt_err:
                    error_msg = f'[CAMERA] [ERROR] Cannot convert frame shape {frame_raw.shape} to grayscale: {cvt_err}'
                    return (1, error_msg, None)

            # --- Convert to 8-bit ---
            frame_gray_8bit = None
            logger.info('Converting to 8-bit grayscale (target dtype: uint8)...')
            if frame_gray_intermediate.dtype == np.uint8:
                logger.info('Frame is already 8-bit.')
                frame_gray_8bit = frame_gray_intermediate
            else:
                source_dtype = frame_gray_intermediate.dtype
                logger.info(
                    f'Frame is {source_dtype}, using cv2.normalize to scale to 8-bit...'
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
                    logger.info('Normalization successful.')
                except cv2.error as norm_err:
                    error_msg = f'[CAMERA] [ERROR] Failed to normalize frame with dtype {source_dtype}: {norm_err}'
                    return (1, error_msg, None)
            # --- End normalization ---

            logger.info('Frame captured.')
            logger.info(f'      Shape: {frame_gray_8bit.shape}')
            logger.info(f'      dtype: {frame_gray_8bit.dtype}')
            logger.info(f'      Min/Max value: {frame_gray_8bit.min()}/{frame_gray_8bit.max()}')
            if frame_gray_8bit.max() == 0:
                logger.info('[WARN] Captured frame all black (max pixel value is 0)!')

            # --- Apply Image Transform ---
            logger.info(f'Applying image transform: {CAMERA_TRANFORM}...')
            frame_gray_8bit = CAMERA_TRANFORM.apply_transform(frame_gray_8bit)

            # --- Save the 8-bit Grayscale Frame ---
            if not savename:
                filename = (
                    f'image_{capture_timestamp.strftime("%Y%m%d_%H%M%S_%f")}_cam{CAMERA_INDEX}.png'
                )
            else:
                filename = savename
            
            filepath = Path(data_dir, filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f'Saving image to {filepath} ...')
            saved = cv2.imwrite(str(filepath), frame_gray_8bit)  # Use original BGR frame

            if saved:
                logger.info('Image saved.')
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
            logger.info(f'Camera {CAMERA_INDEX} released.')
        logger.info('--- Camera Controller Done ---')
