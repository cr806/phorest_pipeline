# src/process_pipeline/shared/config.py
import sys
import tomllib
from pathlib import Path

from phorest_pipeline.shared.communication_methods import CommunicationMethod
from phorest_pipeline.shared.image_sources import (
    ImageSourceType,
    ImageTransform,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

CONFIG_FILEPATH = Path(PROJECT_ROOT, "configs", "Phorest_config.toml")

METADATA_FILENAME = Path("metadata_manifest.json")
RESULTS_FILENAME = Path("processing_results.jsonl")

CSV_FILENAME = Path("communicating_results.csv")
IMAGE_FILENAME = Path("processed_data_plot.png")


def load_config():
    if not CONFIG_FILEPATH.is_file():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILEPATH}")

    try:
        with CONFIG_FILEPATH.open("rb") as f:
            config = tomllib.load(f)
        return config
    except tomllib.TomlDecodeError as e:
        raise ValueError(f"Error decoding TOML config file '{CONFIG_FILEPATH}': {e}") from e
    except Exception as e:
        raise IOError(
            f"An unexpected error occurred reading config file '{CONFIG_FILEPATH}': {e}"
        ) from e


def get_path(config: dict, section_name: str, key: str, fallback: str) -> Path:
    """Gets the full path from a key in config, within a specified section."""
    # .get() on a dict handles missing sections/keys gracefully
    value = config.get(section_name, {}).get(key, fallback)
    return Path(value)


def get_flag_path(config: dict, flag_name_key: str) -> Path:
    """Gets the full path for a flag file."""
    flag_dir = get_path(config, "Paths", "flag_dir", "flags")  # Now specify section for get_path
    flag_filename = config.get("Flags", {}).get(flag_name_key)  # Access directly from dict
    if not flag_filename:
        raise ValueError(f"Flag key '{flag_name_key}' not found in config [Flags]")
    return Path(flag_dir, flag_filename)


def check_or_create_dir(path: Path):
    """Checks if a directory exists, and creates it if not."""
    if not path.is_dir():
        try:
            path.mkdir(parents=True, exist_ok=True)
            print(f"[CONFIG] Created directory: {path}")
        except Exception as e:
            print(f"[CONFIG] Error creating directory {path}: {e}")
            sys.exit(1)
    else:
        print(f"[CONFIG] Directory already exists: {path}")


