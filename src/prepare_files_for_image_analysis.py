# from pathlib import Path

# from config_file_preparation.generate_ROI_JSON import generate_ROI_JSON
from scripts.generate_roi_manifest import generate_roi_manifest

# PROJECT_ROOT = Path(__file__).resolve().parent.parent
# PATH_TO_IMAGES = Path(PROJECT_ROOT, "continuous_capture")
# IMAGE_NAME_FOR_ROI_PLOTS = Path("continuous_capture_frame.jpg")
# ROI_METADATA_NAME = Path("ROI_manifest.json")


# 1. Confirm root, image, ROI, and server_root variables
# print("\nThese locations will be used:")
# print(f"\t{'Image folder:':<30} {PATH_TO_IMAGES.as_posix()}")
# print(f"\t{'Image type:':<30} {IMAGE_NAME_FOR_ROI_PLOTS.suffix}")
# print(f"\t{'ROI metadata name:':<30} {ROI_METADATA_NAME.as_posix()}")

# 2. Generate ROI metadata and save plots of ROI locations
print("\nGenerating ROI metadata (this may take a few seconds)...")
generate_roi_manifest()
# generate_ROI_JSON(
#     Path(PATH_TO_IMAGES, IMAGE_NAME_FOR_ROI_PLOTS),
#     Path(ROI_METADATA_NAME),
# )

# 3. Confirm generated files with user
print("----------------------------------------------------------------------")
print("   ROI location file has been created.")
print("   Please check the saved ROI location images before continuing.")
print("   (see 'generated_files' directory)")
print("----------------------------------------------------------------------")
