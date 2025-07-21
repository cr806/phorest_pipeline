import json
import subprocess
import time
from pathlib import Path

from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(
    name=__name__, rotate_daily=False, log_filename='storage_check.log', log_to_terminal=True
)

EXPECTED_USB_UUID = 'BB92-0AA4'
MOUNT_POINT = Path('/', 'mnt', 'ARGUS_data')
TEST_FILE_NAME = Path('.usb_health_check_temp')


def check_usb_mount_and_permissions(
    mount_point: Path, test_file_name: Path, expected_uuid: str
) -> bool:
    """
    Checks if the specified USB drive (by UUID) is detected, mounted at the correct location,
    and if read/write permissions are correct.
    """
    logger.info(
        f'Starting USB health check for mount point: {mount_point} with UUID: {expected_uuid}'
    )

    # 1. Check if the expected USB device (by UUID) is even present and active
    try:
        lsblk_cmd = ['lsblk', '-J', '-o', 'NAME,UUID,MOUNTPOINT']
        result = subprocess.run(lsblk_cmd, capture_output=True, text=True, check=True)

        lsblk_data = json.loads(result.stdout)

        usb_detected = False
        actual_mountpoint = None

        for block in lsblk_data.get('blockdevices', []):
            for child in block.get('children', []):
                if child.get('uuid') == expected_uuid:
                    usb_detected = True
                    actual_mountpoint = child.get('mountpoint')
                    break

        if not usb_detected:
            logger.error(f"USB drive with UUID '{expected_uuid}' not detected by lsblk.")
            return False
        else:
            logger.info(f"USB drive with UUID '{expected_uuid}' detected.")
            if actual_mountpoint is None:
                logger.info(
                    f"USB drive with UUID '{expected_uuid}' is detected but not currently mounted according to lsblk."
                )
    except FileNotFoundError:
        logger.error("[ERROR] 'lsblk' command not found. Please ensure 'util-linux' is installed.")
        return False
    except json.JSONDecodeError:
        logger.error("[ERROR] Could not parse 'lsblk -J' output. Is the output valid JSON?")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"[ERROR] Error executing 'lsblk': {e.stderr.strip()}")
        return False
    except Exception as e:
        logger.error(f'[ERROR] An unexpected error occurred during lsblk check: {e}')
        return False

    # 2. Check if the mount point exists and is a directory
    if not mount_point.exists():
        logger.error(f"Mount point '{mount_point}' does not exist.")
        return False

    if not mount_point.is_dir():
        logger.error(f"Mount point '{mount_point}' is not a directory.")
        return False

    # 3. Check if a filesystem is actually mounted at the mount point
    try:
        result = subprocess.run(
            ['findmnt', '-n', '-o', 'TARGET', mount_point.as_posix()],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0 or result.stdout.strip() != mount_point.as_posix():
            logger.error(
                f"No filesystem mounted at '{mount_point}' or mount point mismatch (findmnt check failed)."
            )
            if usb_detected and actual_mountpoint != mount_point:
                logger.warning(
                    f"USB detected, but mounted elsewhere ({actual_mountpoint}) or not at all, instead of '{mount_point}'."
                )
            return False

        logger.info(f'Filesystem confirmed to be mounted at: {mount_point} (via findmnt).')
    except FileNotFoundError:
        logger.error(
            "[ERROR] 'findmnt' command not found. Please ensure 'util-linux' is installed."
        )
        return False
    except Exception as e:
        logger.error(f'[ERROR] An unexpected error occurred while checking mount status: {e}')
        return False

    # 4. Check read/write permissions by creating and deleting a file
    test_file_path = Path(mount_point, test_file_name)

    try:
        with test_file_path.open('w') as f:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            f.write(f'Health check ran at {timestamp}\n')
        logger.info(f'Successfully created test file: {test_file_path}')

        test_file_path.unlink()
        logger.info(f'Successfully deleted test file: {test_file_path}')

        logger.info(
            f"USB drive at '{mount_point}' is mounted and has correct read/write permissions."
        )
        return True
    except PermissionError:
        logger.error(
            f"[ERROR] Permission denied: Cannot write to or delete from '{mount_point}'. "
            f'        Check ownership and permissions.'
        )
        return False
    except OSError as e:
        logger.error(
            f"[ERROR] Operating System error while testing permissions on '{mount_point}': {e}"
        )
        return False
    except Exception as e:
        logger.error(f'[ERROR] An unexpected error occurred during permission test: {e}')
        return False


if __name__ == '__main__':
    if check_usb_mount_and_permissions(MOUNT_POINT, TEST_FILE_NAME, EXPECTED_USB_UUID):
        logger.info('USB health check PASSED!')
        exit(0)
    else:
        logger.error('USB health check FAILED!')
        exit(1)
