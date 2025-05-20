## USB information

Obtain these by running `sudo blkid`
- UUID="BB92-0AA4"
- BLOCK_SIZE="512"
- TYPE="vfat"

## User account information
Obtain these by running `id` look for your username
labuser:
- User ID (UID) 1000
- Group ID (GID) 1000

## Edit fstab for persisent USB drive mounting

Enter the following line at the bottom of the fstab
1. `sudo nano /etc/fstab`
2. Enter this line at bottom of table replacing place-holders as neccessary:
 `UUID=<UUID OF USB DRIVE HERE> /mnt/ARGUS_data vfat defaults,nofail,uid=<USED ID>,gid=<USER ID>,umask=002 0 0`
3. Save and close
4. Reboot Pi `sudo reboot`