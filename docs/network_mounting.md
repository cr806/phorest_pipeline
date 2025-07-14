Install pre-requisites:
`sudo apt-get install cifs-utils`

Mount a drive:
`sudo mount -t cifs -o username=<UNIVERSITY_USERNAME>,domain=itsyork,uid=<UID_HERE> //storage.york.ac.uk/physics/krauss /mnt/storage`

Unmount a drive:
`sudo umount /home/chris/mnt/storage`
