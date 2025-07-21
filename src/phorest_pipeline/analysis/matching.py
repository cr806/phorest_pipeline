import itertools
import math
from pathlib import Path

import cv2
import numpy as np

from phorest_pipeline.analysis.file_utils import create_directory_with_error_handling
from phorest_pipeline.analysis.geometry import angle_between_points, calculate_distance
from phorest_pipeline.analysis.image_utils import load_template
from phorest_pipeline.analysis.visualise import (
    visualize_search_window_preprocessing,
    visualize_template_matching_result,
)
from phorest_pipeline.shared.config import LABEL_TEMPLATE_DIR


def get_type_of_chip(chip_type, all_chip_mappings):
    message = "at function get_type_of_chip"
    for chip_mapping in all_chip_mappings:
        chip_name_label = chip_mapping.get("chip_type", None)
        if not chip_name_label:
            return (None, f"[ERROR] Missing 'chip_type' in chip mapping {message}.")
        if chip_name_label == chip_type:
            return (chip_mapping, None)
    return (None, f"[ERROR] Chip type '{chip_type}' not found {message}.")


def get_location_from_label(label, chip_mapping):
    message = "at function get_location_from_label"
    if chip_mapping and isinstance(chip_mapping.get("labels"), list):
        for chip_label in chip_mapping.get("labels"):
            if chip_label and chip_label.get("label") == label:
                return (chip_label.get("label_origin"), None)
        return (None, f"[ERROR] Label '{label}' not found in chip mapping {message}.")
    else:
        return (None, f"[ERROR] Invalid or missing 'labels' in chip mapping {message}.")


def get_user_label_locations_from_chip_map(chip_mapping, user_chip_mapping):
    message = "at function get_user_label_locations_from_chip_map"
    user_features = user_chip_mapping.get("features", None)
    if user_features:
        updated_features = []
        for user_feature in user_features:
            label = user_feature.get("label", None)
            if not label:
                return (None, f"[ERROR] Missing 'label' in user chip mapping {message}.")
            feature_location, error = get_location_from_label(label, chip_mapping)
            if error:
                error = error + f" {message}"
                return (None, error)
            user_feature["chip_location"] = feature_location
            updated_features.append(user_feature)
        user_chip_mapping["features"] = updated_features
        return (user_chip_mapping, None)
    return (None, f"[ERROR] Missing 'features' in user chip mapping {message}.")


def chip_rotation_angle(user_chip_mapping, key="user_location"):
    message = "at function chip_rotation_angle"
    if (
        not isinstance(user_chip_mapping, dict)
        or "features" not in user_chip_mapping
        or not isinstance(user_chip_mapping["features"], list)
        or len(user_chip_mapping["features"]) < 2
    ):
        return (
            None,
            f"[ERROR] Invalid user chip mapping structure or insufficient features {message}.",
        )

    locations = [a.get(key) for a in user_chip_mapping["features"] if a.get(key) is not None]
    chip_locations = [
        a.get("chip_location")
        for a in user_chip_mapping["features"]
        if a.get("chip_location") is not None
    ]

    if len(locations) < 2 or len(chip_locations) < 2:
        return (
            None,
            f"[ERROR] Insufficient valid locations or chip locations (key: {key}) {message}.",
        )

    combination_idxs = list(itertools.combinations(range(len(locations)), 2))

    location_combinations = [(locations[a], locations[b]) for (a, b) in combination_idxs]
    chip_location_combinations = [
        (chip_locations[a], chip_locations[b]) for (a, b) in combination_idxs
    ]

    angles = [angle_between_points(a, b) for (a, b) in location_combinations]
    chip_angles = [angle_between_points(a, b) for (a, b) in chip_location_combinations]

    rotation_angles = [a - b for a, b in zip(chip_angles, angles)]

    rotation_angle = np.quantile(rotation_angles, 0.5)

    user_chip_mapping[f"{key}_all_rotation_angles"] = angles
    user_chip_mapping["chip_location_all_rotation_angles"] = chip_angles

    if "refined" in key and "rotation_angle" in user_chip_mapping:
        rotation_angle = user_chip_mapping["rotation_angle"] + rotation_angle

    user_chip_mapping[f"{key}_rotation_angle"] = rotation_angle
    user_chip_mapping["rotation_angle"] = rotation_angle

    return ((user_chip_mapping, rotation_angle), None)


