import json
from pathlib import Path

from config_file_preparation.Locator_functions import (
    load_image_and_normalise,
    rotate_image,
    visualize_features_with_matplotlib,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PATH_TO_IMAGE = Path(PROJECT_ROOT, "continuous_capture", "continuous_capture_frame.jpg")
ROI_METADATA_PATH = Path(PROJECT_ROOT, "generated_files", "ROI_manifest.json")
GRATING_LOCATION_IMAGE_PATH = Path(PROJECT_ROOT, "generated_files", "Grating_locations.png")

with ROI_METADATA_PATH.open("r") as f:
    roi_dict = json.load(f)

image_angle = roi_dict.get("image_angle", 0)

grating_list = []
for k, v in roi_dict.items():
    if k == "image_angle":
        continue
    roi_dict[k]["label"] = f"{v.get('label', None)}_flipped:{v.get('flip', None)}"
    roi_dict[k]["grating_origin"] = v.get("coords", None)
    roi_dict[k]["x-size"] = v.get("size", [None, None])[0]
    roi_dict[k]["y-size"] = v.get("size", [None, None])[1]
    grating_list.append(roi_dict[k])

image, error = load_image_and_normalise(PATH_TO_IMAGE)
if error:
    print(error)

rotated_image, error = rotate_image(image, -image_angle)
if error:
    print(error)

_, error = visualize_features_with_matplotlib(
    rotated_image, grating_list, None, GRATING_LOCATION_IMAGE_PATH, key="gratings"
)
if error:
    print(error)

print("----------------------------------------------------------------------")
print("   ROI location file has been created.")
print("   Please check the saved ROI location images before continuing.")
print("   (see 'generated_files' directory)")
print("----------------------------------------------------------------------")
