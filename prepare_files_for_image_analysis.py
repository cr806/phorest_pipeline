import shutil
from pathlib import Path

from config_file_preparation.generate_ROI_JSON import generate_ROI_JSON

PATH_TO_IMAGES = './continuous_capture'
IMAGE_TYPE = 'jpg'
IMAGE_NAME_FOR_ROI_PLOTS = 'continuous_capture_frame'
ROI_METADATA_NAME = 'ROI_manifest.json'


def move_files(files_src_dest_name):
    """
    Copy a file from src_path to dest_path.

    Args:
        files_src_dest_name (list(tuple)): List containging tuples with src_path,
                                           dest_path, and filename

    Returns:
        bool: True if the copy succeeded, False otherwise.
    """

    message = []
    success = True
    for src_path, dest_path, name in files_src_dest_name:
        try:
            shutil.copy(Path(src_path, name), Path(dest_path, name))
            message.append(
                f"Successfully copied '{Path(src_path, name)}' to '{Path(dest_path, name)}'."
            )
        except PermissionError:
            message.append(
                f"[ERROR]: Permission denied while copying '{Path(src_path, name)}' to '{Path(dest_path, name)}'."
            )
            success = False
        except shutil.SameFileError:
            message.append(
                f"[ERROR]: Source and destination are the same file: '{Path(src_path, name)}'."
            )
            success = False
        except Exception as e:
            message.append(
                f"[ERROR]: Failed to copy '{Path(src_path, name)}' to '{Path(dest_path, name)}': {e}"
            )
            success = False
    print('\n')
    print('\n'.join(message))
    return success


# 1. Confirm root, image, ROI, and server_root variables
print('\nThese locations will be used:')
print(f'\t{"Image folder:":<30} {PATH_TO_IMAGES}')
print(f'\t{"Image type:":<30} {IMAGE_TYPE}')
print(f'\t{"ROI metadata name:":<30} {ROI_METADATA_NAME}')
input('Press Enter to continue...')

# 2. Generate ROI metadata and save plots of ROI locations
print('\nGenerating ROI metadata (this may take a few seconds)...')
generate_ROI_JSON(
    Path(PATH_TO_IMAGES, f'{IMAGE_NAME_FOR_ROI_PLOTS}.{IMAGE_TYPE}'),
    Path(f'{ROI_METADATA_NAME}'),
)

# 3. Confirm generated files with user
print(
    '\nROI location file has been created, please check the saved ROI location plots before continuing.'
)
