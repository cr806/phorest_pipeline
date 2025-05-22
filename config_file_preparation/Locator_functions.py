import itertools
import json
import math
import tomllib
from pathlib import Path

import cv2
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

TEMPLATE_PATH_ROOT = Path("config_file_preparation", "Label_templates")


## Load user feature locations from JSON file and populate 'user_chip_mapping' dictionary


def load_image_and_normalise(image_path):
    message = "at function load_image_and_normalise"
    try:
        if not isinstance(image_path, Path):
            raise TypeError("Image path must be a path.")
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found at: {image_path}")
        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if image is None:
            return (None, f"[ERROR] Error loading image {message}: cv2.imread returned None.")
        image = cv2.normalize(
            image,
            None,
            0,
            255,
            cv2.NORM_MINMAX,
            dtype=cv2.CV_8U,  # type: ignore
        )
        if len(image.shape) > 2:  # Check if the image has more than one channel
            try:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            except cv2.error as e:
                return (
                    None,
                    f"[ERROR] Error converting image to greyscale {message}: OpenCV error - {e}",
                )
            except Exception as e:
                return (
                    None,
                    f"[ERROR] An unexpected error occurred during greyscale conversion {message}: {e}",
                )
        return (image, None)
    except FileNotFoundError as e:
        return (None, f"[ERROR] Error loading image {message}: {e}")
    except TypeError as e:
        return (None, f"[ERROR] Error loading image {message}: {e}")
    except cv2.error as e:
        return (None, f"[ERROR] Error loading image {message}: OpenCV error - {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred {message}: {e}")


def load_json(file_path):
    message = "at function load_json"
    try:
        if not isinstance(file_path, Path):
            raise TypeError("File path must be a Path object.")
        if not file_path.exists():
            raise FileNotFoundError(f"File not found at '{file_path}'")
        with file_path.open("r") as f:
            data = json.load(f)
        return (data, None)
    except FileNotFoundError as e:
        return (None, f"[ERROR] File not found {message}: {e}")
    except json.JSONDecodeError as e:
        return (
            None,
            f"[ERROR] Could not decode JSON from '{file_path}' {message}: {e}. Check the file format.",
        )
    except TypeError as e:
        return (None, f"[ERROR] Invalid file path type {message}: {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred {message}: {e}")


