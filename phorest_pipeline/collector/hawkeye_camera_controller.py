import datetime
import time
from pathlib import Path
import subprocess

import numpy as np
import cv2

from phorest_pipeline.shared.config import (
    CAMERA_GAIN,
    CAMERA_INDEX,
    CAMERA_TRANFORM,
    CAMERA_BRIGHTNESS,
    CAMERA_CONTRAST,
    CAMERA_EXPOSURE,
)
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename='camera.log')

RESOLTION = (9152, 6944)
# CAMERA_BRIGHTNESS = 0 # Range: -1.0 (dark) to 1.0 (bright)


def camera_controller(data_dir: Path, savename: Path = None, resolution: tuple = None) -> tuple[int, str, dict | None]:
    """
    Controls camera using libcamera tools (rpicam-jpeg), captures image,
    saves, returns status and metadata dict.

    Args:
        data_dir (Path): Directory to save the captured image.
        savename (Path, optional): Desired filename for the image. If None,
                                   a timestamped name is generated. Defaults to None.

    Returns:
        tuple[int, str, dict | None]: (status_code, message, metadata_dict)
        status_code: 0 for success, 1 for error.
        message: Status message string.
        metadata_dict: Dictionary with capture details on success, None on failure.
    """
    logger.info('--- Starting Libcamera-based Camera Controller (for Hawkeye) ---')

    filepath = None
    metadata_dict = None
    if resolution:
        global RESOLTION
        RESOLTION = resolution

    # Create a temporary file path for rpicam-jpeg to save its output
    temp_jpeg_path = Path(data_dir, f"temp_capture_{int(time.time())}.jpg")

    try:
        capture_timestamp = datetime.datetime.now()
        
        # --- Build rpicam-jpeg command ---
        rpicam_cmd = [
            'rpicam-jpeg',
            '-c', str(CAMERA_INDEX),                # Camera 0-based ID (should be 0 for single camera)
            '--output', str(temp_jpeg_path),        # Output path for the captured JPEG
            '--nopreview',                          # Don't show preview on capture
            '--width', str(RESOLTION[0]),           # Set image width
            '--height', str(RESOLTION[1]),          # Set image height
            '--gain', str(CAMERA_GAIN),             # Set analog gain
            '--brightness', str(CAMERA_BRIGHTNESS), # Set brightness
            '--contrast', str(CAMERA_CONTRAST),     # Set contrast
            '--shutter', str(CAMERA_EXPOSURE * 1_000_000),   # Set exposure time (microseconds)
            '--vflip',                                       # In camera vertical flip
            '--timeout', '100',                              # Time to wait before capture (e.g., for auto-exposure to settle)
            '--quality', '93',                               # JPEG compression quality (0-100)
            '--info-text', '%md'                             # Include metadata in stderr for diagnostics
        ]

        logger.info(f"Executing libcamera capture command: {' '.join(rpicam_cmd)}")
        
        # --- Execute the command using subprocess ---
        result = subprocess.run(rpicam_cmd, capture_output=True, text=True, check=False)

        if result.stderr:
            logger.info("--- rpicam-jpeg STDERR Output (Diagnostics) ---")
            for line in result.stderr.splitlines():
                logger.info(line)
            logger.info("-------------------------------------------------")
        
        # Check if the rpicam-jpeg command was successful
        if result.returncode != 0:
            error_msg = (
                f"[CAMERA] [ERROR] rpicam-jpeg command failed with exit code {result.returncode}. "
                f"Stderr: {result.stderr.strip()}"
            )
            logger.error(error_msg)
            return (1, error_msg, None)
        
        logger.info('Image capture command executed successfully by rpicam-jpeg.')

        # --- Load the captured JPEG using OpenCV ---
        if not temp_jpeg_path.exists():
            error_msg = f"[CAMERA] [ERROR] Captured JPEG file was not found at {temp_jpeg_path}."
            logger.error(error_msg)
            return (1, error_msg, None)

        # Read the image file using OpenCV
        frame_captured = cv2.imread(str(temp_jpeg_path), cv2.IMREAD_UNCHANGED)
        
        if frame_captured is None:
            error_msg = f"[CAMERA] [ERROR] OpenCV failed to load image from {temp_jpeg_path}. File might be corrupt or empty."
            logger.error(error_msg)
            return (1, error_msg, None)

        logger.info(f'Frame loaded from JPEG. Shape: {frame_captured.shape}, dtype: {frame_captured.dtype}')

        # --- Convert to Grayscale (if needed) ---
        frame_gray_intermediate = None
        if len(frame_captured.shape) == 3 and frame_captured.shape[2] == 3:
            logger.info('Converting color frame (from JPEG) to grayscale...')
            frame_gray_intermediate = cv2.cvtColor(frame_captured, cv2.COLOR_BGR2GRAY)
        elif len(frame_captured.shape) == 2: # Already grayscale (e.g., if camera is monochrome or JPEG was grayscale)
            logger.info('Frame is already single channel (assuming grayscale from JPEG).')
            frame_gray_intermediate = frame_captured
        else:
            logger.warning(
                f'Unexpected frame shape {frame_captured.shape}. Attempting conversion assuming BGR source.'
            )
            try:
                frame_gray_intermediate = cv2.cvtColor(frame_captured, cv2.COLOR_BGR2GRAY)
            except cv2.error as cvt_err:
                error_msg = f'[CAMERA] [ERROR] Cannot convert frame shape {frame_captured.shape} to grayscale: {cvt_err}'
                return (1, error_msg, None)

        # --- Convert to 8-bit (if needed) ---
        frame_gray_8bit = None
        logger.info('Converting to 8-bit grayscale (target dtype: uint8)...')
        if frame_gray_intermediate.dtype == np.uint8:
            logger.info('Frame is already 8-bit.')
            frame_gray_8bit = frame_gray_intermediate
        else:
            source_dtype = frame_gray_intermediate.dtype
            logger.info(f'Frame is {source_dtype}, using cv2.normalize to scale to 8-bit...')
            try:
                frame_gray_8bit = cv2.normalize(
                    frame_gray_intermediate,
                    None,  # type: ignore (output array)
                    0,
                    255,
                    cv2.NORM_MINMAX,
                    dtype=cv2.CV_8U,
                )
                logger.info('Normalization successful.')
            except cv2.error as norm_err:
                error_msg = f'[CAMERA] [ERROR] Failed to normalize frame with dtype {source_dtype}: {norm_err}'
                return (1, error_msg, None)

        logger.info('Processed frame details:')
        logger.info(f'      Shape: {frame_gray_8bit.shape}')
        logger.info(f'      dtype: {frame_gray_8bit.dtype}')
        logger.info(f'      Min/Max value: {frame_gray_8bit.min()}/{frame_gray_8bit.max()}')
        if frame_gray_8bit.max() == 0:
            logger.info('[WARN] Captured frame all black (max pixel value is 0)! Check lighting/exposure.')

        # --- Apply Image Transform ---
        logger.info(f'Applying image transform: {CAMERA_TRANFORM}...')
        frame_gray_8bit = CAMERA_TRANFORM.apply_transform(frame_gray_8bit)

        # --- Save the final 8-bit Grayscale Frame ---
        if not savename:
            filename = (
                f'image_{capture_timestamp.strftime("%Y%m%d_%H%M%S_%f")}_cam{CAMERA_INDEX}.png'
            )
        else:
            filename = savename

        filepath = Path(data_dir, filename)
        filepath.parent.mkdir(parents=True, exist_ok=True) # Ensure output directory exists
        logger.info(f'Saving image to {filepath} ...')
        saved = cv2.imwrite(str(filepath), frame_gray_8bit)

        if saved:
            logger.info('Image saved successfully.')
            metadata_dict = {
                'type': 'image',
                'filename': filename,
                'filepath': filepath.parent.resolve().as_posix(), # Absolute path string
                'timestamp_iso': capture_timestamp.isoformat(),
                'camera_index': CAMERA_INDEX,
                'error_flag': False,
                'error_message': None,
            }
            return (
                0,
                f'[CAMERA] Image captured and processed successfully, saved to {filename}.',
                metadata_dict,
            )
        else:
            return (1, f'[CAMERA] [ERROR] Failed to save image to {filepath}.', None)

    except Exception as e:
        error_msg = f'[CAMERA] [ERROR] Unexpected error during camera operation: {e}'
        logger.exception(error_msg)
        return (1, error_msg, None)
    finally:
        # Clean up the temporary JPEG file created by rpicam-jpeg
        if temp_jpeg_path.exists():
            try:
                temp_jpeg_path.unlink()
                logger.info(f"Cleaned up temporary JPEG file: {temp_jpeg_path}")
            except OSError as e:
                logger.warning(f"Failed to remove temporary file {temp_jpeg_path}: {e}")
        logger.info('--- Libcamera-based Camera Controller Done ---')


