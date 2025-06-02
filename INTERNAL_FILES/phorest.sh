#!/bin/bash

cd /home/phorest/Documents/Python/phorest_pipeline || { echo "[ERROR] Project directory can not be found."; exit 1; }

exec uv run phorest.py "$@" 
