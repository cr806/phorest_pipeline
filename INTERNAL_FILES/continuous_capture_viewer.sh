#!/bin/bash
IMAGE_PATH="~sftp://phorest@192.168.1.2/home/phorest/Documents/Python/phorest_pipeline/continuous_capture/continuous_capture_frame.jpg"

feh --reload 1 --zoom fill --title "Live Image" "$IMAGE_PATH" &

ifnotifywait -m -e close_write "$IMAGE_PATH" | while read path action file; do
    echo "File changed: $file"
done
