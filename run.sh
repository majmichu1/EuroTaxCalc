#!/bin/bash
# EuroTaxCalc - Launcher for Linux/macOS

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to script directory
cd "$SCRIPT_DIR"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.12 or higher."
    echo "   Visit: https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

# Install/verify dependencies (fast if already installed)
echo "⏳ Checking dependencies..."
pip3 install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies."
    read -p "Press Enter to exit..."
    exit 1
fi

# Run the application
echo "🚀 Starting EuroTaxCalc..."
python3 main.py

# Keep window open if there was an error
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Application encountered an error."
    read -p "Press Enter to exit..."
fi
