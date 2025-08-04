# XeroFlow Client

This is a standalone client for interacting with the XeroFlow server. It provides a graphical user interface for submitting jobs and viewing results.

## Prerequisites

Before you begin, you must have **Python 3** installed on your system. You can download it from [python.org](https://www.python.org/downloads/).

When installing on Windows, make sure to check the box that says **"Add Python to PATH"** during the installation process.

## How to Run

The client includes startup scripts that will automatically create a local environment and install all necessary dependencies for you. Simply follow the instructions for your operating system.

## Important: Initial Setup

Before you can submit jobs, you must configure the client to communicate with the main XeroFlow Assistant.

1.  **Set Folders**: Go to the **Settings** tab in the client. You **must** set the **Inbox Folder** and the **Outbox Folder**. These are the folders the client will use to send jobs and receive results.

2.  **Sync with XeroFlow Assistant**: The main XeroFlow Assistant workflow **must be running** and configured to monitor the **exact same Inbox and Outbox folders**. If the folders do not match, the client will not be able to communicate with the assistant.

3.  **(Optional) Cloud Sync for Mobile Access**: For best results, set your Inbox and Outbox folders to a location that is synced with a cloud service like Google Drive, Dropbox, or OneDrive. This will allow you to drop files into the Inbox from any device (including your phone) to submit jobs.

### For Windows Users

1.  Navigate to the `Client` directory.
2.  Double-click the `start_client.bat` file.
3.  A command prompt window will open, install the required packages, and then launch the application. The first time you run it, the setup might take a minute.

### For macOS and Linux Users

1.  Open your terminal.
2.  Navigate to the `Client` directory where you extracted the files.
3.  Make the script executable by running the following command:
    ```bash
    chmod +x start_client.sh
    ```
4.  Run the script:
    ```bash
    ./start_client.sh
    ```
5.  The script will check for dependencies, ask for your permission if it needs to install system packages (like `venv` or `pip`), set up the environment, and launch the application.

---

That's it! The script handles the heavy lifting so you can get started quickly.
