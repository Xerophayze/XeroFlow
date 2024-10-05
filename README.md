# XeroLLM

[GitHub Repository](https://github.com/Xerophayze/XeroLLM)

XeroLLM is a node-based interface for managing and interacting with various Large Language Model (LLM) APIs. It provides a flexible and customizable platform for building workflows that integrate multiple APIs to generate and manage content. The platform allows users to visually create, connect, and manage these workflows through a graphical interface. This system is designed to be modular, making it easy to expand with new nodes or APIs as required.

## Features

### 1. **Node-Based Workflow Creation**
   - XeroLLM allows users to design workflows using a visual interface. Nodes represent different functions, processes, or APIs that you want to interact with. The nodes can be connected to define the data flow between them.
   - The node editor provides intuitive drag-and-drop functionality, allowing users to design and configure complex workflows without having to manage the underlying code manually.
   - Nodes are now saved as separate, customizable files, offering more flexibility and personalization of workflow components.

### 2. **Custom Module Creation**
   - XeroLLM now supports creating custom modules using Python. This allows users to extend the system with custom logic, making it even more adaptable to specific project needs.

### 3. **Save and Share Workflows**
   - Workflows can now be saved as individual files, enabling users to easily share them with others or reload them for future use. This makes collaboration and reuse of workflows seamless.

### 4. **API Integration**
   - The system supports integrating multiple LLM APIs by allowing users to connect and configure API endpoints. The interface manages multiple API keys and credentials for smooth integration with various LLM providers.
   - By using the editor, users can create workflows that leverage multiple APIs in sequence or in parallel, generating complex interactions that combine the strengths of each connected service.
   - Common API integrations include OpenAI, Ollama, and other LLM-based content generation services.

### 5. **Graphical Interface for Node Management**
   - A GUI-based node editor (built with Tkinter) is the core component of XeroLLM. The interface allows users to:
     - Add new nodes (LLM APIs, content generation processes, etc.)
     - Customize nodes through individual files for full control over node behavior
     - Connect nodes to create workflows
     - Save, modify, and reload existing workflows
     - Resize, drag, and modify node positions easily
   - Each node is identified using a unique ID (generated via `uuid`), and the editor manages the internal state of each node and connection.

### 6. **Enhanced Output Window**
   - A revamped output window now features better formatting, supporting rich text and code display. This enhancement provides clearer feedback and formatting when working with code and results.

### 7. **Prompt Generation and Workflow Execution**
   - The `PromptGen` component helps users define prompts and manage the execution of workflows. It checks for dependencies (like requests, PyYAML, and others) and ensures that the necessary libraries are installed.
   - Dependencies are automatically installed if missing, making the setup and deployment of workflows smoother.

### 8. **Custom Node Behavior**
   - Users can implement custom behavior for each node. For example, the system can process or modify content before sending it to the next API or node.
   - The resizing and connection logic between nodes allows for flexibility in creating workflows that meet the specific needs of the user.

### 9. **Dependency Management**
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

3. **Run the Application:**
   Start the node editor by running the main script, which will open the graphical interface:
   ```
   python main.py
   ```

4. **Build Your Workflow:**
   Use the node editor to design and connect different APIs and functions. Save and manage your workflows easily using the provided interface.

## Recent Updates

- **Customizable Nodes:** Nodes are now separate files, allowing for greater customization.
- **Create Custom Modules:** Add Python-based custom modules to expand functionality.
- **Save & Share Workflows:** Easily save workflows as individual files for sharing.
- **Improved Interface:** A more streamlined interface for easier navigation and use.
- **Enhanced Output Window:** Better formatting for code and other rich text in the output window.
- **Backend Code Overhaul:** Significant improvements to make the backend more modular, setting the foundation for future upgrades.

## Future Enhancements
- Adding a chat history or chronological context window for all output.
- Creating more pre-built node types for common tasks like data transformation, filtering, and aggregation.
- Adding the ability to create a library of preset prompts that can be selected in the node properties.
- Enhancing user customization options for node design and interconnectivity.

## Contributions
Contributions are welcome! Feel free to submit pull requests or report issues. Please review the contribution guidelines before getting started.