# Load config once on import
try:
    settings = load_config()  # settings is now a dictionary

    # --- Data analysis ---
    METHOD = settings.get("Data_Analysis", {}).get("method", "gaussian")
    NUMBER_SUB_ROIS = int(settings.get("Data_Analysis", {}).get("number_of_subROIs", 1))

    # --- Paths ---
    REMOTE_ROOT_DIR = get_path(settings, "Paths", "remote_root_dir", "remote")
    ROOT_DIR = get_path(settings, "Paths", "root_dir", ".")
    DATA_DIR = get_path(settings, "Paths", "data_dir", "data")
    CONTINUOUS_DIR = get_path(settings, "Paths", "continuous_capture_dir", "continuous_capture")
    RESULTS_DIR = get_path(settings, "Paths", "results_dir", "results")
    LOGS_DIR = get_path(settings, "Paths", "logs_dir", "logs")
    BACKUP_DIR = get_path(settings, "Paths", "backup_dir", "backup")

    DATA_DIR = Path(ROOT_DIR, DATA_DIR)
    RESULTS_DIR = Path(ROOT_DIR, RESULTS_DIR)
    LOGS_DIR = Path(ROOT_DIR, LOGS_DIR)
    BACKUP_DIR = Path(ROOT_DIR, BACKUP_DIR)

    check_or_create_dir(DATA_DIR)
    check_or_create_dir(CONTINUOUS_DIR)
    check_or_create_dir(RESULTS_DIR)
    check_or_create_dir(LOGS_DIR)
    check_or_create_dir(BACKUP_DIR)

    # --- Service Availability ---
    ENABLE_CAMERA = settings.get("Services", {}).get("enable_camera", False)
    ENABLE_THERMOCOUPLE = settings.get("Services", {}).get("enable_thermocouple", False)
    ENABLE_BRIGHTFIELD = settings.get("Services", {}).get("enable_brightfield", False)
    ENABLE_BACKUP = settings.get("Services", {}).get("enable_file_backup", False)
    ENABLE_COMPRESSOR = settings.get("Services", {}).get("enable_image_compression", False)
    ENABLE_SYNCER = settings.get("Services", {}).get("enable_remote_sync", False)


    # --- Timing ---
    # No need for getint/getboolean, TOML parses types directly
    COLLECTOR_INTERVAL = settings.get("Timing", {}).get("collector_interval_seconds", 300)
    PROCESSOR_INTERVAL = settings.get("Timing", {}).get("processor_interval_seconds", 2)
    COMMUNICATOR_INTERVAL = settings.get("Timing", {}).get("communicator_interval_seconds", 60)
    COMPRESSOR_INTERVAL = settings.get("Timing", {}).get("compress_interval_seconds", 3600)
    POLL_INTERVAL = settings.get("Timing", {}).get("poll_interval_seconds", 2)
    RETRY_DELAY = settings.get("Timing", {}).get("collector_retry_delay_seconds", 2)
    FILE_BACKUP_INTERVAL = settings.get("Timing", {}).get("file_backup_interval_seconds", 3600)
    SYNC_INTERVAL = settings.get("Timing", {}).get("sync_interval_seconds", 3600)

    # --- Retries ---
    FAILURE_LIMIT = settings.get("Retries", {}).get("collector_failure_limit", 5)

    # --- Buffer ---
    IMAGE_BUFFER_SIZE = settings.get("Buffer", {}).get("image_buffer_size", 300)

    # --- Communication Settings ---
    communication_method_str = settings.get("Communication", {}).get("method", "CSV_PLOT")
    communication_method_str = communication_method_str.upper()
    try:
        COMMUNICATION_METHOD = CommunicationMethod[communication_method_str]
    except KeyError:
        print(f"[CONFIG] Invalid communication method: {communication_method_str}.")
        print(f"Please use one of {', '.join(CommunicationMethod.__members__.keys())}")
        exit(1)

    # --- Camera Settings ---
    camera_type_str = settings.get("Camera", {}).get("camera_type", "DUMMY")
    camera_type_str = camera_type_str.upper()
    try:
        CAMERA_TYPE = ImageSourceType[camera_type_str]
    except KeyError:
        print(f"[CONFIG] Invalid camera type: {camera_type_str}.")
        print(f"Please use one of {', '.join(ImageSourceType.__members__.keys())}")
        exit(1)
    CAMERA_INDEX = int(settings.get("Camera", {}).get("camera_id", 0))
    CAMERA_EXPOSURE = int(settings.get("Camera", {}).get("camera_exposure", 150))
    CAMERA_GAIN = int(settings.get("Camera", {}).get("camera_gain", 32))
    CAMERA_BRIGHTNESS = int(settings.get("Camera", {}).get("camera_brightness", 128))
    CAMERA_CONTRAST = int(settings.get("Camera", {}).get("camera_contrast", 32))

    camera_transform_str = settings.get("Camera", {}).get("camera_transform", "NONE")
    camera_transform_str = camera_transform_str.upper()
    try:
        CAMERA_TRANFORM = ImageTransform[camera_transform_str]
    except KeyError:
        print(f"[CONFIG] Invalid camera image transform: {camera_transform_str}.")
        print(f"Please use one of {', '.join(ImageTransform.__members__.keys())}")
        exit(1)

    # --- Temperature Settings ---
    THERMOCOUPLE_IDS = settings.get("Temperature", {}).get("thermocouple_sensors", {})

    # --- Brightfield Settings ---
    BRIGHTFIELD_CAMERA_INDEX = int(settings.get("Brightfield", {}).get("camera_id", 1))


    # --- Advanced config entries ---
    # --- Flags ---
    DATA_READY_FLAG = get_flag_path(settings, "data_ready")
    RESULTS_READY_FLAG = get_flag_path(settings, "results_ready")

    # --- Static Asset Paths ---
    ROI_GENERATION_IMAGE_PATH = Path(
        PROJECT_ROOT, settings.get("Assets", {}).get("roi_generation_image")
    )
    LABEL_TEMPLATE_DIR = Path(PROJECT_ROOT, settings.get("Assets", {}).get("label_template_dir"))
    FEATURE_LOCATIONS_CONFIG_PATH = Path(
        PROJECT_ROOT, settings.get("Assets", {}).get("feature_locations_config")
    )
    ROI_MANIFEST_FILENAME = Path(
        settings.get("Assets", {}).get("roi_manifest_filename", "ROI_manifest.json")
    )
    GENERATED_FILES_DIR = Path(PROJECT_ROOT, settings.get("Assets", {}).get("generated_files_dir"))

    # --- Development Settings ---
    DEBUG_MODE = settings.get("Development", {}).get("debug_mode", False)

except (FileNotFoundError, ValueError, IOError) as e:
    print(f"FATAL ERROR loading/parsing configuration: {e}")
    sys.exit(1)