if __name__ == '__main__':
    # Dummy config and transform for independent testing
    class DummyConfig:
        CAMERA_EXPOSURE = 1000000 # 1 second exposure (example, adjust for your camera/lighting)
        CAMERA_INDEX = 0         # Assuming a single camera connected to the Pi
        
        class DummyTransform:
            def apply_transform(self, image):
                logger.info("Applying dummy CAMERA_TRANFORM (no actual change to image data).")
                # Example: You might add a small border or text for testing
                # cv2.putText(image, "TRANSFORMED", (50,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255), 2, cv2.LINE_AA)
                return image
        
        CAMERA_TRANFORM = DummyTransform()

    # Temporarily override the shared config with dummy values for testing this script directly
    import sys
    sys.modules['phorest_pipeline.shared.config'] = DummyConfig

    # Create a dummy data directory for saving images
    test_data_dir = Path("test_camera_captures")
    test_data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running camera_controller demo with libcamera (rpicam-jpeg)...")
    status, message, metadata = camera_controller(test_data_dir)

    print("\n--- Camera Capture Result ---")
    print(f"Status: {status} ({'SUCCESS' if status == 0 else 'ERROR'})")
    print(f"Message: {message}")
    if metadata:
        print(f"Metadata: {metadata}")
        if status == 0:
            print(f"Image saved to: {Path(metadata['filepath'], metadata['filename'])}")
    print("-----------------------------\n")
