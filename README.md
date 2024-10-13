so the setup may not work.  there are a lot of requirements that i am sorting through.  I already had a lot of things installed on my dev system so i am testing on a clean system.
# XeroFlow

[GitHub Repository](https://github.com/Xerophayze/XeroFlow)

XeroFlow is a node-based interface for managing and interacting with various Large Language Model (LLM) APIs. It provides a flexible and customizable platform for building workflows that integrate multiple APIs to generate and manage content. The platform allows users to visually create, connect, and manage these workflows through a graphical interface. This system is designed to be modular, making it easy to expand with new nodes or APIs as required.

## Features

### 1. **Node-Based Workflow Creation**
   - XeroFlow allows users to design workflows using a visual interface. Nodes represent different functions, processes, or APIs that you want to interact with. The nodes can be connected to define the data flow between them.
   - The node editor provides intuitive drag-and-drop functionality, allowing users to design and configure complex workflows without having to manage the underlying code manually.
   - The workflow consists of different types of nodes like **Start**, **Processing**, and **Finish** nodes, which can be customized and connected to form powerful automation pipelines.
   - Newly added advanced nodes include capabilities like database search and interactive chat.

### 2. **Improved Setup with Batch Files**
   - The installation process is streamlined using two batch files:
     - `setup.bat` checks for and installs all required components, including Python and pip, if not already installed.
     - `run.bat` sets up a virtual environment and runs the main program.
   - The main program also checks for dependencies; however, this may be further refined in future updates.

### 3. **Enhanced Node Editor with New Advanced Nodes**
   - The node editor has been expanded with several advanced nodes, including:
     - **Interactive LOL Chat Node**: Incorporates database search functionality through the `/doc` command, allowing users to query documents directly within the chat.
     - **Long-Form Content Creation Mode**: Designed to generate long-form content such as stories, manuals, blog posts, etc. An example in the database includes a 90,000-word sci-fi story with 30 chapters and multiple subsections.
   - A refined management panel consolidates various management tasks (like API endpoints, databases, document management, and node management) into a single interface with multiple tabs.

### 4. **API Integration**
   - The system supports integrating multiple LLM APIs by allowing users to connect and configure API endpoints. The interface manages multiple API keys and credentials for smooth integration with various LLM providers.
   - By using the editor, users can create workflows that leverage multiple APIs in sequence or in parallel, generating complex interactions that combine the strengths of each connected service.
   - Common API integrations can include OpenAI, Ollama, and others that support LLM-based content generation.

### 5. **Graphical Interface for Node Management**
   - A GUI-based node editor (built with Tkinter) is the core component of XeroFlow. The interface allows users to:
     - Add new nodes (LLM APIs, content generation processes, etc.)
     - Connect nodes to create workflows
     - Save, modify, and reload existing workflows
     - Resize, drag, and modify node positions easily
   - Each node is identified using a unique ID (generated via `uuid`), and the editor manages the internal state of each node and connection.

### 6. **Database Search in Main Interface**
   - Users can directly perform database searches within the main interface, allowing for quick and easy access to document information without requiring specific nodes or workflows.

### 7. **Dependency Management**
   - The system includes utilities for checking and installing dependencies (like `requests`, `PyYAML`, and `Pygments`).
   - For components that cannot be installed via `pip` (e.g., `Tkinter`), users will be notified to install them manually.

## How to Use

1. **Install Python and Pip:**
   - Ensure you have Python (version 3.8 or higher) and pip installed on your system. You can download and install them from the official [Python website](https://www.python.org/downloads/).

2. **Clone the Repository:**
   ```
   git clone https://github.com/Xerophayze/XeroFlow.git
   cd XeroFlow
   ```

3. **Run the Setup:**
   Run the setup script to install Python, pip, and other necessary dependencies:
   ```
   setup.bat
   ```

4. **Run the Application:**
   Start the application with `run.bat`, which will set up a virtual environment and launch the main program:
   ```
   run.bat
   ```

5. **Build Your Workflow:**
   Use the node editor to design and connect different APIs and functions. Save and manage your workflows easily using the provided interface.

## Future Enhancements
- **Database Selection Improvement**: Currently, the database selection dropdown in the interactive chat node does not function fully and defaults to the database specified in the node’s properties.
- **Additional Advanced Nodes**: Adding nodes for logic processing, loops (repeater nodes), and more will further expand the capabilities of XeroFlow.
- **Directory Structure**: The directory will be organized further, moving all required modules into a dedicated subdirectory to streamline the root structure.

## Contributions
Contributions are welcome! Feel free to submit pull requests or report issues. Please review the contribution guidelines before getting started.
