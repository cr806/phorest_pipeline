# Guide: Auto-Mounting a USB Drive on Raspberry Pi

This guide explains how to configure your Raspberry Pi to automatically and reliably mount a USB drive every time it boots. This is the recommended setup for storing your data.

---
### Step 1: Find Your Drive and User Information

First, we need to gather two key pieces of information: the unique ID of your USB drive and your personal user ID.

1.  **Find the Drive's UUID**:
    * Plug your USB drive into the Raspberry Pi.
    * Open a terminal and run the following command:
        ```bash
        sudo blkid
        ```
    * Look for the line corresponding to your USB drive (it might be `/dev/sda1` or similar). Copy the `UUID` value. It will look something like `UUID="BB92-0AA4"`.

2.  **Find Your User ID (UID) and Group ID (GID)**:
    * In the same terminal, run the `id` command:
        ```bash
        id
        ```
    * Note your `uid` and `gid` numbers. For the default user, this is typically `1000`.

---
### Step 2: Create the Mount Point

This is the folder on the Pi where the contents of the USB drive will appear.

1.  Create a directory in the `/mnt` folder. You can name it whatever you like (e.g., `phorest_data`).
    ```bash
    sudo mkdir -p /mnt/phorest_data
    ```

---
### Step 3: Edit `fstab` for Persistent Mounting

The `/etc/fstab` file tells the operating system which drives to mount at boot time.

1.  Open the file with `nano`, a simple text editor:
    ```bash
    sudo nano /etc/fstab
    ```
2.  Go to the very bottom of the file and add the following new line. **Be sure to replace the placeholder values with the `UUID`, `uid`, and `gid` you found in Step 1.**

    ```
    UUID=<UUID OF USB DRIVE HERE> /mnt/phorest_data vfat defaults,nofail,uid=<USER ID>,gid=<USER ID>,umask=002 0 0
    ```
    * **Example:** `UUID=BB92-0AA4 /mnt/phorest_data vfat defaults,nofail,uid=1000,gid=1000,umask=002 0 0`

3.  Save the file and exit `nano` by pressing `Ctrl+X`, then `Y`, then `Enter`.

---
### Step 4: Test and Reboot

1.  To test that your `fstab` entry is correct without rebooting, run the mount command:
    ```bash
    sudo mount -a
    ```
    If no errors appear, the drive is mounted. You can check its contents with `ls /mnt/phorest_data`.

2.  Reboot the Raspberry Pi to confirm it works automatically.
    ```bash
    sudo reboot
    ```

Your USB drive will now be reliably mounted at `/mnt/phorest_data` every time you start your Pi.