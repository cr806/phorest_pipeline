# src/phorest_pipeline/scripts/single_capture.py
import sys
from pathlib import Path

from phorest_pipeline.shared.config import (
    CAMERA_TYPE,
    CONTINUOUS_DIR,
    ENABLE_CAMERA,
    settings,
)
from phorest_pipeline.shared.image_sources import ImageSourceType
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="single_capture.log")

if ENABLE_CAMERA:
    if CAMERA_TYPE == ImageSourceType.LOGITECH:
        from phorest_pipeline.collector.sources.logi_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.ARGUS:
        from phorest_pipeline.collector.sources.argus_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.TIS:
        from phorest_pipeline.collector.sources.tis_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.HAWKEYE:
        from phorest_pipeline.collector.sources.hawkeye_camera_controller import camera_controller
    elif CAMERA_TYPE == ImageSourceType.DUMMY:
        from phorest_pipeline.collector.sources.dummy_camera_controller import camera_controller
    else:

        def camera_controller(_):
            return (1, "Invalid or no camera type specified for single capture.", None)
else:

    def camera_controller(_):
        return (1, "Camera is not enabled in the configuration.", None)


def main():
    """
    Main entry point for the single image capture utility.
    Captures one image and saves it to the continuous_capture directory.
    """
    logger.info("--- Starting Single Image Capture ---")

    if settings is None:
        logger.error("Configuration error. Halting.")
        sys.exit(1)

    try:
        status, msg, data = camera_controller(
            CONTINUOUS_DIR,
            savename=Path("continuous_capture_frame.jpg"),
        )

        if status == 0:
            filename = data.get("filename", "Unknown file")
            logger.info(f"Successfully captured single image: {filename}")
            print(f"Successfully captured single image: {filename}")
            sys.exit(0)
        else:
            logger.error(f"Failed to capture single image: {msg}")
            print(f"ERROR: {msg}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        logger.critical(f"A fatal error occurred during single capture: {e}", exc_info=True)
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
