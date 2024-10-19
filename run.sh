#!/bin/bash

# Define the virtual environment directory
VENV_DIR="venv"

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found, creating one..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        exit 1
    fi
fi

# Activate the virtual environment
echo "Activating the virtual environment..."
source "$VENV_DIR/bin/activate"

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "main.py not found."
    deactivate
    exit 1
fi

# Run the main.py program
echo "Running main.py..."
python main.py

# Deactivate the virtual environment after running the program
echo "Deactivating the virtual environment..."
deactivate
