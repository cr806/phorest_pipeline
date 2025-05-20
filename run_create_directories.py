import os
from pathlib import Path

from phorest_pipeline.shared.logger_config import configure_logger

USB_MOUNT_POINT = Path('/', 'mnt', 'ARGUS_data')
PROJECT_ROOT = Path(__file__).resolve().parent
LOG_FILEPATH = Path(USB_MOUNT_POINT, 'logs', 'directory_setup.log')

logger = configure_logger(name=__name__, rotate_daily=False, log_filename=LOG_FILEPATH, log_to_terminal=True)

DIRECTORIES_TO_CREATE = [
    "continuous_capture",
    "data",
    "flags",
    "generated_files",
    "logs",
    "results"
]


def create_directories(usb_path: Path, directories: list[str]) -> bool:
    """
    Creates a list of directories under a specified USB path.
    """
    logger.info(f"Attempting to create directories at: {usb_path}")
    all_successful = True
    
    if not usb_path.is_dir():
        logger.error(f"USB path '{usb_path}' does not exist or is not a directory.")
        return False

    for directory_name in directories:
        full_path = Path(usb_path, directory_name)
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory created or already exists: {full_path}")
        except OSError as e:
            logger.error(f"Error creating directory '{full_path}': {e}")
            all_successful = False
        except Exception as e:
            logger.error(f"An unexpected error occurred while creating directory '{full_path}': {e}")
            all_successful = False
            
    return all_successful


def create_symlinks_to_usb(usb_path: Path, project_path: Path, directories: list[str]) -> bool:
    """
    Creates symbolic links from project directories to corresponding directories on the USB.
    """
    logger.info(f"Attempting to create symlinks from '{usb_path}' to '{project_path}'")
    all_successful = True

    if not project_path.is_dir():
        logger.error(f"Project root path '{project_path}' does not exist or is not a directory. Cannot create symlinks.")
        return False

    for directory_name in directories:
        source_path = Path(usb_path, directory_name)
        link_path = Path(project_path, directory_name)

        if not source_path.is_dir():
            logger.warning(f"Source directory '{source_path}' does not exist. Skipping symlink creation for this directory.")
            all_successful = False
            continue

        try:
            if link_path.is_symlink():
                if link_path.resolve() == source_path.resolve():
                    logger.info(f"Symlink already exists and is correct: {link_path} -> {source_path}")
                else:
                    logger.warning(f"Existing symlink '{link_path}' points to '{link_path.resolve()}' instead of '{source_path}'. Removing and recreating.")
                    link_path.unlink()
                    os.symlink(source_path, link_path)
                    logger.info(f"Recreated symlink: {link_path} -> {source_path}")
            elif link_path.exists():
                logger.error(f"Cannot create symlink: A file or directory already exists at '{link_path}' and is not a symlink. Please move or delete it manually.")
                all_successful = False
            else:
                os.symlink(source_path, link_path)
                logger.info(f"Symlink created: {link_path} -> {source_path}")
        except OSError as e:
            logger.error(f"Error creating symlink for '{directory_name}': {e}")
            all_successful = False
        except Exception as e:
            logger.error(f"An unexpected error occurred while creating symlink for '{directory_name}': {e}")
            all_successful = False

    return all_successful

if __name__ == "__main__":
    logger.info(f"Project root determined as: {PROJECT_ROOT}")

    # Validate USB_MOUNT_POINT
    if not USB_MOUNT_POINT.is_dir():
        logger.critical(f"ERROR: USB mount point '{USB_MOUNT_POINT}' does not exist or is not a directory. Is the USB drive mounted correctly?")
        logger.info("Please ensure the USB drive is mounted at '/mnt/ARGUS_data' before running this script.")
        exit(1)
    
    # Validate PROJECT_ROOT itself
    if not PROJECT_ROOT.is_dir():
        logger.critical(f"ERROR: Project root directory '{PROJECT_ROOT}' does not exist or is not a directory. Please create it first.")
        exit(1)

    logger.info("Starting directory and symlink setup process.")

    # 1. Create directories on the USB drive
    usb_dir_success = create_directories(USB_MOUNT_POINT, DIRECTORIES_TO_CREATE)

    # 2. Create symlinks in the project directory
    symlink_success = create_symlinks_to_usb(USB_MOUNT_POINT, PROJECT_ROOT, DIRECTORIES_TO_CREATE)

    if usb_dir_success and symlink_success:
        logger.info("Directory and symlink setup completed successfully!")
        exit(0)
    else:
        logger.error("Directory and symlink setup encountered errors.")
        exit(1)