def user_chip_scale_factor(user_chip_mapping, key="user_location"):
    message = "at function user_chip_scale_factor"
    if (
        not isinstance(user_chip_mapping, dict)
        or "features" not in user_chip_mapping
        or not isinstance(user_chip_mapping["features"], list)
        or len(user_chip_mapping["features"]) < 2
    ):
        return (
            None,
            f"[ERROR] Invalid user chip mapping structure or insufficient features {message}.",
        )

    locations = [a.get(key) for a in user_chip_mapping["features"] if a.get(key) is not None]
    chip_locations = [
        a.get("chip_location")
        for a in user_chip_mapping["features"]
        if a.get("chip_location") is not None
    ]

    if len(locations) < 2 or len(chip_locations) < 2:
        return (
            None,
            f"[ERROR] Insufficient valid locations or chip locations to calculate scale factor {message}.",
        )

    combination_idxs = list(itertools.combinations(range(len(locations)), 2))

    location_combinations = [(locations[a], locations[b]) for (a, b) in combination_idxs]
    chip_location_combinations = [
        (chip_locations[a], chip_locations[b]) for (a, b) in combination_idxs
    ]

    distances = [calculate_distance(a, b) for (a, b) in location_combinations]
    chip_distances = [calculate_distance(a, b) for (a, b) in chip_location_combinations]

    scale_factors = []
    for dist, chip_dist in zip(distances, chip_distances):
        if chip_dist == 0:
            return (
                None,
                f"[ERROR] Zero distance encountered in chip locations, cannot calculate scale factor {message}.",
            )
        scale_factors.append(dist / chip_dist)

    if not scale_factors:
        return (None, f"[ERROR] Could not calculate scale factors {message}.")

    user_chip_mapping[f"{key}_all_scale_factors"] = scale_factors

    scale_factor = np.quantile(scale_factors, 0.5)

    user_chip_mapping[f"{key}_scale_factor"] = scale_factor
    user_chip_mapping["scale_factor"] = scale_factor

    return ((user_chip_mapping, scale_factor), None)


def rotate_user_feature_locations(user_location, image_center, rotation_angle):
    message = "at function rotate_user_feature_locations"
    if not (
        isinstance(user_location, (tuple, list))
        and len(user_location) == 2
        and all(isinstance(coord, (int, float)) for coord in user_location)
    ):
        return (None, f"[ERROR] 'user_location' must be a tuple or list of two numbers {message}.")
    if not (
        isinstance(image_center, (tuple, list))
        and len(image_center) == 2
        and all(isinstance(coord, (int, float)) for coord in image_center)
    ):
        return (None, f"[ERROR] 'image_center' must be a tuple or list of two numbers {message}.")
    if not isinstance(rotation_angle, (int, float)):
        return (None, f"[ERROR] 'rotation_angle' must be a number {message}.")

    x, y = user_location
    cx, cy = image_center
    angle_rad = math.radians(rotation_angle)

    rotated_x = cx + (x - cx) * math.cos(angle_rad) - (y - cy) * math.sin(angle_rad)
    rotated_y = cy + (x - cx) * math.sin(angle_rad) + (y - cy) * math.cos(angle_rad)
    return ([int(rotated_x), int(rotated_y)], None)


def get_template_image_from_label(chip_type, label):
    # TODO! Factor this filepath out
    message = "at function get_template_image_from_label"
    template_path = Path(LABEL_TEMPLATE_DIR, f"{chip_type[:-2]}", f"{chip_type}", f"{label}.png")
    if not template_path.exists():
        return (None, f"[ERROR] Template file not found at: {template_path} at {message}.")
    template, error = load_template(template_path)
    if error:
        error = error + f" {message}"
        return (None, error)
    return (template, None)


def scale_template(template, scale_factor):
    message = "at function scale_template"
    if not isinstance(template, np.ndarray):
        return (None, f"[ERROR] Input 'template' must be a NumPy array {message}.")
    if not isinstance(scale_factor, (int, float)) or scale_factor <= 0:
        return (None, f"[ERROR] Input 'scale_factor' must be a positive number {message}.")

    try:
        new_size = (int(template.shape[1] * scale_factor), int(template.shape[0] * scale_factor))
        scaled_template = cv2.resize(template, new_size, interpolation=cv2.INTER_LINEAR)
        return (scaled_template, None)
    except cv2.error as e:
        return (None, f"[ERROR] OpenCV error during template scaling {message}: {e}")
    except Exception as e:
        return (
            None,
            f"[ERROR] An unexpected error occurred during template scaling {message}: {e}",
        )