def save_json(file_path: Path, data):
    message = "at function save_json"

    def convert_numpy(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        return obj

    try:
        if not isinstance(file_path, Path):
            raise TypeError("File path must be a Path object.")
        with file_path.open("w") as f:
            json.dump(data, f, indent=4, default=convert_numpy)
        return (None, None)
    except TypeError as e:
        return (None, f"[ERROR] Invalid file path type {message}: {e}")
    except IOError as e:
        return (None, f'[ERROR] Error writing JSON to "{file_path}" {message}: {e}')
    except json.JSONEncodeError as e:
        return (None, f"[ERROR] Could not encode data to JSON {message}: {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred while saving JSON {message}: {e}")


def create_directory_with_error_handling(directory_path: Path):
    message = "at function create_directory_with_error_handling"
    try:
        directory_path.mkdir(parents=True, exist_ok=True)
        return (None, None)
    except FileExistsError:
        # This should be rare with exist_ok=True, but handle just in case
        return (None, f"[WARNING] Directory '{directory_path}' already exists {message}.")
    except FileNotFoundError as e:
        return (
            None,
            f"[ERROR] Could not create directory '{directory_path}' - likely a permission issue) {message}: {e}",
        )
    except PermissionError as e:
        return (
            None,
            f"[ERROR] Permission denied to create directory '{directory_path}' {message}: {e}",
        )
    except OSError as e:
        return (
            None,
            f"[ERROR] Operating system error occurred while creating directory '{directory_path}' {message}: {e}",
        )
    except Exception as e:
        return (
            None,
            f"[ERROR] An unexpected error occurred while creating directory '{directory_path}' {message}: {e}",
        )


def load_user_feature_locations(file_path):
    message = "at function load_user_feature_locations"
    user_raw_data = None  # Initialize to None

    try:
        # Use 'rb' mode for tomllib (binary read)
        with file_path.open("rb") as f:
            user_raw_data = tomllib.load(f)
    except FileNotFoundError:
        return (None, f"[ERROR] Config file not found at '{file_path}' {message}")
    except tomllib.TomlDecodeError as e:
        return (None, f"[ERROR] Error decoding TOML file '{file_path}': {e} {message}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred: {e} {message}")
    
    user_chip_mapping = {}

    chip_type = user_raw_data.get('chip_type')
    if chip_type is None:
        return (None, f"[ERROR] Missing 'chip_type' in user feature data {message}.")
    user_chip_mapping['chip_type'] = chip_type

    user_features = user_raw_data.get('features')
    if user_features is None:
        return (None, f"[ERROR] Missing 'features' list in user feature data {message}.")

    features = []
    for feature in user_features:
        label_name = feature.get('label')
        if label_name is None:
            return (None, f"[ERROR] Missing 'label' in a feature entry {message}.")

        feature_location = feature.get('feature_location')
        if feature_location is None:
            return (
                None,
                f"[ERROR] Missing 'feature_location' in a feature entry {message}.",
            )
        # Ensure feature_location is a list/tuple as expected, if not already
        if not isinstance(feature_location, (list, tuple)):
            return (None, f"[ERROR] 'feature_location' for label '{label_name}' is not a list or tuple {message}.")

        features.append({'label': label_name, 'user_location': feature_location})

    user_chip_mapping['features'] = features
    return (user_chip_mapping, None)


## Load chip map locations from JSON and update 'user_chip_map' dictionary


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


def load_chip_feature_locations(file_path, user_chip_mapping):
    message = "at function load_chip_feature_locations"
    chip_raw_data, error = load_json(file_path)
    if error:
        error = error + f" {message}"
        return (None, error)

    chip_type = user_chip_mapping.get("chip_type", None)
    if not chip_type:
        return (None, f"[ERROR] Chip type '{chip_type}' not found {message}.")

    chip_mapping, error = get_type_of_chip(chip_type, chip_raw_data["chip"])
    if error:
        error = error + f" {message}"
        return (None, error)

    locations, error = get_user_label_locations_from_chip_map(chip_mapping, user_chip_mapping)
    if error:
        error = error + f" {message}"
        return (None, error)
    return (locations, None)


## Calculate the rotation angle


def angle_between_points(v1, v2):
    """Calculates the signed angle in degrees between the line connecting two vectors
    and the positive x-axis.

    Args:
        v1: (x1, y1)
        v2: (x2, y2)

    Returns:
        Angle in degrees, positive for counter-clockwise rotation from the
        positive x-axis to the line segment from point1 to point2.
    """
    x1, y1 = v1
    x2, y2 = v2

    dx = x2 - x1
    dy = y2 - y1

    return math.degrees(math.atan2(dy, dx))  # Angle relative to positive x-axis


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


## Calculate the scale factor


def calculate_distance(v1, v2):
    """Calculates the Euclidean distance between two points in 2D space.

    Args:
      v1: A tuple or list representing the first point (x1, y1).
      v1: A tuple or list representing the second point (x2, y2).

    Returns:
      The Euclidean distance between the two points.
    """
    x1, y1 = v1
    x2, y2 = v2

    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


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


## Rotate the image and user feature locations using calculated angle
def rotate_image(image, rotation_angle):
    message = "at function rotate_image"
    if not isinstance(image, np.ndarray):
        return (None, f"[ERROR] Input 'image' must be a NumPy array {message}.")
    if not isinstance(rotation_angle, (int, float)):
        return (None, f"[ERROR] Input 'rotation_angle' must be a number {message}.")

    try:
        # Calculate the center of rotation
        h, w = image.shape[:2]  # Handle both grayscale and color images
        center = (w / 2, h / 2)

        # Get the rotation matrix
        rotation_matrix = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)

        # Apply the rotation
        rotated_image = cv2.warpAffine(image, rotation_matrix, (w, h))

        return (rotated_image, None)
    except cv2.error as e:
        return (None, f"[ERROR] OpenCV error during image rotation {message}: {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during image rotation {message}: {e}")


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


