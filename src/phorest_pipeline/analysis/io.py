import json
import tomllib
from pathlib import Path

import numpy as np

from phorest_pipeline.analysis.matching import (
    get_type_of_chip,
    get_user_label_locations_from_chip_map,
    offset_and_scale_grating_data,
)


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

    chip_type = user_raw_data.get("chip_type")
    if chip_type is None:
        return (None, f"[ERROR] Missing 'chip_type' in user feature data {message}.")
    user_chip_mapping["chip_type"] = chip_type

    user_features = user_raw_data.get("features")
    if user_features is None:
        return (None, f"[ERROR] Missing 'features' list in user feature data {message}.")

    features = []
    for feature in user_features:
        label_name = feature.get("label")
        if label_name is None:
            return (None, f"[ERROR] Missing 'label' in a feature entry {message}.")

        feature_location = feature.get("feature_location")
        if feature_location is None:
            return (
                None,
                f"[ERROR] Missing 'feature_location' in a feature entry {message}.",
            )
        # Ensure feature_location is a list/tuple as expected, if not already
        if not isinstance(feature_location, (list, tuple)):
            return (
                None,
                f"[ERROR] 'feature_location' for label '{label_name}' is not a list or tuple {message}.",
            )

        features.append({"label": label_name, "user_location": feature_location})

    user_chip_mapping["features"] = features
    return (user_chip_mapping, None)


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
