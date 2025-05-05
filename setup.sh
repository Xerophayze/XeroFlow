#!/usr/bin/env bash
# setup.sh
# This script checks for Python, pip, git, and CUDA (if necessary),
# clones or updates the XeroFlow repository, sets up a virtual environment,
# installs all required dependencies, and installs either the CPU-only or CUDA-enabled version of PyTorch.

set -e

# Function to check Python version
check_python_version() {
    if command -v python3 &> /dev/null; then
        version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if [[ "$version" == "3.10" ]]; then
            return 0
        fi
    fi
    return 1
}

# Function to wait for user input
wait_for_input() {
    echo
    read -n 1 -s -r -p "Press any key to continue..."
    echo
}

# Function to open a URL in the default browser
open_url() {
    url="$1"
    echo "Opening $url in your default browser..."
    
    if command -v xdg-open &> /dev/null; then
        xdg-open "$url" &> /dev/null &
    elif command -v open &> /dev/null; then
        open "$url" &> /dev/null &
    else
        echo "Could not open the URL automatically. Please visit:"
        echo "$url"
    fi
}

# Function to install Python and necessary packages
install_python() {
    echo "Installing Python and necessary packages..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3.10 python3.10-venv python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python310 python310-venv python3-pip
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

# Function to install pip3
install_pip3() {
    echo "Installing pip3..."
    
    # Detect OS type
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        echo "Detected macOS system"
        if command -v brew &> /dev/null; then
            echo "Using Homebrew to install pip..."
            brew install python3  # This also installs pip3
        else
            echo "Homebrew not found. Using ensurepip module..."
            python3 -m ensurepip --upgrade
            python3 -m pip install --upgrade pip
        fi
    else
        # Linux
        echo "Detected Linux system"
        if command -v apt-get &> /dev/null; then
            echo "Using apt to install pip..."
            sudo apt-get update
            sudo apt-get install -y python3-pip
        elif command -v yum &> /dev/null; then
            echo "Using yum to install pip..."
            sudo yum install -y python3-pip
        elif command -v dnf &> /dev/null; then
            echo "Using dnf to install pip..."
            sudo dnf install -y python3-pip
        elif command -v pacman &> /dev/null; then
            echo "Using pacman to install pip..."
            sudo pacman -Syu --noconfirm python-pip
        elif command -v zypper &> /dev/null; then
            echo "Using zypper to install pip..."
            sudo zypper install -y python3-pip
        else
            echo "No package manager found. Using get-pip.py method..."
            # Use get-pip.py as a fallback method
            curl -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py
            python3 get-pip.py
            rm get-pip.py
        fi
    fi
    
    # Verify pip installation
    if command -v pip3 &> /dev/null; then
        echo "pip3 has been successfully installed."
        return 0
    else
        echo "Failed to install pip3. Please install it manually."
        return 1
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

# Check for Python 3.10
echo "Checking for Python 3.10..."
if ! check_python_version; then
    echo "Python 3.10 is required but not found."
    echo "Would you like to be directed to the Python download page? (y/n)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        PYTHON_DOWNLOAD_URL="https://www.python.org/downloads/"
        open_url "$PYTHON_DOWNLOAD_URL"
        echo "Please download and install Python 3.10 from the website."
        echo "Be sure to check 'Add Python to PATH' during installation."
        echo
    fi
    
    echo "For Ubuntu/Debian:"
    echo "  sudo add-apt-repository ppa:deadsnakes/ppa"
    echo "  sudo apt update"
    echo "  sudo apt install python3.10 python3.10-venv python3-pip"
    echo
    echo "For other systems, please refer to your package manager's documentation"
    echo "or visit https://www.python.org/downloads/"
    wait_for_input
    exit 1
else
    echo "Python 3.10 is available."
fi

# Check for pip3
echo "Checking for pip3..."
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Attempting to install it automatically..."
    if install_pip3; then
        echo "pip3 has been successfully installed."
    else
        echo "Automatic installation failed. Would you like to be directed to the pip installation guide? (y/n)"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            PIP_GUIDE_URL="https://pip.pypa.io/en/stable/installation/"
            open_url "$PIP_GUIDE_URL"
            echo "Please follow the instructions on the website to install pip."
        fi
        wait_for_input
        exit 1
    fi
else
    echo "pip3 is available."
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
        sudo apt-get install -y python3.10-venv
    elif command -v yum &> /dev/null; then
        sudo yum install -y python310-venv
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
    pip install --upgrade pip
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
else
    echo "Installing CPU-only version of PyTorch..."
    pip install --upgrade pip
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
