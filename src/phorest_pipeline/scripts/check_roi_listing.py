import json
import sys
from pathlib import Path

from phorest_pipeline.analysis.geometry import rotate_image
from phorest_pipeline.analysis.image_utils import load_image_and_normalise
from phorest_pipeline.analysis.visualise import visualize_features_with_matplotlib
from phorest_pipeline.shared.config import (
    GENERATED_FILES_DIR,
    ROI_GENERATION_IMAGE_PATH,
    ROI_MANIFEST_FILENAME,
)


def main():
    """
    Loads the generated ROI manifest, processes it to create a grating list,
    and visualizes the grating locations on the rotated reference image.
    """
    print("Checking ROI manifest and generating visualization...")

    roi_metadata_path = Path(GENERATED_FILES_DIR, ROI_MANIFEST_FILENAME)
    grating_location_image_path = Path(GENERATED_FILES_DIR, "Grating_locations.png")

    try:
        with roi_metadata_path.open("r") as f:
            roi_dict = json.load(f)

        image_angle = roi_dict.get("image_angle", 0)

        grating_list = []
        for k, v in roi_dict.items():
            if k == "image_angle":
                continue
            grating_item = v.copy() # Avoid modifying the dict while iterating
            grating_item["label"] = f"{v.get('label', None)}_flipped:{v.get('flip', None)}"
            grating_item["grating_origin"] = [v.get("coords", [None, None])[1], v.get("coords", [None, None])[0]]
            grating_item["x-size"] = v.get("size", [None, None])[1]
            grating_item["y-size"] = v.get("size", [None, None])[0]
            grating_list.append(grating_item)

        image, error = load_image_and_normalise(ROI_GENERATION_IMAGE_PATH)
        if error:
            raise RuntimeError(error)

        rotated_image, error = rotate_image(image, -image_angle)
        if error:
            raise RuntimeError(error)

        _, error = visualize_features_with_matplotlib(
            rotated_image, grating_list, None, grating_location_image_path, key="gratings"
        )
        if error:
            raise RuntimeError(error)

        print("----------------------------------------------------------------------")
        print("   ROI location file has been created.")
        print("   Please check the saved ROI location images before continuing.")
        print("   (see 'generated_files' directory)")
        print("----------------------------------------------------------------------")

    except Exception as e:
        print(f"\n[ERROR] Failed to check ROI manifest: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()