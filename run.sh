#!/bin/bash

# Set script to exit on error
set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
echo "Script directory: $SCRIPT_DIR"
cd "$SCRIPT_DIR"
echo "Current working directory: $(pwd)"

# Define the virtual environment directory
VENV_DIR="venv"
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"

# Debug info
echo "Looking for virtual environment at: $VENV_DIR"
echo "Looking for activation script at: $ACTIVATE_SCRIPT"
ls -la .

# Check if the virtual environment exists but is incomplete
if [ -d "$VENV_DIR" ] && [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "Virtual environment directory exists but seems incomplete."
    echo "Removing incomplete virtual environment and recreating it..."
    rm -rf "$VENV_DIR"
fi

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    
    # Check if virtual environment was created successfully
    if [ ! -d "$VENV_DIR" ] || [ ! -f "$ACTIVATE_SCRIPT" ]; then
        echo "Failed to create virtual environment."
        echo "Please ensure python3-venv is installed:"
        echo "sudo apt-get install python3-venv"
        exit 1
    fi
fi

# Check if the activate script exists
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "Activation script not found at $ACTIVATE_SCRIPT"
    echo "This is unusual. Let's try to fix it by creating a new virtual environment..."
    
    # Try to create the virtual environment again
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    
    if [ ! -f "$ACTIVATE_SCRIPT" ]; then
        echo "Still couldn't create a proper virtual environment."
        echo "Please run: sudo apt-get install python3-venv"
        echo "Then try again."
        exit 1
    fi
fi

# Activate the virtual environment
echo "Activating the virtual environment using: $ACTIVATE_SCRIPT"
source "$ACTIVATE_SCRIPT"

# Upgrade pip and install wheel
echo "Upgrading pip and installing wheel..."
pip install --upgrade pip wheel

# Install required packages if needed
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
fi

# Ensure langchain packages are properly installed
echo "Checking langchain packages..."
if ! pip show langchain-core &> /dev/null || ! pip show langchain-community &> /dev/null; then
    echo "Installing or upgrading langchain packages..."
    pip uninstall -y langchain langchain-core langchain-community || true
    pip install --upgrade langchain-core
    pip install --upgrade langchain-community
    pip install --upgrade langchain
fi

# Verify Python is available in the virtual environment
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "Python not found in the virtual environment."
    echo "Try running setup.sh again to fix this issue."
    exit 1
fi

# Determine which Python command to use
PYTHON_CMD="python"
if ! command -v python &> /dev/null && command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
fi

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "main.py not found in $(pwd)"
    echo "Make sure you're running this script from the XeroFlow directory."
    echo "Files in current directory:"
    ls -la
    if [ -n "$VIRTUAL_ENV" ]; then
        deactivate || true
    fi
    exit 1
fi

# Run the main.py program
echo "Running main.py using $PYTHON_CMD..."
$PYTHON_CMD main.py

# Deactivate the virtual environment after running the program
echo "Deactivating the virtual environment..."
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate || true
else
    echo "Virtual environment was not properly activated."
fi

echo "Done."