## Load template image and scale according to the scale factor
def load_template(template_path):
    message = "at function load_template"
    try:
        if not isinstance(template_path, Path):
            raise TypeError("Template path must be a Path object.")
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found at: {template_path}")
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            return (None, f"[ERROR] Error loading template {message}: cv2.imread returned None.")
        return (template, None)
    except FileNotFoundError as e:
        return (None, f"[ERROR] Error loading template {message}: {e}")
    except TypeError as e:
        return (None, f"[ERROR] Error loading template {message}: {e}")
    except cv2.error as e:
        return (None, f"[ERROR] OpenCV error loading template {message}: {e}")
    except Exception as e:
        return (
            None,
            f"[ERROR] An unexpected error occurred while loading the template {message}: {e}",
        )


def get_template_image_from_label(chip_type, label):
    # TODO! Factor this filepath out
    message = "at function get_template_image_from_label"
    template_path = Path(TEMPLATE_PATH_ROOT, f"{chip_type[:-2]}", f"{chip_type}", f"{label}.png")
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


## Visualise results with matplotlib
def visualize_search_window_preprocessing(
    original_search_window, sharpened_search_window, binarized_search_window, save_path
):
    message = "at function visualize_search_window_preprocessing"

    if not isinstance(save_path, Path):
        return (None, f"[ERROR] 'save_path' must be a pathlib.Path object {message}.")

    _, axes = plt.subplots(1, 3, figsize=(15, 5))

    try:
        axes[0].imshow(cv2.cvtColor(original_search_window, cv2.COLOR_BGR2RGB))
        axes[0].set_title("Original Search Window")
        axes[0].axis("off")

        axes[1].imshow(cv2.cvtColor(sharpened_search_window, cv2.COLOR_BGR2RGB))
        axes[1].set_title("Sharpened Search Window")
        axes[1].axis("off")

        axes[2].imshow(cv2.cvtColor(binarized_search_window, cv2.COLOR_BGR2RGB))
        axes[2].set_title("Binarized Search Window")
        axes[2].axis("off")

        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        return (None, None)
    except IOError as e:
        return (
            None,
            f"[ERROR] Error saving search window visualization to '{save_path}' {message}: {e}",
        )
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during visualization {message}: {e}")


def visualize_template_matching_result(
    search_window, result, max_loc, max_val, mean_val, quality_metric, save_path
):
    message = "at function visualize_template_matching_result"

    if not isinstance(save_path, Path):
        return (None, f"[ERROR] 'save_path' must be a pathlib.Path object {message}.")

    try:
        _, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))

        ax1.imshow(cv2.cvtColor(search_window, cv2.COLOR_BGR2RGB))
        ax1.set_title("Search Window")
        circle1 = patches.Circle(max_loc, 5, color="red", fill=False)
        ax1.add_patch(circle1)

        ax2.imshow(result, cmap="gray")
        ax2.set_title(
            f"Template Matching Result\n{max_val =:.2f}\n{mean_val =:.2f}\n{quality_metric =:.2f}"
        )
        circle2 = patches.Circle(max_loc, 5, color="red", fill=False)
        ax2.add_patch(circle2)

        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        return (None, None)
    except IOError as e:
        return (
            None,
            f"[ERROR] Error saving template matching visualization to '{save_path}' {message}: {e}",
        )
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during visualization {message}: {e}")


