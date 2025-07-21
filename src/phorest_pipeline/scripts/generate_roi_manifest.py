# scripts/generate_roi_manifest.py
import sys
from pathlib import Path

from phorest_pipeline.analysis.file_utils import create_directory_with_error_handling
from phorest_pipeline.analysis.geometry import rotate_image
from phorest_pipeline.analysis.image_utils import load_image_and_normalise
from phorest_pipeline.analysis.io import (
    create_ROI_JSON,
    load_and_offset_grating_data,
    load_chip_feature_locations,
    load_user_feature_locations,
    save_json,
)
from phorest_pipeline.analysis.matching import (
    calculate_chip_offset,
    chip_rotation_angle,
    refine_feature_locations,
    user_chip_scale_factor,
)
from phorest_pipeline.analysis.visualise import visualize_features_with_matplotlib
from phorest_pipeline.shared.config import (
    FEATURE_LOCATIONS_CONFIG_PATH,
    GENERATED_FILES_DIR,
    LABEL_TEMPLATE_DIR,
    ROI_GENERATION_IMAGE_PATH,
    ROI_MANIFEST_FILENAME,
)
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(
    name=__name__, rotate_daily=True, log_filename="generate_ROI_manifest.log"
)


def main():
    """
    This script locates features on a reference image and generates the
    ROI_manifest.json needed for processing.
    """
    print("\nGenerating ROI metadata (this may take a few seconds)...")

    try:
        # --- 1. Define paths ---
        output_path = Path(GENERATED_FILES_DIR, ROI_MANIFEST_FILENAME)
        chip_location_json = Path(LABEL_TEMPLATE_DIR, "Chip_map.json")
        calculated_image_feature_path = Path(GENERATED_FILES_DIR, "CalculatedImageFeatures.json")
        grating_locations_image_path = Path(GENERATED_FILES_DIR, "Grating_locations.png")
        label_locations_image_path = Path(GENERATED_FILES_DIR, "Label_locations.png")

        # --- 2. Setup and load initial data ---
        _, error = create_directory_with_error_handling(GENERATED_FILES_DIR)
        if error:
            raise RuntimeError(f"Directory setup failed: {error}")

        image, error = load_image_and_normalise(ROI_GENERATION_IMAGE_PATH)
        if error:
            raise RuntimeError(f"Image loading failed: {error}")

        user_chip_mapping, error = load_user_feature_locations(FEATURE_LOCATIONS_CONFIG_PATH)
        if error:
            raise RuntimeError(f"Loading user features failed: {error}")

        user_chip_mapping, error = load_chip_feature_locations(
            chip_location_json, user_chip_mapping
        )
        if error:
            raise RuntimeError(f"Loading chip features failed: {error}")

        # --- 3. Perform analysis sequence ---
        # 3a. Calculate chip angle and scale from user locations
        result, error = chip_rotation_angle(user_chip_mapping, key="user_location")
        if error:
            raise RuntimeError(f"Initial rotation angle calculation failed: {error}")
        user_chip_mapping, initial_rotation_angle = result

        result, error = user_chip_scale_factor(user_chip_mapping, key="user_location")
        if error:
            raise RuntimeError(f"Initial scale factor calculation failed: {error}")
        user_chip_mapping, _ = result

        # 3b. Rotate image using user angle
        rotated_image, error = rotate_image(image, -initial_rotation_angle)
        if error:
            raise RuntimeError(f"Initial image rotation failed: {error}")

        # 3c. Refine feature locations using template matching
        result, error = refine_feature_locations(
            rotated_image, user_chip_mapping, GENERATED_FILES_DIR
        )
        if error:
            raise RuntimeError(f"First feature refinement failed: {error}")
        user_chip_mapping, _, _ = result

        # 3d. Calculate rotation-angle / scale-factor of image from the located image features (not from user input locations)
        result, error = chip_rotation_angle(user_chip_mapping, key="refined_location")
        if error:
            raise RuntimeError(f"Refined rotation angle calculation failed: {error}")
        user_chip_mapping, _ = result

        # user_chip_mapping['rotation_angle'] = initial_rotation_angle + refined_rotation_angle
        result, error = user_chip_scale_factor(user_chip_mapping, key="refined_location")
        if error:
            raise RuntimeError(f"Refined scale factor calculation failed: {error}")
        user_chip_mapping, _ = result

        # 3e. Rotate image by refined rotation angle
        rotated_image, error = rotate_image(image, -user_chip_mapping["rotation_angle"])
        if error:
            raise RuntimeError(f"Final image rotation failed: {error}")

        # 3f. Refine feature locations again with new rotation-angle / scale-factor using template matching
        result, error = refine_feature_locations(
            rotated_image, user_chip_mapping, GENERATED_FILES_DIR
        )
        if error:
            raise RuntimeError(f"Second feature refinement failed: {error}")
        user_chip_mapping, _, template_shape = result

        # 3g. Calculate offset between image and chip-map
        user_chip_mapping, error = calculate_chip_offset(user_chip_mapping)
        if error:
            raise RuntimeError(f"Chip offset calculation failed: {error}")

        # 3h. Load and offset grating locations
        grating_data, error = load_and_offset_grating_data(chip_location_json, user_chip_mapping)
        if error:
            raise RuntimeError(f"Grating data processing failed: {error}")

        # --- 4. Generate visualisation and output files ---
        visualize_features_with_matplotlib(
            rotated_image,
            user_chip_mapping,
            template_shape,
            label_locations_image_path,
            key="features",
        )

        visualize_features_with_matplotlib(
            rotated_image, grating_data, None, grating_locations_image_path, key="gratings"
        )

        # pp = pprint.PrettyPrinter(indent=4)  # Create a PrettyPrinter object
        # print('User chip mapping:')
        # pp.pprint(user_chip_mapping)

        chip_type = user_chip_mapping["chip_type"]
        rotation_angle = user_chip_mapping["rotation_angle"]
        _, error = create_ROI_JSON(
            chip_type, grating_data, rotated_image.shape, rotation_angle, output_path
        )
        if error:
            raise RuntimeError(f"Failed to create final ROI JSON: {error}")

        _, error = save_json(calculated_image_feature_path, user_chip_mapping)
        if error:
            raise RuntimeError(f"Failed to save calculated image features: {error}")

        # --- 5. Final User Message ---
        print("\n----------------------------------------------------------------------")
        print("   ROI location file has been created successfully.")
        print("   Please check the saved ROI location images before continuing.")
        print("   (see 'generated_files' directory)")
        print("----------------------------------------------------------------------")

    except Exception as e:
        print(f"\n[ERROR] A failure occurred during analysis preparation: {e}", file=sys.stderr)
        logger.error(f"A failure occurred during analysis preparation: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
