from pathlib import Path
import shutil


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
    
def clear_and_create_directory_with_error_handling(directory_path: Path):
    message = "at function create_directory_with_error_handling"
    try:
        if directory_path.is_dir():
            for item in directory_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        directory_path.mkdir(parents=True, exist_ok=True)
        return (None, None)
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