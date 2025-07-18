#!/usr/bin/env bash

MOUNT_POINT="/mnt/storage"
NETWORK_ADDR="//storage.york.ac.uk/physics/krauss"
USED_UID=$(id -u)

if [ ! -d "$MOUNT_POINT" ]; then
    echo "Error: Mount point '$MOUNT_POINT' does not exist."
    echo "Please create it first - sudo mkdir -p $MOUNT_POINT"
    exit 1
fi

read -p "Enter your University username: " user_name

if [ -z "$user_name" ]; then
    echo "ERROR: No username entered. Aborting."
    exit 1
fi

if ! [[ "$user_name" =~ [[:alpha:]] && "$user_name" =~ [[:digit:]] ]]; then
    echo "Error: Badly formed username. It must contain both letters and numbers."
    exit 1
fi

echo "Attempting to mount '$NETWORK_ADDR' to '$MOUNT_POINT' for user '$user_name'..."

sudo mount -t cifs -o username="$user_name",domain=itsyork,uid=$USED_UID $NETWORK_ADDR "$MOUNT_POINT"

# Check if the mount was successful
if [ $? -eq 0 ]; then
	echo "Storage drive mounted successfully"
else
	echo "Failed to mount Storage."
fi