## Find the location of the template in the image using cv2.matchTemplate
def refine_feature_locations(image, user_chip_mapping, result_save_path):
    message = "at function refine_feature_locations"
    chip_type = user_chip_mapping.get("chip_type", None)
    if not chip_type:
        return (None, f"[ERROR] 'chip_type' not found in user chip mapping {message}.")

    rotation_angle = user_chip_mapping.get("rotation_angle", None)
    if not rotation_angle:
        return (None, f"[ERROR] 'rotation_angle' not found in user chip mapping {message}.")

    scale_factor = user_chip_mapping.get("scale_factor", None)
    if not scale_factor:
        return (None, f"[ERROR] 'scale_factor' not found in user chip mapping {message}.")

    image_center = (image.shape[1] / 2, image.shape[0] / 2)

    user_features = user_chip_mapping.get("features", None)
    if not user_features:
        return (None, f"[ERROR] 'features' not found in user chip mapping {message}.")

    result_save_root = Path(result_save_path, "label_locating_results")
    result, error = create_directory_with_error_handling(result_save_root)
    if error:
        error = error + f" {message}"
        return (None, error)
    result_save_path = Path(result_save_root, result_save_path.name)

    for idx, f in enumerate(user_features):
        label = f.get("label")
        user_location = f.get("user_location")

        if not label or not user_location:
            user_chip_mapping["features"][idx]["refined_location"] = None
            user_chip_mapping["features"][idx]["match_quality"] = 0
            user_chip_mapping["features"][idx]["label_locating_success"] = False
            continue

        # Rotate the user location to match the rotated image
        rotated_user_location, error = rotate_user_feature_locations(
            user_location, image_center, rotation_angle
        )
        if error:
            error = error + f" {message}"
            return (None, error)

        # Load and scale template to match image size
        template, error = get_template_image_from_label(chip_type, label)
        if error:
            error = error + f" {message}"
            return (None, error)

        template, error = scale_template(template, scale_factor)
        if error:
            error = error + f" {message}"
            return (None, error)

        # Define a search window around the rotated initial location
        search_window_size = (template.shape[1] * 1.5, template.shape[0] * 1.5)
        x_start = max(0, int(rotated_user_location[0] - search_window_size[0] / 2))
        y_start = max(0, int(rotated_user_location[1] - search_window_size[1] / 2))
        x_end = min(image.shape[1], int(rotated_user_location[0] + search_window_size[0] / 2))
        y_end = min(image.shape[0], int(rotated_user_location[1] + search_window_size[1] / 2))

        search_window = image[y_start:y_end, x_start:x_end]

        if search_window.size == 0:
            user_chip_mapping["features"][idx]["refined_location"] = None
            user_chip_mapping["features"][idx]["match_quality"] = 0
            user_chip_mapping["features"][idx]["label_locating_success"] = False
            continue

        ## Pre-process the search window to match the template type
        # Sharpen the search window
        blurred = cv2.GaussianBlur(search_window, (25, 25), 0)
        sharpened_search_window = cv2.addWeighted(search_window, 1.5, blurred, -0.5, 0)

        # Binarise the search window to match the template
        _, binarized_search_window = cv2.threshold(
            sharpened_search_window, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
        )

        _result_save_path = result_save_path.with_name(
            f"{label}_pre-processing_{result_save_path.name}"
        )
        visualize_search_window_preprocessing(
            search_window, sharpened_search_window, binarized_search_window, _result_save_path
        )

        # Perform template matching
        result = cv2.matchTemplate(binarized_search_window, template, cv2.TM_CCORR_NORMED)

        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # Calculate quality metric (e.g., peak-to-mean ratio)
        mean_val = np.mean(result)
        quality_metric = max_val / mean_val if mean_val > 0 else 0  # Avoid division by zero
        _result_save_path = result_save_path.with_name(f"{label}_matching_{result_save_path.name}")
        visualize_template_matching_result(
            search_window, result, max_loc, max_val, mean_val, quality_metric, _result_save_path
        )

        if quality_metric > 1.5:
            refined_x = x_start + max_loc[0]
            refined_y = y_start + max_loc[1]
            user_chip_mapping["features"][idx]["refined_location"] = [refined_x, refined_y]
            user_chip_mapping["features"][idx]["match_quality"] = quality_metric
            is_good_match = True
            user_chip_mapping["features"][idx]["label_locating_success"] = is_good_match
        else:
            refined_x = None
            refined_y = None
            user_chip_mapping["features"][idx]["refined_location"] = None
            user_chip_mapping["features"][idx]["match_quality"] = quality_metric
            is_good_match = False
            user_chip_mapping["features"][idx]["label_locating_success"] = is_good_match

    return ((user_chip_mapping, [refined_x, refined_y], template.shape), None)


