#!/bin/bash

# Set the name of the virtual environment
VENV_DIR="venv"

# Set the path to the main Python script
SCRIPT_PATH="Source/xeroflow_client.py"

# --- Helper function to prompt for package installation ---
install_package() {
    local package_name="$1"
    local check_command="$2"
    local user_friendly_name="$3"

    eval "$check_command" &> /dev/null
    if [ $? -ne 0 ]; then
        echo "-----------------------------------------------------------------"
        echo "Requirement Missing: ${user_friendly_name}"
        
        local install_cmd=""
        if command -v apt-get &> /dev/null; then
            install_cmd="sudo apt-get install -y ${package_name}"
        elif command -v dnf &> /dev/null; then
            # For Fedora/CentOS, python3-devel often includes venv
            install_cmd="sudo dnf install -y python3-pip ${package_name}"
        elif command -v yum &> /dev/null; then
            install_cmd="sudo yum install -y python3-pip ${package_name}"
        elif command -v pacman &> /dev/null; then
            install_cmd="sudo pacman -S --noconfirm python-pip ${package_name}"
        else
            echo "Could not detect your package manager. Please install '${package_name}' manually."
            read -p "Press enter to exit"
            exit 1
        fi

        read -p "May I run the following command to install it? (y/n): ${install_cmd} " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Running installation command..."
            eval "$install_cmd"
            if [ $? -ne 0 ]; then
                echo "ERROR: Installation failed. Please try running the command manually."
                read -p "Press enter to exit"
                exit 1
            fi
            echo "${user_friendly_name} installed successfully."
        else
            echo "Installation declined. The application cannot continue."
            read -p "Press enter to exit"
            exit 1
        fi
        echo "-----------------------------------------------------------------"
    fi
}

echo "Checking for Python..."

if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed or not in the system's PATH."
    echo "Please install Python 3."
    read -p "Press enter to continue"
    exit 1
fi

echo "Python 3 found. Checking dependencies..."

# --- Helper function to check if venv is truly functional ---
check_venv_functional() {
    local temp_venv_dir=".temp_venv_check"
    # Attempt to create a minimal venv to test full functionality
    python3 -m venv "$temp_venv_dir" &> /dev/null
    local venv_result=$?
    # Clean up the test venv, if it was (partially) created
    if [ -d "$temp_venv_dir" ]; then
        rm -rf "$temp_venv_dir"
    fi
    return $venv_result
}

# Check for and install python3-venv and python3-pip if missing
install_package "python3-venv" "check_venv_functional" "Python's virtual environment module (venv)"
install_package "python3-pip" "python3 -m pip --version" "Python's package installer (pip)"
install_package "python3-tk" "python3 -c 'import tkinter'" "Python's GUI module (tkinter)"

# Check if the virtual environment directory exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        read -p "Press enter to continue"
        exit 1
    fi
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies."
    read -p "Press enter to continue"
    exit 1
fi

echo "Starting XeroFlow Client..."
python3 "$SCRIPT_PATH"

deactivate

echo
echo "XeroFlow Client has closed."
read -p "Press enter to continue"
