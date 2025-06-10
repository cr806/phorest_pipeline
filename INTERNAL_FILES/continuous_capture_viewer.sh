#!/bin/bash
UoY='144.32.82.24'
BIC='192.168.1.2'
IMAGE_PATH="~sftp://phorest@$UoY/home/phorest/Documents/Python/phorest_pipeline/continuous_capture/continuous_capture_frame.jpg"

feh --reload 1 --zoom fill --title "Live Image" "$IMAGE_PATH" &

ifnotifywait -m -e close_write "$IMAGE_PATH" | while read path action file; do
    echo "File changed: $file"
done