def visualize_features_with_matplotlib(
    rotated_image, chip_mapping, feature_shape, save_path, key="features"
):
    message = "at function visualize_features_with_matplotlib"

    if not isinstance(save_path, Path):
        return (None, f"[ERROR] 'save_path' must be a pathlib.Path object {message}.")

    try:
        rotated_image_rgb = cv2.cvtColor(rotated_image, cv2.COLOR_BGR2RGB)

        _, ax = plt.subplots(1, figsize=(12, 12))
        ax.imshow(rotated_image_rgb)

        if "features" in key:
            features = chip_mapping.get(key, None)
        if "gratings" in key:
            features = chip_mapping

        if features:
            for f in features:
                label = f.get("label")
                if "features" in key:
                    location = f.get("refined_location")
                if "gratings" in key:
                    location = f.get("grating_origin")

                if location:
                    x, y = location
                    if feature_shape:
                        height, width = feature_shape
                    else:
                        width = f.get("x-size")
                        height = f.get("y-size")

                    rect = patches.Rectangle(
                        (x, y), width, height, linewidth=1, edgecolor="white", facecolor="none"
                    )
                    ax.add_patch(rect)
                    ax.annotate(
                        label, location, color="white", fontsize=8, ha="center", va="bottom"
                    )

        plt.title("Rotated Image with features highlighted")
        plt.savefig(save_path)
        plt.close()
        return (None, None)
    except IOError as e:
        return (None, f"[ERROR] Error saving visualization to '{save_path}' {message}: {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during visualization {message}: {e}")


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

    result_save_root = Path(result_save_path.parent, "label_locating_results")
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


def load_and_offset_grating_data(file_path, user_chip_mapping):
    message = "at function load_and_offset_grating_data"
    chip_raw_data, error = load_json(file_path)
    if error:
        error = error + f" {message}"
        return (None, error)

    chip_type = user_chip_mapping.get("chip_type", None)
    if not chip_type:
        return (None, f"[ERROR] 'chip_type' not found in user chip mapping {message}.")
    chip_mapping, error = get_type_of_chip(chip_type, chip_raw_data["chip"])
    if error:
        error = error + f" {message}"
        return (None, error)

    raw_grating_mapping = chip_mapping.get("gratings", None)
    if not raw_grating_mapping:
        return (None, f"[ERROR] 'gratings' not found in chip mapping {message}.")

    offset_grating_data, error = offset_and_scale_grating_data(
        raw_grating_mapping, user_chip_mapping
    )
    if error:
        error = error + f" {message}"
        return (None, error)
    return (offset_grating_data, None)


