#!/usr/bin/env bash

# A script to find and display all running Phorest Pipeline processes.

echo "--- Active Phorest Pipeline Services ---"

# 1. 'ps aux' lists all running processes.
# 2. 'grep '[p]horest-'' filters for lines containing 'phorest-', excluding the grep process itself.
# 3. 'awk' processes each matching line:
#    - It takes the second column as the PID.
#    - It takes the last column (the full command path) as the command.
#    - It strips the path from the command to get just the executable name.
#    - It prints the formatted PID and command name.
ps aux | grep '[p]horest-' | awk '{
    pid = $2
    command = $NF
    sub(".*/", "", command)
    printf "PID: %-8s Command: %s\n", pid, command
}'

echo "----------------------------------------"