## Calculate image offset from chip map
def calculate_chip_offset(user_chip_mapping):
    message = "at function calculate_chip_offset"
    if (
        not isinstance(user_chip_mapping, dict)
        or "features" not in user_chip_mapping
        or not isinstance(user_chip_mapping["features"], list)
    ):
        return (None, f"[ERROR] Invalid user chip mapping structure {message}.")

    scale_factor = user_chip_mapping.get("scale_factor", None)
    if not isinstance(scale_factor, (int, float)):
        return (None, f"[ERROR] 'scale_factor' must be a number {message}.")

    user_features = user_chip_mapping["features"]
    if not user_features:
        return (None, f"[ERROR] No user features found in mapping {message}.")

    x_offsets = []
    y_offsets = []
    for idx, f in enumerate(user_features):
        refined_location = f.get("refined_location")
        chip_location = f.get("chip_location")

        if (
            refined_location is not None
            and chip_location is not None
            and len(refined_location) == 2
            and len(chip_location) == 2
        ):
            try:
                offset = [a - (b * scale_factor) for a, b in zip(refined_location, chip_location)]
                x_offsets.append(offset[0])
                y_offsets.append(offset[1])
                user_chip_mapping["features"][idx]["feature_offset"] = offset
            except TypeError:
                user_chip_mapping["features"][idx]["feature_offset"] = None
        else:
            user_chip_mapping["features"][idx]["feature_offset"] = None

    if x_offsets and y_offsets:
        user_chip_mapping["offset"] = [np.quantile(x_offsets, 0.5), np.quantile(y_offsets, 0.5)]
        return (user_chip_mapping, None)
    else:
        return (
            None,
            f"[ERROR] Could not calculate chip offset due to missing location data {message}.",
        )


## Load and offset grating locations from chip map
def offset_and_scale_grating_data(grating_mapping, user_chip_mapping):
    message = "at function offset_and_scale_grating_data"
    if (
        not isinstance(user_chip_mapping, dict)
        or "offset" not in user_chip_mapping
        or "scale_factor" not in user_chip_mapping
    ):
        return (
            None,
            f"[ERROR] Invalid user chip mapping structure (missing 'offset' or 'scale_factor') {message}.",
        )

    offset = user_chip_mapping.get("offset")
    scale_factor = user_chip_mapping.get("scale_factor")

    if not isinstance(grating_mapping, list):
        return (None, f"[ERROR] 'grating_mapping' must be a list {message}.")

    if not isinstance(offset, list) or len(offset) != 2 or offset[0] is None or offset[1] is None:
        return (
            None,
            f"[ERROR] Invalid offset in user chip mapping: must be a list of two non-None numbers {message}.",
        )

    if not isinstance(scale_factor, (int, float)):
        return (None, f"[ERROR] 'scale_factor' in user chip mapping must be a number {message}.")

    updated_grating_mapping = []
    for grating in grating_mapping:
        if (
            not isinstance(grating, dict)
            or "grating_origin" not in grating
            or "x-size" not in grating
            or "y-size" not in grating
        ):
            continue  # Skip this grating if it doesn't have the required keys

        grating_origin = grating.get("grating_origin")
        x_size = grating.get("x-size")
        y_size = grating.get("y-size")

        if (
            not isinstance(grating_origin, list)
            or len(grating_origin) != 2
            or not all(isinstance(coord, (int, float)) for coord in grating_origin)
        ):
            continue  # Skip if grating origin is invalid

        if not isinstance(x_size, (int, float)) or not isinstance(y_size, (int, float)):
            continue  # Skip if sizes are invalid

        try:
            offset_grating_origin = [
                int((a * scale_factor) + b) for a, b in zip(grating_origin, offset)
            ]
            updated_grating = grating.copy()
            updated_grating["grating_origin"] = offset_grating_origin
            updated_grating["x-size"] = int(x_size * scale_factor)
            updated_grating["y-size"] = int(y_size * scale_factor)
            updated_grating_mapping.append(updated_grating)
        except Exception as e:
            return (None, f"[ERROR] Error processing grating: {e} {message}.")

    return (updated_grating_mapping, None)
