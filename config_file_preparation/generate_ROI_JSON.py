from pathlib import Path

from config_file_preparation.Locator_functions import (
    calculate_chip_offset,
    chip_rotation_angle,
    create_directory_with_error_handling,
    create_ROI_JSON,
    load_and_offset_grating_data,
    load_chip_feature_locations,
    load_image_and_normalise,
    load_user_feature_locations,
    refine_feature_locations,
    rotate_image,
    save_json,
    user_chip_scale_factor,
    visualize_features_with_matplotlib,
)


def generate_ROI_JSON(path_to_image, output_ROI_filename):
    """Main function to perform image alignment and feature localization."""
    # 1. Script input file data
    feature_location_toml = Path('configs', 'Feature_locations.toml')
    chip_location_json = Path('config_file_preparation', 'Label_templates', 'Chip_map.json')
    generated_results_root = Path('generated_files')
    calculated_image_feature_path = Path(generated_results_root, 'CalculatedImageFeatures.json')
    grating_locations_image_path = Path(generated_results_root, 'Grating_locations.png')
    label_locations_image_path = Path(generated_results_root, 'Label_locations.png')
    template_matching_image_path = Path(generated_results_root, 'result.png')
    output_ROI_path = Path(generated_results_root, output_ROI_filename)

    result, error = create_directory_with_error_handling(generated_results_root)
    if error:
        print(error)
        exit(1)

    image, error = load_image_and_normalise(path_to_image)
    if error:
        print(error)
        exit(1)

    user_chip_mapping, error = load_user_feature_locations(feature_location_toml)
    if error:
        print(error)
        exit(1)

    user_chip_mapping, error = load_chip_feature_locations(chip_location_json, user_chip_mapping)
    if error:
        print(error)
        exit(1)

    # 2. Calculate angle and scale according to user's input
    result, error = chip_rotation_angle(user_chip_mapping, key='user_location')
    if error:
        print(error)
        exit(1)
    user_chip_mapping, initial_rotation_angle = result

    result, error = user_chip_scale_factor(user_chip_mapping, key='user_location')
    if error:
        print(error)
        exit(1)
    user_chip_mapping, _ = result

    # 3. Rotate image using user angle
    rotated_image, error = rotate_image(image, -initial_rotation_angle)
    if error:
        print(error)
        exit(1)

    # 4. Refine feature locations using template matching
    result, error = refine_feature_locations(
        rotated_image, user_chip_mapping, template_matching_image_path
    )
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_locations, _ = result

    # 5. Calculate rotation-angle / scale-factor of image from locatedd the image features (not from user input locations)
    result, error = chip_rotation_angle(user_chip_mapping, key='refined_location')
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_rotation_angle = result

    # user_chip_mapping['rotation_angle'] = initial_rotation_angle + refined_rotation_angle
    result, error = user_chip_scale_factor(user_chip_mapping, key='refined_location')
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_scale_factor = result

    # 6. Rotate image by refined rotation angle
    rotated_image, error = rotate_image(image, -user_chip_mapping['rotation_angle'])
    if error:
        print(error)
        exit(1)

    # 6. Refine feature locations again with new rotation-angle / scale-factor using template matching
    result, error = refine_feature_locations(
        rotated_image, user_chip_mapping, template_matching_image_path
    )
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_locations, template_shape = result

    # 7. Calculate offset between image and chip-map
    user_chip_mapping, error = calculate_chip_offset(user_chip_mapping)
    if error:
        print(error)
        exit(1)

    # 8. Load and offset grating locations
    grating_data, error = load_and_offset_grating_data(chip_location_json, user_chip_mapping)
    if error:
        print(error)
        exit(1)

    # 9.. Visualise feature location results
    visualize_features_with_matplotlib(
        rotated_image,
        user_chip_mapping,
        template_shape,
        label_locations_image_path,
        key='features',
    )

    # 10. Visualise grating location results
    visualize_features_with_matplotlib(
        rotated_image, grating_data, None, grating_locations_image_path, key='gratings'
    )

    # 11. Display results
    # pp = pprint.PrettyPrinter(indent=4)  # Create a PrettyPrinter object
    # print('User chip mapping:')
    # pp.pprint(user_chip_mapping)

    # 12. Create ROI JSON file
    chip_type = user_chip_mapping['chip_type']
    rotation_angle = user_chip_mapping['rotation_angle']
    result, error = create_ROI_JSON(
        chip_type, grating_data, rotated_image.shape, rotation_angle, output_ROI_path
    )
    if error:
        print(error)
        exit(1)

    # 13. Save calculated image features
    result, error = save_json(calculated_image_feature_path, user_chip_mapping)
    if error:
        print(error)
        exit(1)


if __name__ == '__main__':
    # path_to_image = Path(
    #   '/Volumes/krauss/Lisa/GMR/Array/250325/loc1_1/Pos0/img_000000000_Default_000.tif'
    # )
    path_to_image = Path(
        '/Volumes/krauss/Callum/03_Data/17_array_testing/ethanol_full_array_test_240425_flipped/image_20250424_161414.png'
    )
    output_ROI_filename = Path('ROI_ChirpArray_TEST.json')

    generate_ROI_JSON(path_to_image, output_ROI_filename)
