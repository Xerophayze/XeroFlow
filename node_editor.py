import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import math

class NodeEditor:
    def __init__(self, parent, config, api_interfaces, existing_graph=None, existing_name="", save_callback=None, close_callback=None):
        self.parent = parent
        self.config = config
        self.api_interfaces = api_interfaces
        self.nodes = {}
        self.connections = []
        self.selected_node = None
        self.canvas = None
        self.node_counter = {'Start': 0, 'Processing': 0, 'Finish': 0}
        self.node_drag_data = {'x': 0, 'y': 0}
        self.connection_start = None
        self.temp_line = None
        self.instruction_name = existing_name
        self.save_callback = save_callback
        self.close_callback = close_callback

        # New attributes for resizing
        self.resizing_node_id = None
        self.resize_start_data = None

        self.create_editor_window()

        if existing_graph:
            self.load_graph(existing_graph)
            self.redraw_canvas()
            
    def is_open(self):
        return self.editor_window.winfo_exists()

    def highlight_node(self, node_id):
        # Remove existing highlights
        for item in self.canvas.find_withtag('highlight'):
            self.canvas.itemconfig(item, outline='black', width=1)
            self.canvas.dtag(item, 'highlight')

        # Highlight the current node
        node_items = self.canvas.find_withtag(node_id)
        # Only consider rectangle items
        for item in node_items:
            item_type = self.canvas.type(item)
            if item_type == 'rectangle':
                try:
                    self.canvas.itemconfig(item, outline='green', width=2)
                    self.canvas.addtag_withtag('highlight', item)
                except tk.TclError as e:
                    print(f"Failed to highlight node {node_id}: {e}")

    def create_editor_window(self):
        self.editor_window = tk.Toplevel(self.parent)
        self.editor_window.title("Node-Based Instruction Editor")
        self.editor_window.geometry("800x600")
        self.editor_window.resizable(True, True)

        # Handle window close event
        self.editor_window.protocol("WM_DELETE_WINDOW", self.on_close)

        # Create toolbar for node types
        toolbar = ttk.Frame(self.editor_window)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        start_btn = ttk.Button(toolbar, text="Start Node", command=lambda: self.add_node('Start'))
        start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        processing_btn = ttk.Button(toolbar, text="Processing Node", command=lambda: self.add_node('Processing'))
        processing_btn.pack(side=tk.LEFT, padx=5, pady=5)

        finish_btn = ttk.Button(toolbar, text="Finish Node", command=lambda: self.add_node('Finish'))
        finish_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Canvas for node editor
        self.canvas = tk.Canvas(self.editor_window, bg='white')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Save and Cancel buttons
        button_frame = ttk.Frame(self.editor_window)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)

        save_btn = ttk.Button(button_frame, text="Save", command=self.save_node_graph)
        save_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.on_close)
        cancel_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # Instruction Set Name Entry
        name_frame = ttk.Frame(self.editor_window)
        name_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        ttk.Label(name_frame, text="Instruction Set Name:").pack(side=tk.LEFT, padx=5)
        self.name_var = tk.StringVar(value=self.instruction_name)
        name_entry = ttk.Entry(name_frame, textvariable=self.name_var)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def on_close(self):
        # Ask for confirmation before closing
        if messagebox.askokcancel("Quit", "Do you want to discard changes and exit?"):
            if self.close_callback:
                self.close_callback(self)
            self.editor_window.destroy()

    def load_graph(self, graph_data):
        self.nodes = graph_data.get('nodes', {})
        self.connections = graph_data.get('connections', {})

        # Update node counters
        self.node_counter = {'Start': 0, 'Processing': 0, 'Finish': 0}
        for node in self.nodes.values():
            node_type = node['type']
            self.node_counter[node_type] += 1

    def add_node(self, node_type):
        node_id = str(uuid.uuid4())
        node = {
            'id': node_id,
            'type': node_type,
            'title': f"{node_type} Node {self.node_counter[node_type]+1}",
            'x': 50 + self.node_counter[node_type]*20,
            'y': 50 + self.node_counter[node_type]*20,
            'width': 150,
            'height': 80,
            'api': None,
            'prompt': '',
            'test_criteria': '',
            'description': '',  # New description field
            'true_output': None,
            'false_output': None,
            'inputs': [],
            'outputs': []
        }
        self.node_counter[node_type] += 1

        # Draw the node on the canvas
        self.nodes[node_id] = node
        self.draw_node(node)

    def draw_node(self, node):
        x = node['x']
        y = node['y']
        width = node['width']
        height = node['height']
        node_type = node['type']

        node['canvas_items'] = {}  # Initialize the canvas items dictionary

        # Draw rectangle with an additional 'rect' tag
        rect = self.canvas.create_rectangle(x, y, x + width, y + height, fill='lightblue', tags=('node', node['id'], 'rect'))
        node['canvas_items']['rect'] = rect
        self.canvas.tag_bind(rect, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(rect, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(rect, "<ButtonRelease-1>", self.on_node_release)
        self.canvas.tag_bind(rect, "<Button-3>", self.on_right_click)

        # Draw title
        title = self.canvas.create_text(x + width / 2, y + 15, text=node['title'], tags=('node', node['id'], 'title'))
        node['canvas_items']['title'] = title
        self.canvas.tag_bind(title, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(title, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(title, "<ButtonRelease-1>", self.on_node_release)
        self.canvas.tag_bind(title, "<Button-3>", self.on_right_click)

        # Draw description
        description = node.get('description', '')
        if description:
            desc_text = self.canvas.create_text(x + width / 2, y + 35, text=description, tags=('node', node['id'], 'description'))
            node['canvas_items']['description'] = desc_text
            self.canvas.tag_bind(desc_text, "<ButtonPress-1>", self.on_node_press)
            self.canvas.tag_bind(desc_text, "<B1-Motion>", self.on_node_move)
            self.canvas.tag_bind(desc_text, "<ButtonRelease-1>", self.on_node_release)
            self.canvas.tag_bind(desc_text, "<Button-3>", self.on_right_click)

        # Draw connectors
        if node_type != 'Finish':
            # Output connectors (True and False)
            true_output = self.canvas.create_oval(x + width - 10, y + height / 2 - 15, x + width, y + height / 2 - 5, fill='green', tags=('output_true', node['id']))
            false_output = self.canvas.create_oval(x + width - 10, y + height / 2 + 5, x + width, y + height / 2 + 15, fill='red', tags=('output_false', node['id']))
            node['canvas_items']['true_output'] = true_output
            node['canvas_items']['false_output'] = false_output
            self.canvas.tag_bind(true_output, "<ButtonPress-1>", self.start_connection)
            self.canvas.tag_bind(false_output, "<ButtonPress-1>", self.start_connection)
            # Bind right-click to output connectors
            self.canvas.tag_bind(true_output, "<Button-3>", self.on_connector_right_click)
            self.canvas.tag_bind(false_output, "<Button-3>", self.on_connector_right_click)
        if node_type != 'Start':
            # Input connector
            input_connector = self.canvas.create_oval(x, y + height / 2 - 5, x + 10, y + height / 2 + 5, fill='black', tags=('input', node['id']))
            node['canvas_items']['input'] = input_connector
            # Bind right-click to input connector
            self.canvas.tag_bind(input_connector, "<Button-3>", self.on_connector_right_click)

        # Draw resize handle
        resize_handle_size = 10
        resize_handle = self.canvas.create_rectangle(
            x + width - resize_handle_size, y + height - resize_handle_size,
            x + width, y + height, fill='gray', tags=('node', node['id'], 'resize_handle'))
        node['canvas_items']['resize_handle'] = resize_handle
        self.canvas.tag_bind(resize_handle, "<ButtonPress-1>", self.on_resize_press)
        self.canvas.tag_bind(resize_handle, "<B1-Motion>", self.on_resize_move)
        self.canvas.tag_bind(resize_handle, "<ButtonRelease-1>", self.on_resize_release)

        # Redraw connections to ensure they're on top
        self.redraw_connections()

    def on_node_press(self, event):
        # Ignore if clicking on resize handle
        tags = self.canvas.gettags('current')
        if 'resize_handle' in tags:
            return
        # Record the item and its location
        self.selected_node = self.canvas.find_withtag('current')[0]
        tags = self.canvas.gettags(self.selected_node)
        node_id = tags[tags.index('node') + 1]
        self.moving_node_id = node_id
        self.node_drag_data['x'] = event.x
        self.node_drag_data['y'] = event.y

    def on_node_move(self, event):
        if self.selected_node:
            dx = event.x - self.node_drag_data['x']
            dy = event.y - self.node_drag_data['y']
            self.canvas.move(self.selected_node, dx, dy)
            # Move all items with the same node id
            tags = self.canvas.gettags(self.selected_node)
            node_id = tags[tags.index('node') + 1]
            items = self.canvas.find_withtag(node_id)
            for item in items:
                if item != self.selected_node:
                    self.canvas.move(item, dx, dy)
            self.node_drag_data['x'] = event.x
            self.node_drag_data['y'] = event.y
            # Update node position
            node = self.nodes[node_id]
            node['x'] += dx
            node['y'] += dy
            self.redraw_connections()

    def on_node_release(self, event):
        self.selected_node = None

    def redraw_canvas(self):
        self.canvas.delete("all")
        for node_id in self.nodes:
            self.draw_node(self.nodes[node_id])
        self.redraw_connections()

    def redraw_connections(self):
        # Remove existing connection lines
        for item in self.canvas.find_withtag('connection'):
            self.canvas.delete(item)
        for conn in self.connections:
            self.draw_connection(conn)

    def start_connection(self, event):
        tags = self.canvas.gettags('current')
        output_type = 'true' if 'output_true' in tags else 'false'
        node_id = tags[tags.index('output_' + output_type) + 1]
        self.connection_start = (node_id, output_type)
        self.temp_line_start = (event.x, event.y)
        self.temp_line = self.canvas.create_line(event.x, event.y, event.x, event.y, fill='gray', dash=(2, 2))
        self.canvas.bind("<Motion>", self.update_temp_line)
        self.canvas.bind("<ButtonRelease-1>", self.check_connection_end)

    def update_temp_line(self, event):
        if self.temp_line:
            x0, y0 = self.temp_line_start
            self.canvas.coords(self.temp_line, x0, y0, event.x, event.y)

    def check_connection_end(self, event):
        self.canvas.unbind("<Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        if self.temp_line:
            self.canvas.delete(self.temp_line)
            self.temp_line = None

        # Get the item under the cursor
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in items:
            tags = self.canvas.gettags(item)
            if 'input' in tags:
                # Found an input connector
                node_id = tags[tags.index('input') + 1]
                self.end_connection(node_id)
                return
        # If no input connector was found under cursor
        self.connection_start = None

    def end_connection(self, to_node_id):
        output_node_id, output_type = self.connection_start
        self.connection_start = None

        if output_node_id == to_node_id:
            messagebox.showerror("Invalid Connection", "Cannot connect a node to itself.")
            return

        # Prevent multiple connections from the same output to different inputs
        for conn in self.connections:
            if conn['from_node'] == output_node_id and conn['from_output'] == output_type:
                messagebox.showerror("Invalid Connection", "This output is already connected.")
                return

        self.connections.append({
            'from_node': output_node_id,
            'from_output': output_type,
            'to_node': to_node_id
        })
        self.redraw_connections()

    def draw_connection(self, conn, min_length=20):
        from_node = self.nodes[conn['from_node']]
        to_node = self.nodes[conn['to_node']]

        # Calculate the center positions of the connectors
        fx = from_node['x'] + from_node['width']
        if conn['from_output'] == 'true':
            fy = from_node['y'] + from_node['height'] / 2 - 10
        else:
            fy = from_node['y'] + from_node['height'] / 2 + 10
        tx = to_node['x']
        ty = to_node['y'] + to_node['height'] / 2

        # Calculate straight-line distance between connectors
        distance = math.hypot(tx - fx, ty - fy)

        # Determine if adjustment is needed
        if distance < min_length:
            # Calculate the angle of the connection
            angle = math.atan2(ty - fy, tx - fx)
            # Adjust the target position to enforce minimum length
            tx = fx + min_length * math.cos(angle)
            ty = fy + min_length * math.sin(angle)

        # Recalculate the control points based on possibly adjusted tx, ty
        mx = (fx + tx) / 2
        my = (fy + ty) / 2
        offset = 10  # Adjust this value to control the curvature

        # Create a list of points for the Bezier curve
        points = [fx, fy, mx + offset, fy, mx - offset, ty, tx, ty]

        # Draw the curved line
        line = self.canvas.create_line(points, smooth=True, splinesteps=100, arrow=tk.LAST, tags='connection')
        conn['canvas_item'] = line  # Store the canvas item ID
        # Bind right-click to the connection line
        self.canvas.tag_bind(line, "<Button-3>", self.on_connection_right_click)

    def on_right_click(self, event):
        # Show context menu for editing node properties
        item = self.canvas.find_withtag('current')
        if item:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                node_id = tags[tags.index('node') + 1]
                node = self.nodes.get(node_id)
                if node:
                    self.show_context_menu(event, node)

    def show_context_menu(self, event, node):
        menu = tk.Menu(self.canvas, tearoff=0)
        menu.add_command(label="Edit", command=lambda: self.edit_node_properties(node))
        menu.add_command(label="Delete", command=lambda: self.delete_node(node))
        menu.post(event.x_root, event.y_root)

    def delete_node(self, node):
        # Remove connections associated with this node
        self.connections = [conn for conn in self.connections if conn['from_node'] != node['id'] and conn['to_node'] != node['id']]
        # Remove node
        del self.nodes[node['id']]
        self.redraw_canvas()

    def edit_node_properties(self, node):
        def save_properties():
            prompt = prompt_text.get("1.0", tk.END).strip()
            api = api_var.get()
            test_criteria = test_criteria_entry.get().strip()
            description = description_text.get("1.0", tk.END).strip()  # Get description

            if not prompt:
                messagebox.showwarning("Input Required", "Prompt Text is required.")
                return
            if not api:
                messagebox.showwarning("Input Required", "LLM API Selection is required.")
                return

            # Check if Test Criteria is required
            false_output_connected = any(conn['from_node'] == node['id'] and conn['from_output'] == 'false' for conn in self.connections)
            if false_output_connected and not test_criteria:
                messagebox.showwarning("Input Required", "Test Criteria is required when False output is connected.")
                return

            node['prompt'] = prompt
            node['api'] = api
            node['test_criteria'] = test_criteria
            node['description'] = description  # Save description
            prop_window.destroy()
            # Update description text on canvas
            self.update_node_text(node)

        prop_window = tk.Toplevel(self.editor_window)
        prop_window.title(f"Edit Node Properties - {node['title']}")
        prop_window.geometry("400x500")
        prop_window.resizable(True, True)

        ttk.Label(prop_window, text="Prompt Text:").pack(pady=5)
        prompt_text = tk.Text(prop_window, height=5, width=50)
        prompt_text.pack(pady=5)
        prompt_text.insert(tk.END, node.get('prompt', ''))

        ttk.Label(prop_window, text="LLM API Selection:").pack(pady=5)
        api_var = tk.StringVar()
        api_dropdown = ttk.Combobox(prop_window, textvariable=api_var, values=list(self.api_interfaces.keys()), state="readonly")
        api_dropdown.pack(pady=5)
        if node.get('api'):
            api_dropdown.set(node['api'])

        ttk.Label(prop_window, text="Test Criteria:").pack(pady=5)
        test_criteria_entry = ttk.Entry(prop_window, width=50)
        test_criteria_entry.pack(pady=5)
        test_criteria_entry.insert(0, node.get('test_criteria', ''))

        ttk.Label(prop_window, text="Description:").pack(pady=5)  # New description label
        description_text = tk.Text(prop_window, height=3, width=50)
        description_text.pack(pady=5)
        description_text.insert(tk.END, node.get('description', ''))

        save_btn = ttk.Button(prop_window, text="Save", command=save_properties)
        save_btn.pack(pady=10)

    def save_node_graph(self):
        # Validate node graph before saving
        if not self.validate_node_graph():
            return

        # Get instruction set name
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Input Required", "Please enter a name for the instruction set.")
            return
        self.instruction_name = name

        # Serialize nodes and connections
        graph_data = {
            'nodes': self.nodes,
            'connections': self.connections
        }

        # Save graph data and name
        self.configured_graph = graph_data
        self.configured_name = self.instruction_name

        if self.save_callback:
            self.save_callback(self)

        # Do not destroy the editor window; keep it open
        # self.editor_window.destroy()

    def validate_node_graph(self):
        # Ensure there is exactly one Start Node and one Finish Node
        start_nodes = [node for node in self.nodes.values() if node['type'] == 'Start']
        finish_nodes = [node for node in self.nodes.values() if node['type'] == 'Finish']
        if len(start_nodes) != 1:
            messagebox.showerror("Validation Error", "There must be exactly one Start Node.")
            return False
        if len(finish_nodes) != 1:
            messagebox.showerror("Validation Error", "There must be exactly one Finish Node.")
            return False
        # Check for unconnected nodes
        for node in self.nodes.values():
            if node['type'] != 'Start':
                if not any(conn['to_node'] == node['id'] for conn in self.connections):
                    messagebox.showerror("Validation Error", f"Node '{node['title']}' is not connected.")
                    return False
            if node['type'] != 'Finish':
                if not any(conn['from_node'] == node['id'] for conn in self.connections):
                    messagebox.showerror("Validation Error", f"Node '{node['title']}' has no outgoing connections.")
                    return False
        # Additional validation can be added here
        return True

    def get_configured_graph(self):
        return getattr(self, 'configured_graph', None)

    def get_instruction_name(self):
        return getattr(self, 'configured_name', None)

    # New methods for resizing
    def on_resize_press(self, event):
        item = self.canvas.find_withtag('current')[0]
        tags = self.canvas.gettags(item)
        node_id = tags[tags.index('node') + 1]
        self.resizing_node_id = node_id
        self.resize_start_data = {
            'x': event.x,
            'y': event.y,
            'width': self.nodes[node_id]['width'],
            'height': self.nodes[node_id]['height']
        }

    def on_resize_move(self, event):
        if self.resizing_node_id:
            dx = event.x - self.resize_start_data['x']
            dy = event.y - self.resize_start_data['y']
            new_width = self.resize_start_data['width'] + dx
            new_height = self.resize_start_data['height'] + dy

            # Set minimum size
            min_width = 100
            min_height = 50
            if new_width < min_width:
                new_width = min_width
            if new_height < min_height:
                new_height = min_height

            # Update node dimensions
            node = self.nodes[self.resizing_node_id]
            node['width'] = new_width
            node['height'] = new_height

            # Update the rectangle
            rect = node['canvas_items']['rect']
            x1, y1, x2, y2 = self.canvas.coords(rect)
            x1 = node['x']
            y1 = node['y']
            self.canvas.coords(rect, x1, y1, x1 + new_width, y1 + new_height)

            # Update the resize handle
            resize_handle = node['canvas_items']['resize_handle']
            resize_handle_size = 10
            self.canvas.coords(resize_handle,
                               x1 + new_width - resize_handle_size,
                               y1 + new_height - resize_handle_size,
                               x1 + new_width,
                               y1 + new_height)

            # Update the title position
            title = node['canvas_items']['title']
            self.canvas.coords(title, x1 + new_width / 2, y1 + 15)

            # Update the description position
            if 'description' in node['canvas_items']:
                desc_text = node['canvas_items']['description']
                self.canvas.coords(desc_text, x1 + new_width / 2, y1 + 35)

            # Update connectors positions
            node_type = node['type']
            if node_type != 'Finish':
                true_output = node['canvas_items']['true_output']
                false_output = node['canvas_items']['false_output']
                # True output connector
                self.canvas.coords(true_output,
                                   x1 + new_width - 10, y1 + new_height / 2 - 15,
                                   x1 + new_width, y1 + new_height / 2 - 5)
                # False output connector
                self.canvas.coords(false_output,
                                   x1 + new_width - 10, y1 + new_height / 2 + 5,
                                   x1 + new_width, y1 + new_height / 2 + 15)
            if node_type != 'Start':
                input_connector = node['canvas_items']['input']
                self.canvas.coords(input_connector,
                                   x1, y1 + new_height / 2 - 5,
                                   x1 + 10, y1 + new_height / 2 + 5)

            # Redraw connections
            self.redraw_connections()

    def on_resize_release(self, event):
        self.resizing_node_id = None
        self.resize_start_data = None

    def update_node_text(self, node):
        # Update the description text on the canvas
        if 'description' in node['canvas_items']:
            desc_text_item = node['canvas_items']['description']
            self.canvas.itemconfigure(desc_text_item, text=node.get('description', ''))
        else:
            # If description was previously empty, add it
            if node.get('description', ''):
                x = node['x']
                y = node['y']
                width = node['width']
                desc_text = self.canvas.create_text(x + width / 2, y + 35, text=node['description'], tags=('node', node['id'], 'description'))
                node['canvas_items']['description'] = desc_text
                self.canvas.tag_bind(desc_text, "<ButtonPress-1>", self.on_node_press)
                self.canvas.tag_bind(desc_text, "<B1-Motion>", self.on_node_move)
                self.canvas.tag_bind(desc_text, "<ButtonRelease-1>", self.on_node_release)
                self.canvas.tag_bind(desc_text, "<Button-3>", self.on_right_click)

    # New methods for handling right-click on connectors and connections
    def on_connector_right_click(self, event):
        # Get the item under the cursor
        item = self.canvas.find_withtag('current')[0]
        tags = self.canvas.gettags(item)
        if 'input' in tags:
            connector_type = 'input'
            node_id = tags[tags.index('input') + 1]
        elif 'output_true' in tags:
            connector_type = 'output_true'
            node_id = tags[tags.index('output_true') + 1]
        elif 'output_false' in tags:
            connector_type = 'output_false'
            node_id = tags[tags.index('output_false') + 1]
        else:
            return  # Not a recognized connector

        # Build the context menu
        menu = tk.Menu(self.canvas, tearoff=0)
        menu.add_command(label="Delete Connection", command=lambda: self.delete_connection_from_connector(node_id, connector_type))
        menu.post(event.x_root, event.y_root)

    def delete_connection_from_connector(self, node_id, connector_type):
        # Find the connection(s) associated with this connector
        if connector_type == 'input':
            # Find connection where to_node == node_id
            connections_to_delete = [conn for conn in self.connections if conn['to_node'] == node_id]
        elif connector_type == 'output_true':
            # Find connection where from_node == node_id and from_output == 'true'
            connections_to_delete = [conn for conn in self.connections if conn['from_node'] == node_id and conn['from_output'] == 'true']
        elif connector_type == 'output_false':
            # Find connection where from_node == node_id and from_output == 'false'
            connections_to_delete = [conn for conn in self.connections if conn['from_node'] == node_id and conn['from_output'] == 'false']
        else:
            return

        # If there are connections, delete them
        for conn in connections_to_delete:
            self.delete_connection(conn)

    def on_connection_right_click(self, event):
        # Get the canvas item
        item = self.canvas.find_withtag('current')[0]
        # Find the connection associated with this item
        for conn in self.connections:
            if conn.get('canvas_item') == item:
                self.show_connection_context_menu(event, conn)
                break

    def show_connection_context_menu(self, event, conn):
        menu = tk.Menu(self.canvas, tearoff=0)
        menu.add_command(label="Delete Connection", command=lambda: self.delete_connection(conn))
        menu.post(event.x_root, event.y_root)

    def delete_connection(self, conn):
        # Remove the line from the canvas
        if 'canvas_item' in conn:
            self.canvas.delete(conn['canvas_item'])
        # Remove the connection from the connections list
        if conn in self.connections:
            self.connections.remove(conn)
        # No need to redraw connections since we just deleted one

    # Example usage:
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    # Mock config and API interfaces
    config = {}
    api_interfaces = {
        'OpenAI API': {'url': 'https://api.openai.com', 'api_key': 'your-api-key'},
        'Local LLM': {'url': 'http://localhost:8000'}
    }

    editor = NodeEditor(root, config, api_interfaces)
    root.mainloop()
