#!/bin/bash
# Install the required libgdal version
sudo apt-get update && sudo apt-get install -y gdal-bin libgdal-dev

# Proceed with the usual pip installation
pip install -r requirements.txt
