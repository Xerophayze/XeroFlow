#!/usr/bin/env bash
# setup.sh
# This script checks for Python, pip, git, and CUDA (if necessary),
# clones or updates the XeroFlow repository, sets up a virtual environment,
# installs all required dependencies, and installs either the CPU-only or CUDA-enabled version of PyTorch.

set -e

# Function to install Python and necessary packages
install_python() {
    echo "Installing Python and necessary packages..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3 python3-venv python3-pip
    elif command -v pacman &> /dev/null; then
        sudo pacman -Syu --noconfirm python python-pip
    else
        echo "Unsupported package manager. Please install Python manually."
        exit 1
    fi
}

# Function to install tkinter
install_tkinter() {
    echo "Installing tkinter..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get install -y python3-tk
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-tkinter
    elif command -v pacman &> /dev/null; then
        sudo pacman -Syu --noconfirm tk
    else
        echo "Unsupported package manager. Please install tkinter manually."
        exit 1
    fi
}

# Function to install pip3 via the system package manager
install_pip3() {
    echo "Installing pip3 via package manager..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-pip
    elif command -v pacman &> /dev/null; then
        sudo pacman -Syu --noconfirm python-pip
    else
        echo "Unsupported package manager. Please install pip3 manually."
        exit 1
    fi
}

# Function to install git
install_git() {
    echo "Installing git..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y git
    elif command -v yum &> /dev/null; then
        sudo yum install -y git
    elif command -v pacman &> /dev/null; then
        sudo pacman -Syu --noconfirm git
    else
        echo "Unsupported package manager. Please install git manually."
        exit 1
    fi
}

# Function to check for CUDA
check_cuda() {
    if command -v nvidia-smi &> /dev/null; then
        echo "CUDA-capable GPU detected."
        return 0  # CUDA detected
    else
        echo "No CUDA-capable GPU detected. Installing CPU-only version of PyTorch."
        return 1  # No CUDA detected
    fi
}

# Check for Python3
if ! command -v python3 &> /dev/null
then
    echo "Python3 not found."
    install_python
else
    echo "Python3 is already installed."
fi

# Check for pip3
if ! command -v pip3 &> /dev/null
then
    echo "pip3 not found."
    install_pip3
else
    echo "pip3 is already installed."
fi

# Check for git
if ! command -v git &> /dev/null
then
    echo "git not found."
    install_git
else
    echo "git is already installed."
fi

# Check for tkinter
if ! python3 -c "import tkinter" &> /dev/null
then
    echo "tkinter not found."
    install_tkinter
else
    echo "tkinter is already installed."
fi

# Clone or update the repository
REPO_URL="https://github.com/Xerophayze/XeroFlow.git"
REPO_DIR="XeroFlow"

if [ -d "$REPO_DIR/.git" ]; then
    echo "Repository already exists. Pulling latest changes..."
    cd "$REPO_DIR"
    git pull
else
    echo "Cloning the repository..."
    git clone "$REPO_URL"
    cd "$REPO_DIR"
fi

# Set up the virtual environment
VENV_DIR="venv"

# Install python3-venv if necessary
if ! python3 -m venv "$VENV_DIR" &> /dev/null; then
    echo "Installing python3-venv..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get install -y python3-venv
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-venv
    elif command -v pacman &> /dev/null; then
        sudo pacman -Syu --noconfirm python-virtualenv
    else
        echo "Unsupported package manager. Please install python3-venv manually."
        exit 1
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment
echo "Activating the virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip and install wheel
echo "Upgrading pip and installing wheel..."
pip install --upgrade pip wheel

# Install numpy without strict version constraint
echo "Installing numpy..."
pip install numpy

# Check for CUDA and install the correct version of PyTorch
if check_cuda; then
    echo "Installing PyTorch with CUDA support..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
else
    echo "Installing CPU-only version of PyTorch..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
fi

# Attempt to install faiss-cpu if available (optional)
echo "Attempting to install faiss-cpu..."
pip install faiss-cpu || echo "Warning: faiss-cpu installation failed. Skipping faiss-cpu installation."

# Install additional dependencies from requirements.txt
if [ -f "requirements.txt" ]; then
    echo "Installing additional dependencies from requirements.txt..."
    pip install -r requirements.txt --no-deps
else
    echo "requirements.txt not found. Skipping additional dependencies installation."
fi

# Ensure langchain_community is installed
echo "Checking if langchain_community is installed..."
if ! pip show langchain_community &> /dev/null
then
    echo "langchain_community not found. Installing..."
    pip install langchain-community
else
    echo "langchain_community is already installed."
fi

# Inform user of successful setup
echo
echo "Setup completed successfully!"
echo "You can now run the application by executing run.sh."
echo

# Deactivate the virtual environment
echo "Deactivating virtual environment..."
deactivate

echo "Done."
