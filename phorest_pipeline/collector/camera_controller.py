import datetime
import time
from pathlib import Path

import cv2

from phorest_pipeline.collector.camera_config import CAMERA_INDEX

NUM_WARMUP_FRAMES = 2


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
            return (1,
                    f'[CAMERA] [ERROR] Could not open camera at index {CAMERA_INDEX}.',
                    None)
        print(f'[CAMERA] Camera {CAMERA_INDEX} opened.')
        time.sleep(0.1)

        # Set other parameters here
        # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        # time.sleep(0.2) # Allow time for settings to apply

        # --- Camera Warm-up ---
        print(f'[CAMERA] Performing {NUM_WARMUP_FRAMES} warm-up captures...')
        for i in range(NUM_WARMUP_FRAMES):
            ret_warmup, _ = cap.read()  # Read and discard the frame
            if not ret_warmup:
                print(f'[CAMERA] [WARN] Warm-up frame {i + 1} capture failed. Continuing...')
                time.sleep(0.5)
            else:
                time.sleep(0.1)
        print('[CAMERA] Warm-up complete.')

        print('[CAMERA] Taking image ...')
        ret, frame = cap.read()  # Read the frame (BGR format)
        capture_timestamp = datetime.datetime.now()

        if not ret or frame is None:
            return (1,
                    '[CAMERA] [ERROR] Failed to capture frame.',
                    None)
        else:
            print('[CAMERA] Frame captured.')
            print(f'      Shape: {frame.shape}')
            print(f'      dtype: {frame.dtype}')
            print(f'      Min/Max value: {frame.min()}/{frame.max()}')
            if frame.max() == 0:
                print('[CAMERA] [WARN] Captured frame all black (max pixel value is 0)!')

            filename = (
                f'image_{capture_timestamp.strftime("%Y%m%d_%H%M%S_%f")}_cam{CAMERA_INDEX}.png'
            )
            filepath = Path(data_dir, filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)  # Ensure data_dir exists

            print(f'[CAMERA] Saving image to {filepath} ...')
            saved = cv2.imwrite(str(filepath), frame)  # Use original BGR frame

            if saved:
                print('[CAMERA] Image saved.')
                metadata_dict = {
                    'type': 'image',
                    'filename': filename,
                    'filepath_relative': str(
                        filepath.relative_to(filepath.parent.parent)
                    ),
                    'timestamp_iso': capture_timestamp.isoformat(),
                    'camera_index': CAMERA_INDEX,
                    'error_flag': False,
                    'error_message': None,
                }
                return (0,
                        f'[CAMERA] Image captured successfully and saved to {filename}.',
                        metadata_dict)
            else:
                return (1,
                        f'[CAMERA] [ERROR] Failed to save image to {filepath}.',
                        None)

    except Exception as e:
        return (1,
                f'[CAMERA] [ERROR] Unexpected error: {e}',
                None)
    finally:
        if cap is not None and cap.isOpened():
            cap.release()
            print(f'[CAMERA] Camera {CAMERA_INDEX} released.')
        print('[CAMERA] --- Camera Controller Done ---')
