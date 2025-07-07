On the raspberry pi:
- Open a terminal
- Run the following command:
  `rpicam-vid -t 10000 -n --codec libav --libav-format mpegts --width 2312 --height 1736 --gain 128 --contrast 0.5 -o tcp://0.0.0.0:5555?listen=1`

  Note:
  - `-t 10000` - 10 second stream
  - `-t 0` - continuous stream, end stream by pressing <ctrl-c>
  - `tcp://0.0.0.0:5555` - '0.0.0.0' Pi's IP address, '5555' port to stream to

On the remote machine:
- Using VLC:
  - Click <Open> -> <Network>
  - Enter URL: `tcp://<IP_ADDR_OF_PI>:<CHOSEN_PORT>`
  - Click <Open>