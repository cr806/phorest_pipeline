# Guide: Live Video Streaming for Sample Alignment

For tasks requiring precise focus and alignment, the low-framerate `continuous_capture` script can be difficult to use. This guide explains how to set up a high-framerate, low-latency video stream directly from the Raspberry Pi to a remote computer using VLC.

---
### Step 1: Start the Stream on the Raspberry Pi

1.  Open a terminal on the Raspberry Pi (either directly or via SSH).
2.  Run the following command to start the video stream. You can adjust the camera parameters to match your setup.

    ```bash
    rpicam-vid -t 0 -n --codec libav --libav-format mpegts --width 2312 --height 1736 --gain 128 --contrast 0.5 -o tcp://0.0.0.0:5555?listen=1
    ```

#### Key Command Options:
* **`-t 0`**: Sets the stream to run continuously. Press `Ctrl+C` in the terminal to stop it. (Use `-t 10000` for a 10-second test stream).
* **`-n`**: No preview (`--nopreview`). Prevents a preview window from opening on the Pi itself.
* **`--width` & `--height`**: Sets the video resolution.
* **`--gain` & `--contrast`**: Adjust these camera parameters as needed.
* **`-o tcp://0.0.0.0:5555`**: Tells the Pi to listen for incoming connections on port `5555` on all its network interfaces.

---
### Step 2: View the Stream on a Remote Machine

1.  Ensure your remote machine is on the same network as the Raspberry Pi.
2.  Open the **VLC media player** application.
3.  Go to the menu and select **Media > Open Network Stream...** (or `Ctrl+N`).
4.  Enter the network URL using the Pi's IP address and the port you chose.
    * **URL:** `tcp://<IP_ADDRESS_OF_PI>:5555`
    * **Example:** `tcp://192.168.1.2:5555`
5.  Click **Play**.

The live video stream from the Pi should now appear in VLC, allowing you to easily align and focus your sample in real-time.

---
#### Using the Stream Script (Recommended)
To make this process easier, a pre-made script is available in the `scripts` directory.

1.  Navigate to the directory containing the script.
2.  Make the script executable (you only need to do this once):
    ```bash
    chmod +x start_TCP_stream.sh
    ```
3.  Run the script to start the stream:
    ```bash
    ./start_TCP_stream.sh
    ```