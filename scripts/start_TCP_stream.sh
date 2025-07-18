#!/usr/bin/env bash

# A script to start a live video stream from the Raspberry Pi camera for remote viewing.

# --- Camera & Stream Configuration ---
WIDTH=2312
HEIGHT=1736
GAIN=128
CONTRAST=0.5
PORT=5555

# --- Main Command ---
echo "Starting camera stream on tcp://0.0.0.0:$PORT"
echo "View the stream in VLC at: tcp://<PI_IP_ADDRESS>:$PORT"
echo "Press Ctrl+C to stop the stream."

rpicam-vid \
    -t 0 \
    -n \
    --codec libav \
    --libav-format mpegts \
    --width "$WIDTH" \
    --height "$HEIGHT" \
    --gain "$GAIN" \
    --contrast "$CONTRAST" \
    -o "tcp://0.0.0.0:$PORT?listen=1"

echo "Stream stopped."