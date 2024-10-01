
# XeroLLM

[GitHub Repository](https://github.com/Xerophayze/XeroLLM)

XeroLLM is a node-based interface for managing and interacting with various Large Language Model (LLM) APIs. It provides a flexible and customizable platform for building workflows that integrate multiple APIs to generate and manage content. The platform allows users to visually create, connect, and manage these workflows through a graphical interface. This system is designed to be modular, making it easy to expand with new nodes or APIs as required.

## Features

### 1. **Node-Based Workflow Creation**
   - XeroLLM allows users to design workflows using a visual interface. Nodes represent different functions, processes, or APIs that you want to interact with. The nodes can be connected to define the data flow between them.
   - The node editor provides intuitive drag-and-drop functionality, allowing users to design and configure complex workflows without having to manage the underlying code manually.
   - The workflow consists of different types of nodes like **Start**, **Processing**, and **Finish** nodes, which can be customized and connected to form powerful automation pipelines.

### 2. **API Integration**
   - The system supports integrating multiple LLM APIs by allowing users to connect and configure API endpoints. The interface manages multiple API keys and credentials for smooth integration with various LLM providers.
   - By using the editor, users can create workflows that leverage multiple APIs in sequence or in parallel, generating complex interactions that combine the strengths of each connected service.
   - Common API integrations can include OpenAI, Ollama, and others that support LLM-based content generation.

### 3. **Graphical Interface for Node Management**
   - A GUI-based node editor (built with Tkinter) is the core component of XeroLLM. The interface allows users to:
     - Add new nodes (LLM APIs, content generation processes, etc.)
     - Connect nodes to create workflows
     - Save, modify, and reload existing workflows
     - Resize, drag, and modify node positions easily
   - Each node is identified using a unique ID (generated via `uuid`), and the editor manages the internal state of each node and connection.

### 4. **Prompt Generation and Workflow Execution**
   - The `PromptGen` component helps users define prompts and manage the execution of workflows. It checks for dependencies (like requests, PyYAML, and others) and ensures that the necessary libraries are installed.
   - Dependencies are automatically installed if missing, making the setup and deployment of workflows smoother.

### 5. **Custom Node Behavior**
   - Users can implement custom behavior for each node. For example, the system can process or modify content before sending it to the next API or node.
   - The resizing and connection logic between nodes allows for flexibility in creating workflows that meet the specific needs of the user.

### 6. **Dependency Management**
   - The system includes a utility (`PromptGen`) that checks for required dependencies such as `requests`, `PyYAML`, and `Pygments`, installing them if necessary.
   - For packages that are not directly installable via `pip`, such as `Tkinter`, it will notify the user to install them manually.

## How to Use

1. **Clone the Repository:**
   ```
   git clone https://github.com/Xerophayze/XeroLLM.git
   cd XeroLLM
   ```

2. **Install Dependencies:**
   The script will automatically install Python dependencies like `requests`, `PyYAML`, and `Pygments`. Ensure that you also install `Tkinter`, which is required for the GUI.

   You can manually install dependencies using:
   ```
   pip install -r requirements.txt
   ```

3. **Run the Application:**
   Start the node editor by running the main script, which will open the graphical interface:
   ```
   python node_editor.py
   ```

4. **Build Your Workflow:**
   Use the node editor to design and connect different APIs and functions. Save and manage your workflows easily using the provided interface.

## Future Enhancements
- Adding support for more API integrations (Google Cloud, Microsoft Azure, etc.).
- Creating more pre-built node types for common tasks like data transformation, filtering, and aggregation.
- Enhancing user customization options for node design and interconnectivity.

## Contributions
Contributions are welcome! Feel free to submit pull requests or report issues. Please review the contribution guidelines before getting started.
