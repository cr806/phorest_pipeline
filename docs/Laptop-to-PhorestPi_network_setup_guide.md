# Guide: Setting Up a Direct Network Connection

This guide explains how to create a direct, "air-gapped" network connection between the Raspberry Pi and a laptop using an Ethernet cable. This is useful for running the analsys pipeline in environments without access to a local network.

**Note:** This setup assigns a static IP to the Pi's Ethernet port. It might be worth considering the use of the Pi's Wi-Fi interface to connect to the main local network and then dedicate the Ethernet interface solely for this direct connection. This would allow access to the Pi via either network without changing settings.  However, consideration must be made if there is a local requirement for Wi-Fi interfaces to be disabled.

---
### Step 1: Configure the Raspberry Pi

We will use the Network Manager TUI (`nmtui`) to create a new, dedicated network profile with a static IP address.

1.  Connect to your Raspberry Pi (either directly with a screen and keyboard or via SSH over your existing network).
2.  Open the Network Manager by running:
    ```bash
    sudo nmtui
    ```
3.  Using the arrow keys, navigate to **`Edit a connection`** and press `Enter`.
4.  Select **`Add`** on the left-hand side.
5.  Choose **`Ethernet`** from the list and select **`Create`**.
6.  Fill in the profile details as follows:
    * **Profile name:** `Pi Direct Connection` (or another memorable name)
    * **Device:** `eth0`
    * **IPv4 CONFIGURATION:** Change from `<Automatic>` to **`<Manual>`**.
    * Select the **`<Show>`** button next to IPv4 CONFIGURATION to reveal the address fields.
7.  In the **Addresses** section, select **`<Add...>`** and enter:
    * `192.168.1.2/24`
8.  Leave all other fields (Gateway, DNS, etc.) blank.
9.  Ensure the following checkboxes are ticked at the bottom:
    * `[X] Automatically connect`
    * `[X] Available to all users`
10. Navigate to **`<OK>`** and press `Enter` to save.
11. Back in the main `nmtui` screen, select **`Quit`**.

---
### Step 2: Configure the Laptop

Next, we'll create a corresponding static IP profile on the laptop.

> **A Note on IP Addresses:** For a direct connection to work, both devices must be on the same subnet (e.g., `192.168.1.x`) but must have a **different** final number. We typically assign `.1` to the primary unit (the laptop) and `.2` to the secondary unit (the Pi). You will need to remember the Pi's address (`192.168.1.2`) to connect to it via SSH.


1.  Open your system's `Settings` and navigate to the `Network` panel.
2.  Under the **`Wired`** connection section, click the `+` icon to add a new profile.
3.  In the new profile window:
    * Give the connection a memorable name, like `Pi Direct Connection`.
    * Go to the **`IPv4`** tab.
    * Change the **`IPv4 Method`** to **`Manual`**.
4.  In the **Addresses** section, fill in the following:
    * **Address:** `192.168.1.1`
    * **Netmask:** `255.255.255.0`
5.  Leave the Gateway field blank.
6.  Click **`Add`** or **`Apply`** to save the new profile.

---
### Step 3: Connect and Test

1.  Connect the Raspberry Pi and the laptop directly using an Ethernet cable.
2.  The new `Pi Direct Connection` profile on your laptop should become active automatically.
3.  You can now connect to the Pi from your laptop's terminal using its static IP address:
    ```bash
    ssh pi@192.168.1.2
    ```