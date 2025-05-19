import shutil
import sys
from pathlib import Path

from config_file_preparation.generate_ROI_JSON import generate_ROI_JSON


ROOT_PATH =      '.'
PATH_TO_IMAGES = './continuous_capture'
IMAGE_TYPE =     'jpg'
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

print('##############################################')
print('Have you updated the filepaths in this script?')
print('##############################################')

# 1. Confirm root, image, ROI, and server_root variables
print('\nThese locations will be used:')
print(f'\t{"Root folder:":<30} {ROOT_PATH}')
print(f'\t{"Image folder:":<30} {PATH_TO_IMAGES}')
print(f'\t{"Image type:":<30} {IMAGE_TYPE}')
print(f'\t{"ROI metadata name:":<30} {ROI_METADATA_NAME}')
input('Press Enter to continue...')

# 2. Generate ROI metadata and save plots of ROI locations
# Make sure directory exists for generated files
Path('Generated_files').mkdir(parents=True, exist_ok=True)
if Path('Generated_files', 'ImageFeatures.csv').exists():
    Path('Generated_files', 'ImageFeatures.csv').unlink()
print('\nStep 1: Generating ROI metadata...')
generate_ROI_JSON(
    Path(PATH_TO_IMAGES, f'{IMAGE_NAME_FOR_ROI_PLOTS}.{IMAGE_TYPE}'),
    Path(f'{ROI_METADATA_NAME}.json'),
)

# 3. Confirm ROI locations
print('\nStep 2: Please check the saved ROI location plots.')
roi_correct = input('\tAre the ROI locations correct? (y/n): ').lower()
if roi_correct != 'y':
    print('\nROI locations not confirmed. Please adjust and rerun. Exiting.')
    sys.exit(1)


# 4. Back-up generated files to location of experiment
print('\nStep 3: Backing-up all generated files to experiment directory...')
dest_path = Path(ROOT_PATH, 'Image_analysis_files_BACKUP')
dest_path.mkdir(parents=True, exist_ok=True)
files_src_dest_name = []
src_path = Path('Generated_files')
for entry in src_path.iterdir():
    if not entry.is_file():
        continue
    files_src_dest_name.append((src_path, dest_path, entry.name))

src_path = Path('config')
for entry in src_path.iterdir():
    if not entry.is_file():
        continue
    files_src_dest_name.append((src_path, dest_path, entry.name))

if not move_files(files_src_dest_name):
    print('\nFailed to move some/all metadata files. Exiting.')
    sys.exit(1)
