#!/usr/bin/env bash

MOUNT_POINT="/mnt/storage"

if [ ! -d "$MOUNT_POINT" ]; then
    echo "Error: Mount point '$MOUNT_POINT' does not exist."
    echo "Please create it first - sudo mkdir -p $MOUNT_POINT"
    exit 1
fi

echo "Mounting 'storage' to '$MOUNT_POINT'"
sudo mount -t cifs -o username=cr806,domain=itsyork,uid=1000 //storage.york.ac.uk/physics/krauss "$MOUNT_POINT"

# Check if the mount was successful
if [ $? -eq 0 ]; then
	echo "Storage drive mounted successfully"
else
	echo "Failed to mount Storage."
fi