## Use a copy of this file in the root directory to run a script
## that is buried within the TUI


import subprocess
from pathlib import Path
import sys
import os
PROJECT_ROOT = Path(__file__).resolve().parent

full_script_path = Path(PROJECT_ROOT, 'src', 'prepare_files_for_image_analysis.py')

# Prepare environment variables for the subprocess
env = os.environ.copy()
if "PYTHONPATH" in env:
    env["PYTHONPATH"] = f"{PROJECT_ROOT}{os.pathsep}{env['PYTHONPATH']}"
else:
    env["PYTHONPATH"] = str(PROJECT_ROOT) # Convert Path to string for environment variable

result = subprocess.run(
            [sys.executable, str(full_script_path)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=str(PROJECT_ROOT)
        )

all_output_lines = []
if result.stdout:
    all_output_lines.append(f"--- (STDOUT) ---")
    all_output_lines.extend(result.stdout.splitlines())
if result.stderr:
    all_output_lines.append(f"\n--- (STDERR) ---")
    all_output_lines.extend(result.stderr.splitlines())

print("\n".join(all_output_lines))