## Create ROI JSON file
def create_ROI_JSON(chip_type, grating_data, target_shape, rotation_angle, ROI_path):
    message = "at function create_ROI_JSON"
    if not isinstance(chip_type, str):
        return (None, f"[ERROR] 'chip_type' must be a string {message}.")
    if not isinstance(grating_data, list):
        return (None, f"[ERROR] 'grating_data' must be a list {message}.")
    if (
        not isinstance(target_shape, tuple)
        or len(target_shape) != 2
        or not all(isinstance(dim, int) for dim in target_shape)
    ):
        return (
            None,
            f"[ERROR] 'target_shape' must be a tuple of two integers (height, width) {message}.",
        )
    if not isinstance(rotation_angle, (int, float)):
        return (None, f"[ERROR] 'rotation_angle' must be a number {message}.")
    if not isinstance(ROI_path, Path):
        return (None, f"[ERROR] 'ROI_path' must be a pathlib.Path object {message}.")

    ROIs = {}
    try:
        if "IMECII_2" in chip_type:
            suffix = ["N", "S"]
            for g in grating_data:
                x, y = g.get("grating_origin", [None, None])
                x_size = g.get("x-size")
                y_size = g.get("y-size")
                label = g.get("label")

                if x is None or y is None or x_size is None or y_size is None or label is None:
                    continue

                if x < 0 or y < 0 or x + x_size > target_shape[1] or y + y_size > target_shape[0]:
                    continue
                ROIs[f"ROI_{label}_{suffix[0]}"] = {
                    "label": f"{label}_{suffix[0]}",
                    "flip": True,
                    "coords": [y + y_size // 2, x],
                    "size": [y_size // 2, x_size],
                }
                ROIs[f"ROI_{label}_{suffix[1]}"] = {
                    "label": f"{label}_{suffix[1]}",
                    "flip": False,
                    "coords": [y, x],
                    "size": [y_size // 2, x_size],
                }
        else:
            suffix = ["A", "B"]
            for g in grating_data:
                x, y = g.get("grating_origin", [None, None])
                x_size = g.get("x-size")
                y_size = g.get("y-size")
                label = g.get("label")

                if x is None or y is None or x_size is None or y_size is None or label is None:
                    continue

                if x < 0 or y < 0 or x + x_size > target_shape[1] or y + y_size > target_shape[0]:
                    continue
                ROIs[f"ROI_{label}_{suffix[0]}"] = {
                    "label": f"{label}_{suffix[0]}",
                    "flip": True,
                    "coords": [y, x],
                    "size": [y_size, x_size // 2],
                }
                ROIs[f"ROI_{label}_{suffix[1]}"] = {
                    "label": f"{label}_{suffix[1]}",
                    "flip": False,
                    "coords": [y, x + x_size // 2],
                    "size": [y_size, x_size // 2],
                }
        ROIs["image_angle"] = rotation_angle
        with ROI_path.open("w") as file:
            json.dump(ROIs, file, indent=4)
        return (None, None)
    except IOError as e:
        return (None, f"[ERROR] Error writing ROI JSON to '{ROI_path}' {message}: {e}")
    except Exception as e:
        return (
            None,
            f"[ERROR] An unexpected error occurred while creating the ROI JSON {message}: {e}",
        )


if __name__ == "__main__":
    """Main function to perform image alignment and feature localization."""
    # 1. Load data
    feature_location_json = Path("../config/FeatureLocation.json")
    chip_location_json = Path("../Label_templates/Chip_map_list.json")
    ROI_json = Path("../Generated_files/ROI_ChirpArray_TEST.json")

    # image_path = Path('/Volumes/krauss/Lisa/GMR/Array/250325/loc1_1/Pos0/img_000000000_Default_000.tif')
    image_path = Path(
        "/Volumes/krauss/Callum/03_Data/17_array_testing/ethanol_full_array_test_240425_flipped/image_20250424_161414.png"
    )

    image, error = load_image_and_normalise(image_path)
    if error:
        print(error)
        exit(1)

    user_chip_mapping, error = load_user_feature_locations(feature_location_json)
    if error:
        print(error)
        exit(1)

    user_chip_mapping, error = load_chip_feature_locations(chip_location_json, user_chip_mapping)
    if error:
        print(error)
        exit(1)

    # 2. Calculate angle and scale according to user's input
    result, error = chip_rotation_angle(user_chip_mapping, key="user_location")
    if error:
        print(error)
        exit(1)
    user_chip_mapping, initial_rotation_angle = result

    result, error = user_chip_scale_factor(user_chip_mapping, key="user_location")
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
    result, error = refine_feature_locations(rotated_image, user_chip_mapping)
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_locations, _ = result

    # 5. Calculate rotation-angle / scale-factor of image from locatedd the image features (not from user input locations)
    result, error = chip_rotation_angle(user_chip_mapping, key="refined_location")
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_rotation_angle = result

    # user_chip_mapping['rotation_angle'] = initial_rotation_angle + refined_rotation_angle
    result, error = user_chip_scale_factor(user_chip_mapping, key="refined_location")
    if error:
        print(error)
        exit(1)
    user_chip_mapping, refined_scale_factor = result

    # 6. Rotate image by refined rotation angle
    rotated_image, error = rotate_image(image, -user_chip_mapping["rotation_angle"])
    if error:
        print(error)
        exit(1)

    # 6. Refine feature locations again with new rotation-angle / scale-factor using template matching
    result, error = refine_feature_locations(rotated_image, user_chip_mapping)
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
        rotated_image, user_chip_mapping, template_shape, key="features"
    )

    # 10. Visualise grating location results
    visualize_features_with_matplotlib(rotated_image, grating_data, None, key="gratings")

    # # 11. Display results
    # pp = pprint.PrettyPrinter(indent=4)  # Create a PrettyPrinter object
    # print('User chip mapping:')
    # pp.pprint(user_chip_mapping)

    # 12. Create ROI JSON file
    chip_type = user_chip_mapping["chip_type"]
    rotation_angle = user_chip_mapping["rotation_angle"]
    result, error = create_ROI_JSON(
        chip_type, grating_data, rotated_image.shape, rotation_angle, ROI_json
    )
    if error:
        print(error)
        exit(1)
