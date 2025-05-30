# Setting up the PhorestPi-ARGUSLaptop Network

## PhorestPi
- Connect to pi using ssh, or directly with screen/keyboard/mouse
- Enter command `sudo nmtui` (in terminal window if connected directly) to open the Network Manager TUI
  - We require a static IP for the connection between the laptop and the pi to work correctly.

- Create a new connection by:
  `Edit a connection` -> `Add`
- Give the new connection a name e.g. 'Pi Direct Connection'
- Enter the following details:
  Device = 'eth0'
  IPv4 CONFIGURATION = <Show>
    Addresses = 192.168.1.2/24
    NB: Leave all other fields blank
- Ensure: 'Automatically connect' and 'Available to all users' are ticked
- <Ok>

- Activate new connection, select 'Activate a connection' select the new connection and activate

## ARGUS laptop
- Open 'Settings' -> 'Network'
- As above we require a static IP address, we will choose 192.168.1.1 (both the pi and laptop must be on the same subnet)
- Under 'Wired' click the '+' (top right)
  - Give the new connection a name e.g. 'Pi Direct Connection'
  - Under the 'IPv4' tab, select 'Manual' as the method
  - In the 'Addresses' table:
    - Enter 192.168.1.1 in the address column
    - Enter 255.255.255.0 into the Netmask column
  - Leave other tables blank, click 'Add'

- When the pi is connected to the laptop, this connection should automatically become active.

NB: this automatic switching between static and DHCP does not seem to work on the pi.