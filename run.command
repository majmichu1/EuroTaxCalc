#!/bin/bash
# EuroTaxCalc - Launcher for macOS

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to script directory
cd "$SCRIPT_DIR"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    osascript -e 'display alert "Python 3 is not installed. Please install Python 3.12 or higher." message "Visit: https://www.python.org/downloads/" buttons {"OK"} default button 1'
    exit 1
fi

# Install/verify dependencies (fast if already installed)
pip3 install -r requirements.txt -q
if [ $? -ne 0 ]; then
    osascript -e 'display alert "Failed to install dependencies." buttons {"OK"} default button 1'
    exit 1
fi

# Run the application
python3 main.py
