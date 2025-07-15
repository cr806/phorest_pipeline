# scripts/generate_roi_manifest.py
import sys
from pathlib import Path

from phorest_pipeline.analysis.file_utils import create_directory_with_error_handling
from phorest_pipeline.analysis.geometry import (
    rotate_image,
)
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
from phorest_pipeline.analysis.visualise import (
    visualize_features_with_matplotlib,
)
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


def generate_roi_manifest():
    """
    Reads all paths from the central config and runs the ROI generation process.
    """
    try:
        output_path = Path(GENERATED_FILES_DIR, ROI_MANIFEST_FILENAME)

        chip_location_json = Path(LABEL_TEMPLATE_DIR, "Chip_map.json")
        calculated_image_feature_path = Path(GENERATED_FILES_DIR, "CalculatedImageFeatures.json")
        grating_locations_image_path = Path(GENERATED_FILES_DIR, "Grating_locations.png")
        label_locations_image_path = Path(GENERATED_FILES_DIR, "Label_locations.png")

        result, error = create_directory_with_error_handling(GENERATED_FILES_DIR)
        if error:
            print(error)

        image, error = load_image_and_normalise(ROI_GENERATION_IMAGE_PATH)
        if error:
            print(error)

        user_chip_mapping, error = load_user_feature_locations(FEATURE_LOCATIONS_CONFIG_PATH)
        if error:
            print(error)

        user_chip_mapping, error = load_chip_feature_locations(
            chip_location_json, user_chip_mapping
        )
        if error:
            print(error)

        # 2. Calculate angle and scale according to user's input
        result, error = chip_rotation_angle(user_chip_mapping, key="user_location")
        if error:
            print(error)
        user_chip_mapping, initial_rotation_angle = result

        result, error = user_chip_scale_factor(user_chip_mapping, key="user_location")
        if error:
            print(error)
        user_chip_mapping, _ = result

        # 3. Rotate image using user angle
        rotated_image, error = rotate_image(image, -initial_rotation_angle)
        if error:
            print(error)

        # 4. Refine feature locations using template matching
        result, error = refine_feature_locations(
            rotated_image, user_chip_mapping, GENERATED_FILES_DIR
        )
        if error:
            print(error)
        user_chip_mapping, refined_locations, _ = result

        # 5. Calculate rotation-angle / scale-factor of image from locatedd the image features (not from user input locations)
        result, error = chip_rotation_angle(user_chip_mapping, key="refined_location")
        if error:
            print(error)
        user_chip_mapping, refined_rotation_angle = result

        # user_chip_mapping['rotation_angle'] = initial_rotation_angle + refined_rotation_angle
        result, error = user_chip_scale_factor(user_chip_mapping, key="refined_location")
        if error:
            print(error)
        user_chip_mapping, refined_scale_factor = result

        # 6. Rotate image by refined rotation angle
        rotated_image, error = rotate_image(image, -user_chip_mapping["rotation_angle"])
        if error:
            print(error)

        # 6. Refine feature locations again with new rotation-angle / scale-factor using template matching
        result, error = refine_feature_locations(
            rotated_image, user_chip_mapping, GENERATED_FILES_DIR
        )
        if error:
            print(error)
        user_chip_mapping, refined_locations, template_shape = result

        # 7. Calculate offset between image and chip-map
        user_chip_mapping, error = calculate_chip_offset(user_chip_mapping)
        if error:
            print(error)

        # 8. Load and offset grating locations
        grating_data, error = load_and_offset_grating_data(chip_location_json, user_chip_mapping)
        if error:
            print(error)

        # 9.. Visualise feature location results
        visualize_features_with_matplotlib(
            rotated_image,
            user_chip_mapping,
            template_shape,
            label_locations_image_path,
            key="features",
        )

        # 10. Visualise grating location results
        visualize_features_with_matplotlib(
            rotated_image, grating_data, None, grating_locations_image_path, key="gratings"
        )

        # 11. Display results
        # pp = pprint.PrettyPrinter(indent=4)  # Create a PrettyPrinter object
        # print('User chip mapping:')
        # pp.pprint(user_chip_mapping)

        # 12. Create ROI JSON file
        chip_type = user_chip_mapping["chip_type"]
        rotation_angle = user_chip_mapping["rotation_angle"]
        result, error = create_ROI_JSON(
            chip_type, grating_data, rotated_image.shape, rotation_angle, output_path
        )
        if error:
            print(error)

        # 13. Save calculated image features
        result, error = save_json(calculated_image_feature_path, user_chip_mapping)
        if error:
            print(error)

            logger.info("Successfully generated ROI manifest.")

    except Exception as e:
        logger.error(f"Failed to generate ROI manifest: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    generate_roi_manifest()
