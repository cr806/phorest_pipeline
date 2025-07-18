# Guide: Mounting the UoY Network Drive

This guide explains how to connect to the shared network drive to access and store experiment data remotely.

---
### Step 1: Install Prerequisites (One-Time Setup)

Before you can mount the drive, you need to ensure the necessary tools are installed. Open a terminal and run:
```bash
sudo apt-get install cifs-utils
```

---
### Step 2: Create the Mount Point (One-Time Setup)

This is the local folder where the contents of the network drive will appear.

1.  Create a directory in the `/mnt` folder. The standard name is `storage`.
    ```bash
    sudo mkdir -p /mnt/storage
    ```

---
### Step 3: Mount the Drive

You can mount the drive either by running the provided script (recommended) or by using the manual command.

#### Option A: Using the Mount Script (Recommended)

1.  Navigate to the directory containing the script (e.g., `scripts/`).
2.  Make the script executable:
    ```bash
    chmod +x mount_UoY_network_drive.sh
    ```
3.  Run the script:
    ```bash
    ./mount_UoY_network_drive.sh
    ```
4.  When prompted, enter your university username and password. The script will handle the rest.

#### Option B: Manual Command

If you prefer to mount it manually, use the following command in the terminal. You will be prompted for your password.
```bash
sudo mount -t cifs -o username=<YOUR_USERNAME>,domain=itsyork,uid=$(id -u) //storage.york.ac.uk/physics/krauss /mnt/storage
```

---
### Step 4: Unmount the Drive

When you are finished, you can unmount the drive with this command:
```bash
sudo umount /mnt/storage
```