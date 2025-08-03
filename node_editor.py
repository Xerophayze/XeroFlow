# node_editor.py

import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import math
import os
import importlib
import inspect
import json
from node_registry import NODE_REGISTRY  # Import the registry
from nodes.missing_node import MissingNode  # Add import for MissingNode
from nodes.base_node import BaseNode  # Absolute import

class NodeEditor:
    def __init__(self, parent, config, api_interfaces, existing_graph=None, existing_name="", save_callback=None, close_callback=None):
        self.parent = parent
        self.config = config
        self.api_interfaces = api_interfaces
        self.nodes = {}
        self.connections = []
        self.selected_node = None
        self.canvas = None
        self.node_classes = self.load_node_classes()
        self.node_counter = {cls.__name__: 0 for cls in self.node_classes}
        self.node_counter['MissingNode'] = 0  # Add MissingNode to the counter
        self.node_drag_data = {'x': 0, 'y': 0}
        self.connection_start = None
        self.temp_line = None
        self.instruction_name = existing_name
        self.save_callback = save_callback
        self.close_callback = close_callback

        # New attributes for resizing
        self.resizing_node_id = None
        self.resize_start_data = None

        # Modification flag
        self.is_modified = False

        self.create_editor_window()

        if existing_graph:
            self.load_graph(existing_graph)
            self.redraw_canvas()

    def is_open(self):
        return self.editor_window.winfo_exists()

    def load_node_classes(self):
        """
        Retrieve node classes from the node registry.
        Returns a list of node classes.
        """
        node_classes = list(NODE_REGISTRY.values())
        return node_classes

    def get_node_class_by_type(self, node_type):
        """Get the node class by its type, returning MissingNode if not found."""
        try:
            return NODE_REGISTRY.get(node_type, lambda: MissingNode(original_type=node_type))
        except Exception as e:
            print(f"Error getting node class for type {node_type}: {e}")
            return lambda: MissingNode(original_type=node_type)

    def create_editor_window(self):
        self.editor_window = tk.Toplevel(self.parent)
        self.editor_window.title("Node-Based Instruction Editor")
        self.editor_window.geometry("800x600")
        self.editor_window.resizable(True, True)

        # Handle window close event
        self.editor_window.protocol("WM_DELETE_WINDOW", self.on_close)

        # Create toolbar with dropdown menu for node types
        toolbar = ttk.Frame(self.editor_window)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(toolbar, text="Add Node:").pack(side=tk.LEFT, padx=5, pady=5)

        self.node_var = tk.StringVar()
        node_names = [cls.__name__.replace('Node', '') for cls in self.node_classes]
        self.node_dropdown = ttk.Combobox(toolbar, textvariable=self.node_var, values=node_names, state="readonly")
        self.node_dropdown.pack(side=tk.LEFT, padx=5, pady=5)
        self.node_dropdown.bind("<<ComboboxSelected>>", self.on_node_dropdown_select)

        add_button = ttk.Button(toolbar, text="Add", command=self.on_add_button)
        add_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Canvas for node editor
        self.canvas = tk.Canvas(self.editor_window, bg='white')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)

        # Save and Cancel buttons
        button_frame = ttk.Frame(self.editor_window)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.save_btn = ttk.Button(button_frame, text="Save", command=self.save_node_graph, state='disabled')
        self.save_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.on_close)
        cancel_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # Instruction Set Name Entry
        name_frame = ttk.Frame(self.editor_window)
        name_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        ttk.Label(name_frame, text="Instruction Set Name:").pack(side=tk.LEFT, padx=5)
        self.name_var = tk.StringVar(value=self.instruction_name)
        name_entry = ttk.Entry(name_frame, textvariable=self.name_var)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def update_save_button_state(self):
        if self.is_modified:
            self.save_btn.config(state='normal')
        else:
            self.save_btn.config(state='disabled')

    def on_close(self):
        if self.is_modified:
            # Ask for confirmation before closing only if there are unsaved changes
            if not messagebox.askokcancel("Quit", "You have unsaved changes. Do you want to discard them and exit?"):
                return
        if self.close_callback:
            self.close_callback(self)
        self.editor_window.destroy()

    def load_graph(self, graph_data):
        self.nodes = graph_data.get('nodes', {})
        self.connections = graph_data.get('connections', [])

        # Update node counters
        self.node_counter = {cls.__name__: 0 for cls in self.node_classes}
        self.node_counter['MissingNode'] = 0  # Add MissingNode to the counter
        
        for node in self.nodes.values():
            node_type = node['type']
            # If the node type doesn't exist in the counter, add it
            if node_type not in self.node_counter:
                self.node_counter[node_type] = 0
            self.node_counter[node_type] += 1

    def on_node_dropdown_select(self, event):
        pass  # Placeholder for any action on selection

    def on_add_button(self):
        node_type = self.node_var.get()
        if node_type:
            self.add_node(node_type)
            self.node_var.set('')  # Reset dropdown

    def add_node(self, node_type):
        # Create a unique ID for the node
        node_id = str(uuid.uuid4())
        
        # Get the node class
        node_class = self.get_node_class_by_type(node_type + 'Node')
        if not node_class:
            print(f"Node type {node_type} not found")
            return

        # Create an instance of the node to get its properties
        node_instance = node_class(node_id, self.config)
        properties = node_instance.define_properties()

        # Create the node data structure
        node = {
            'id': node_id,
            'type': node_type + 'Node',
            'title': node_type,
            'x': 100,  # Default position
            'y': 100,
            'width': 200,  # Default size
            'height': 150,
            'properties': properties,
            'inputs': node_instance.define_inputs(),
            'outputs': node_instance.define_outputs(),
            'canvas_items': {}  # Will store canvas item IDs
        }

        # Add to nodes dictionary
        self.nodes[node_id] = node

        # Draw the node on canvas
        self.draw_node(node)
        self.is_modified = True
        self.update_save_button_state()

    def create_rounded_rectangle(self, x1, y1, x2, y2, radius=20, **kwargs):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def draw_node(self, node):
        x = node['x']
        y = node['y']
        width = node.get('width', 200)  # Default width if not specified
        height = node.get('height', 150)  # Default height if not specified
        node_type = node.get('type', 'Unknown')
        drag_bar_height = 25  # Height of the drag bar

        # Check if this is a missing node - node type not in registry
        is_missing = node_type not in NODE_REGISTRY
        
        node['canvas_items'] = {}  # Initialize the canvas items dictionary
        
        # Create the node background with rounded corners
        bg_color = '#ffcccc' if is_missing else 'white'  # Red background for missing nodes
        node_bg = self.create_rounded_rectangle(
            x, y, x + width, y + height,
            radius=10,
            fill=bg_color,
            outline='black',
            tags=('node', node['id'], 'rect')  # Removed draggable tag
        )
        node['canvas_items']['rect'] = node_bg

        # Create drag bar at the top
        drag_bar = self.create_rounded_rectangle(
            x, y, x + width, y + drag_bar_height,
            radius=10,
            fill='#e0e0e0',  # Light gray color
            outline='black',
            tags=('node', node['id'], 'drag_bar', 'draggable')
        )
        node['canvas_items']['drag_bar'] = drag_bar
        
        # Add event bindings for dragging to the drag bar only
        self.canvas.tag_bind(drag_bar, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(drag_bar, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(drag_bar, "<ButtonRelease-1>", self.on_node_release)

        # Add event bindings for the background rectangle (except dragging)
        self.canvas.tag_bind(node_bg, "<Button-3>", self.on_right_click)
        
        # Store the current highlight state in the node data
        node['highlight_state'] = False
        
        # Modified event bindings for highlighting
        self.canvas.tag_bind(node_bg, "<Enter>", lambda e, nid=node['id']: self.on_node_enter(nid))
        self.canvas.tag_bind(node_bg, "<Leave>", lambda e, nid=node['id']: self.on_node_leave(nid))

        # Draw title (now on the drag bar)
        title = node.get('title', str(node_type))
        if is_missing:
            title = f"Missing Node: {node_type}"
            
        title_item = self.canvas.create_text(
            x + width/2, y + drag_bar_height/2,
            text=title,
            font=('Arial', 10, 'bold'),
            anchor='center',
            tags=('node', node['id'], 'title', 'draggable')  # Added draggable tag
        )
        node['canvas_items']['title'] = title_item
        
        # Add drag events to title text
        self.canvas.tag_bind(title_item, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(title_item, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(title_item, "<ButtonRelease-1>", self.on_node_release)

        # If this is a missing node, draw a large red X
        if is_missing:
            padding = 40  # Increased padding for larger X
            x1, y1 = x + padding, y + padding
            x2, y2 = x + width - padding, y + height - padding
            
            # First diagonal line of the X (top-left to bottom-right)
            line1 = self.canvas.create_line(
                x1, y1, x2, y2,
                fill='red',
                width=4,
                tags=('node', node['id'], 'x_mark')  # Removed draggable tag
            )
            
            # Second diagonal line of the X (top-right to bottom-left)
            line2 = self.canvas.create_line(
                x2, y1, x1, y2,
                fill='red',
                width=4,
                tags=('node', node['id'], 'x_mark')  # Removed draggable tag
            )
            
            node['canvas_items']['x_mark1'] = line1
            node['canvas_items']['x_mark2'] = line2

        # Draw properties (description with character limit)
        properties_y = y + drag_bar_height + 15  # Adjusted for drag bar
        if 'properties' in node:
            description = node['properties'].get('description', {}).get('default', '')
            if description:
                max_chars = 30
                if len(description) > max_chars:
                    description = description[:max_chars-3] + "..."
                
                prop_item = self.canvas.create_text(
                    x + width/2,
                    properties_y,
                    text=description,
                    anchor='center',
                    tags=('node', node['id'], 'description'),  # Removed draggable tag
                    font=('Arial', 9),
                    width=width - 20
                )
                node['canvas_items']['description'] = prop_item

        # Draw input connectors
        input_x = x
        if 'inputs' in node:
            num_inputs = len(node['inputs'])
            input_gap = (height - drag_bar_height - 15) / (num_inputs + 1) if num_inputs > 0 else (height - drag_bar_height)/2
            for idx, input_name in enumerate(node['inputs']):
                y_pos = y + drag_bar_height + 15 + (idx + 1) * input_gap
                connector = self.canvas.create_oval(
                    input_x - 5, y_pos - 5,
                    input_x + 5, y_pos + 5,
                    fill='lightblue',
                    tags=('node', node['id'], f'input_{input_name}')
                )
                node['canvas_items'][f'input_{input_name}'] = connector
                
                # Bind input connector events
                self.canvas.tag_bind(connector, '<Button-1>', self.on_connector_press)
                
                label = self.canvas.create_text(
                    input_x + 15, y_pos,
                    text=input_name,
                    anchor='w',
                    font=('Arial', 8),
                    tags=('node', node['id'], f'input_label_{input_name}')
                )
                node['canvas_items'][f'input_label_{input_name}'] = label

        # Draw output connectors
        output_x = x + width
        if 'outputs' in node:
            num_outputs = len(node['outputs'])
            output_gap = (height - drag_bar_height - 15) / (num_outputs + 1) if num_outputs > 0 else (height - drag_bar_height)/2
            for idx, output_name in enumerate(node['outputs']):
                y_pos = y + drag_bar_height + 15 + (idx + 1) * output_gap
                connector = self.canvas.create_oval(
                    output_x - 5, y_pos - 5,
                    output_x + 5, y_pos + 5,
                    fill='lightgreen',
                    tags=('node', node['id'], f'output_{output_name}')
                )
                node['canvas_items'][f'output_{output_name}'] = connector
                
                # Bind output connector events
                self.canvas.tag_bind(connector, '<Button-1>', self.start_connection)
                
                label = self.canvas.create_text(
                    output_x - 15, y_pos,
                    text=output_name,
                    anchor='e',
                    font=('Arial', 8),
                    tags=('node', node['id'], f'output_label_{output_name}')
                )
                node['canvas_items'][f'output_label_{output_name}'] = label

        # Draw resize handle
        resize_handle_size = 10
        resize_handle = self.canvas.create_rectangle(
            x + width - resize_handle_size, y + height - resize_handle_size,
            x + width, y + height,
            fill='gray75',
            tags=('node', node['id'], 'resize_handle')
        )
        node['canvas_items']['resize_handle'] = resize_handle
        
        # Add resize handle bindings
        self.canvas.tag_bind(resize_handle, '<ButtonPress-1>', self.on_resize_start)
        self.canvas.tag_bind(resize_handle, '<B1-Motion>', self.on_resize_move)
        self.canvas.tag_bind(resize_handle, '<ButtonRelease-1>', self.on_resize_end)

    def on_node_press(self, event):
        # Record the item and its location
        clicked_item = self.canvas.find_withtag('current')[0]
        tags = self.canvas.gettags(clicked_item)
        
        # Only handle draggable items
        if 'draggable' not in tags or 'resize_handle' in tags:
            return
            
        try:
            node_id = tags[tags.index('node') + 1]
            self.moving_node_id = node_id
            self.node_drag_data['x'] = event.x
            self.node_drag_data['y'] = event.y
        except (ValueError, IndexError):
            self.moving_node_id = None
            return

    def on_node_move(self, event):
        if not self.moving_node_id:
            return
        try:
            tags = self.canvas.gettags('current')
            if 'node' not in tags:
                return
            node_id = tags[tags.index('node') + 1]
            
            dx = event.x - self.node_drag_data['x']
            dy = event.y - self.node_drag_data['y']
            
            # Move all items with the same node id
            items = self.canvas.find_withtag(node_id)
            for item in items:
                self.canvas.move(item, dx, dy)
            
            self.node_drag_data['x'] = event.x
            self.node_drag_data['y'] = event.y
            
            # Update node position
            node = self.nodes[node_id]
            node['x'] += dx
            node['y'] += dy
            self.redraw_connections()

            # Mark as modified
            self.is_modified = True
            self.update_save_button_state()
        except (ValueError, IndexError, KeyError):
            pass  # Ignore any tag-related errors

    def on_node_release(self, event):
        self.moving_node_id = None

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

    def draw_connection(self, conn, min_length=20):
        """Draw a connection between two nodes with a curved line."""
        from_x, from_y = self.get_connector_position(conn['from_node'], conn['from_output'], 'output')
        to_x, to_y = self.get_connector_position(conn['to_node'], conn['to_input'], 'input')

        # Calculate straight-line distance between connectors
        distance = math.hypot(to_x - from_x, to_y - from_y)

        # Determine if adjustment is needed
        if distance < min_length:
            # Calculate the angle of the connection
            angle = math.atan2(to_y - from_y, to_x - from_x)
            # Adjust the target position to enforce minimum length
            to_x = from_x + min_length * math.cos(angle)
            to_y = from_y + min_length * math.sin(angle)

        # Control points for a smooth curve
        mid_x = (from_x + to_x) / 2
        mid_y = (from_y + to_y) / 2
        offset = 50  # Adjust for curvature

        # Create a Bezier-like curve using a smooth line
        points = [
            from_x, from_y,
            mid_x, from_y,
            mid_x, to_y,
            to_x, to_y
        ]

        # Draw the curved line
        line = self.canvas.create_line(
            points,
            smooth=True,
            splinesteps=100,
            fill='black',
            arrow=tk.LAST,
            tags=('connection',)
        )
        
        # Store the line item in the connection data
        conn['canvas_item'] = line
        
        # Add right-click binding for the connection
        self.canvas.tag_bind(line, "<Button-3>", lambda e, c=conn: self.on_connection_right_click(e, c))

    def get_connector_position(self, node_id, connector_name, connector_type):
        """
        Get the absolute position of a connector.
        """
        node = self.nodes[node_id]
        key = f'{connector_type}_{connector_name}'
        item = node['canvas_items'].get(key)
        if not item:
            return (0, 0)  # Default position if connector not found
        coords = self.canvas.coords(item)
        if len(coords) < 4:
            return (0, 0)  # Invalid coordinates
        x = (coords[0] + coords[2]) / 2
        y = (coords[1] + coords[3]) / 2
        return (x, y)

    def update_temp_line(self, event):
        if self.temp_line:
            self.canvas.coords(
                self.temp_line,
                self.temp_line_start[0], self.temp_line_start[1],
                event.x, event.y
            )

    def check_connection_end(self, event):
        self.canvas.unbind("<Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        if self.temp_line:
            self.canvas.delete(self.temp_line)
            self.temp_line = None

        if not self.connection_start:
            return

        # Get the item under the cursor with some tolerance
        items = self.canvas.find_overlapping(event.x-10, event.y-10, event.x+10, event.y+10)
        target_item = None
        target_tags = None

        # Find the first item with an input tag
        for item in items:
            tags = self.canvas.gettags(item)
            if any('input_' in tag for tag in tags):
                target_item = item
                target_tags = tags
                break

        if target_item and target_tags:
            # Get the node ID - it should be the tag after 'node'
            try:
                node_index = target_tags.index('node')
                if node_index + 1 < len(target_tags):
                    node_id = target_tags[node_index + 1]
                else:
                    return
            except ValueError:
                return

            # Get the input name from the input_ tag
            input_name = next((tag.split('_', 1)[1] for tag in target_tags if tag.startswith('input_')), None)

            if node_id and input_name:
                from_node_id, output_name = self.connection_start

                # Check if trying to connect to self
                if from_node_id == node_id:
                    messagebox.showerror("Invalid Connection", "Cannot connect a node to itself.")
                    self.connection_start = None
                    return

                # Check if this exact connection already exists
                for conn in self.connections:
                    if (conn['from_node'] == from_node_id and 
                        conn['to_node'] == node_id and 
                        conn['from_output'] == output_name and 
                        conn['to_input'] == input_name):
                        messagebox.showinfo("Connection exists", "This exact connection already exists.")
                        self.connection_start = None
                        return

                # Create the connection
                connection = {
                    'from_node': from_node_id,
                    'from_output': output_name,
                    'to_node': node_id,
                    'to_input': input_name
                }
                self.connections.append(connection)
                self.draw_connection(connection)

                # Mark as modified
                self.is_modified = True
                self.update_save_button_state()

        self.connection_start = None

    def on_right_click(self, event):
        # Show context menu for editing node properties
        item = self.canvas.find_withtag('current')
        if item:
            tags = self.canvas.gettags(item[0])
            if 'node' in tags:
                node_id = tags[tags.index('node') + 1]
                node = self.nodes.get(node_id)
                if node:
                    self.show_context_menu(event, node)
                    return "break"  # Prevent further handling

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

        # Mark as modified
        self.is_modified = True
        self.update_save_button_state()

    def edit_node_properties(self, node):
        def save_properties():
            for prop_name in node['properties']:
                prop_details = node['properties'][prop_name]
                widget = prop_widgets[prop_name]
                if prop_details['type'] == 'text':
                    value = widget.get()
                elif prop_details['type'] == 'dropdown':
                    value = widget.get()
                elif prop_details['type'] == 'textarea':
                    value = widget.get("1.0", tk.END).strip()
                elif prop_details['type'] == 'boolean':
                    value = var_states[prop_name].get()
                else:
                    value = widget.get()

                node['properties'][prop_name]['default'] = value

                display_value = 'Yes' if prop_details['type'] == 'boolean' and value else value
                canvas_item_key = f'prop_{prop_name}'
                if canvas_item_key in node['canvas_items']:
                    self.canvas.itemconfigure(node['canvas_items'][canvas_item_key], text=f"{prop_name}: {display_value}")

            if 'node_name' in node['properties']:
                new_node_name = node['properties']['node_name']['default']
                node['title'] = new_node_name
                title_item = node['canvas_items'].get('title')
                if title_item:
                    self.canvas.itemconfigure(title_item, text=new_node_name)

            prop_window.destroy()
            self.redraw_canvas()
            self.is_modified = True
            self.update_save_button_state()

        # Main properties window
        prop_window = tk.Toplevel(self.editor_window)
        prop_window.title(f"Edit Node Properties - {node['title']}")
        prop_window.geometry("350x600")
        prop_window.minsize(350, 550)  # Set minimum window size
        prop_window.resizable(True, True)

        # Create node instance to get fresh property definitions
        node_class = self.get_node_class_by_type(node['type'])
        node_instance = node_class(node_id=node['id'], config=self.config)
        fresh_properties = node_instance.define_properties()

        # Scrollable frame setup
        content_frame = ttk.Frame(prop_window)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Create canvas with explicit width
        canvas = tk.Canvas(content_frame, width=330)
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        # Bind mouse wheel events to the canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        prop_window.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width-4))
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Property widgets
        prop_widgets = {}
        var_states = {}

        for prop_name, prop_details in fresh_properties.items():
            # Get current value from node
            current_value = node['properties'].get(prop_name, {}).get('default', prop_details.get('default', ''))
            
            # Create label
            label_text = prop_details.get('label', prop_name)
            ttk.Label(scrollable_frame, text=label_text).pack(pady=5, anchor='w', padx=10)

            if prop_details['type'] == 'text':
                widget = ttk.Entry(scrollable_frame)
                widget.insert(0, str(current_value))
                widget.pack(fill='x', padx=10, pady=2)
            elif prop_details['type'] == 'dropdown':
                widget = ttk.Combobox(scrollable_frame, state="readonly")
                # Get options - either from function or direct list
                if callable(prop_details['options']):
                    options = prop_details['options']()
                else:
                    options = prop_details['options']
                widget['values'] = options
                if current_value in options:
                    widget.set(current_value)
                elif options:
                    widget.set(options[0])
                widget.pack(fill='x', padx=10, pady=2)
            elif prop_details['type'] == 'textarea':
                widget = tk.Text(scrollable_frame, height=10)
                widget.insert("1.0", str(current_value))
                widget.pack(fill='x', padx=10, pady=2)
            elif prop_details['type'] == 'boolean':
                var_states[prop_name] = tk.BooleanVar(value=current_value)
                widget = ttk.Checkbutton(scrollable_frame, variable=var_states[prop_name])
                widget.pack(anchor='w', padx=10, pady=2)
            else:
                widget = ttk.Entry(scrollable_frame)
                widget.insert(0, str(current_value))
                widget.pack(fill='x', padx=10, pady=2)

            prop_widgets[prop_name] = widget

        # Save button at bottom
        ttk.Button(scrollable_frame, text="Save", command=save_properties).pack(pady=20)

    def on_connector_press(self, event):
        pass  # Placeholder for any connector press actions

    def on_canvas_right_click(self, event):
        # Check if the click is on a node or not
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        on_node = False
        for item in items:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                on_node = True
                break
        if not on_node:
            # Show context menu with "Add" option and submenu of available nodes
            menu = tk.Menu(self.canvas, tearoff=0)
            add_menu = tk.Menu(menu, tearoff=0)
            node_names = [cls.__name__.replace('Node', '') for cls in self.node_classes]
            for node_name in node_names:
                add_menu.add_command(label=node_name, command=lambda n=node_name: self.add_node(n))
            menu.add_cascade(label="Add", menu=add_menu)
            menu.post(event.x_root, event.y_root)

    def save_node_graph(self):
        # Serialize nodes and connections
        graph_data = {
            'nodes': self.nodes,
            'connections': self.connections
        }

        # Get instruction set name
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Input Required", "Please enter a name for the instruction set.")
            return
        self.instruction_name = name

        # Save graph data and name
        self.configured_graph = graph_data
        self.configured_name = self.instruction_name

        if self.save_callback:
            self.save_callback(self)

        # Reset modification flag
        self.is_modified = False
        self.update_save_button_state()

        # Close the editor window
        self.on_close()

    # New methods for resizing
    def on_resize_start(self, event):
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
        if not self.resizing_node_id:
            return

        # Get the current node being resized
        node = self.nodes[self.resizing_node_id]
        node_type = node.get('type', 'Unknown')  # Get the node type for background color

        # Calculate new dimensions
        x1, y1 = node['x'], node['y']
        x2, y2 = event.x, event.y
        
        # Enforce minimum size
        new_width = max(x2 - x1, 100)  # Minimum width of 100
        new_height = max(y2 - y1, 100)  # Minimum height of 100

        # Update node dimensions
        node['width'] = new_width
        node['height'] = new_height

        # Update visual elements
        if self.resizing_node_id in self.nodes:
            # Update the rounded rectangle
            rect = node['canvas_items']['rect']
            drag_bar = node['canvas_items']['drag_bar']
            x1, y1 = node['x'], node['y']
            x2, y2 = x1 + new_width, y1 + new_height
            
            # Update main rectangle
            self.canvas.delete(rect)
            bg_color = '#ffcccc' if node_type not in NODE_REGISTRY else 'white'  # Red background for missing nodes
            new_rect = self.create_rounded_rectangle(
                x1, y1, x2, y2,
                radius=10,
                fill=bg_color,
                outline='black',
                tags=('node', node['id'], 'rect')
            )
            node['canvas_items']['rect'] = new_rect

            # Update drag bar
            self.canvas.delete(drag_bar)
            new_drag_bar = self.create_rounded_rectangle(
                x1, y1, x2, y1 + 25,  # Fixed height of 25 for drag bar
                radius=10,
                fill='#e0e0e0',
                outline='black',
                tags=('node', node['id'], 'drag_bar', 'draggable')
            )
            node['canvas_items']['drag_bar'] = new_drag_bar
            
            # Rebind drag bar events
            self.canvas.tag_bind(new_drag_bar, "<ButtonPress-1>", self.on_node_press)
            self.canvas.tag_bind(new_drag_bar, "<B1-Motion>", self.on_node_move)
            self.canvas.tag_bind(new_drag_bar, "<ButtonRelease-1>", self.on_node_release)
            
            # Update title position and make it draggable
            title = node['canvas_items']['title']
            title_text = self.canvas.itemcget(title, 'text')  # Get text before deleting
            self.canvas.delete(title)
            new_title = self.canvas.create_text(
                x1 + new_width/2, y1 + 25/2,  # Center in drag bar
                text=title_text,  # Use preserved text
                font=('Arial', 10, 'bold'),
                anchor='center',
                tags=('node', node['id'], 'title', 'draggable')
            )
            node['canvas_items']['title'] = new_title
            
            # Rebind title events
            self.canvas.tag_bind(new_title, "<ButtonPress-1>", self.on_node_press)
            self.canvas.tag_bind(new_title, "<B1-Motion>", self.on_node_move)
            self.canvas.tag_bind(new_title, "<ButtonRelease-1>", self.on_node_release)
            
            # If this is a missing node, update the X mark
            if node_type not in NODE_REGISTRY:
                padding = 40  # Same padding as in draw_node
                # Update first diagonal line
                if 'x_mark1' in node['canvas_items']:
                    self.canvas.coords(
                        node['canvas_items']['x_mark1'],
                        x1 + padding, y1 + padding,
                        x1 + new_width - padding, y1 + new_height - padding
                    )
                # Update second diagonal line
                if 'x_mark2' in node['canvas_items']:
                    self.canvas.coords(
                        node['canvas_items']['x_mark2'],
                        x1 + new_width - padding, y1 + padding,
                        x1 + padding, y1 + new_height - padding
                    )

            # Update the properties (description) position and text
            properties_y = y1 + 40
            description = node['properties'].get('description', {}).get('default', '')  # Get the description
            if description:
                max_chars = 30  # Limit for better display
                if len(description) > max_chars:
                    description = description[:max_chars-3] + "..."
                prop_item = node['canvas_items'].get('description')
                if prop_item:
                    self.canvas.itemconfigure(prop_item, text=description, width=new_width - 20)
                    self.canvas.coords(prop_item, x1 + new_width / 2, properties_y)

            # Update input connectors
            input_x = x1
            num_inputs = len(node['inputs'])
            input_gap = (new_height - 40) / (num_inputs + 1) if num_inputs > 0 else new_height/2
            for idx, input_name in enumerate(node['inputs']):
                connector_y = y1 + 40 + (idx + 1) * input_gap
                input_connector = node['canvas_items'][f'input_{input_name}']
                self.canvas.delete(input_connector)
                
                # Recreate input connector
                new_connector = self.canvas.create_oval(
                    input_x - 5, connector_y - 5,
                    input_x + 5, connector_y + 5,
                    fill='lightblue',
                    tags=('node', node['id'], f'input_{input_name}')
                )
                node['canvas_items'][f'input_{input_name}'] = new_connector
                
                # Rebind input connector events
                self.canvas.tag_bind(new_connector, '<Button-1>', self.on_connector_press)
                
                input_label = node['canvas_items'][f'input_label_{input_name}']
                self.canvas.coords(input_label, input_x + 15, connector_y)

            # Update output connectors
            output_x = x1 + new_width
            num_outputs = len(node['outputs'])
            output_gap = (new_height - 40) / (num_outputs + 1) if num_outputs > 0 else new_height/2
            for idx, output_name in enumerate(node['outputs']):
                connector_y = y1 + 40 + (idx + 1) * output_gap
                output_connector = node['canvas_items'][f'output_{output_name}']
                self.canvas.delete(output_connector)
                
                # Recreate output connector
                new_connector = self.canvas.create_oval(
                    output_x - 5, connector_y - 5,
                    output_x + 5, connector_y + 5,
                    fill='lightgreen',
                    tags=('node', node['id'], f'output_{output_name}')
                )
                node['canvas_items'][f'output_{output_name}'] = new_connector
                
                # Rebind output connector events
                self.canvas.tag_bind(new_connector, '<Button-1>', self.start_connection)
                
                output_label = node['canvas_items'][f'output_label_{output_name}']
                self.canvas.coords(output_label, output_x - 15, connector_y)

            # Update resize handle
            resize_handle = node['canvas_items']['resize_handle']
            resize_handle_size = 10
            self.canvas.coords(
                resize_handle,
                x1 + new_width - resize_handle_size, y1 + new_height - resize_handle_size,
                x1 + new_width, y1 + new_height
            )

            # Redraw connections
            self.redraw_connections()

            # Raise all items except the rectangle to ensure they are visible
            for item_id in node['canvas_items'].values():
                self.canvas.tag_raise(item_id)

            # Mark as modified
            self.is_modified = True
            self.update_save_button_state()

    def on_resize_end(self, event):
        self.resizing_node_id = None
        self.resize_start_data = None

    def on_connection_right_click(self, event, conn):
        # Show context menu for deleting the connection
        menu = tk.Menu(self.canvas, tearoff=0)
        menu.add_command(label="Delete Connection", command=lambda: self.delete_connection(conn))
        menu.post(event.x_root, event.y_root)

    def delete_connection(self, conn):
        # Remove the line from the canvas
        if 'canvas_item' in conn and conn['canvas_item']:
            self.canvas.delete(conn['canvas_item'])
        # Remove the connection from the connections list
        if conn in self.connections:
            self.connections.remove(conn)

        # Mark as modified
        self.is_modified = True
        self.update_save_button_state()

    def clear_all_highlights(self):
        """Remove highlights from all nodes."""
        for node_id, node_data in self.nodes.items():
            rect = node_data['canvas_items']['rect']
            self.canvas.itemconfig(rect, outline='black', width=2)
            node_data['highlight_state'] = False

    def highlight_node(self, node_id, is_workflow=True):
        """Highlight the specified node."""
        if node_id not in self.nodes:
            return
            
        rect = self.nodes[node_id]['canvas_items']['rect']
        self.canvas.itemconfig(rect, outline='red', width=2)
        
        # Set the highlight state if this is from workflow execution
        if is_workflow:
            self.nodes[node_id]['highlight_state'] = True

    def remove_highlight(self, node_id):
        """Remove highlight from the specified node."""
        if node_id not in self.nodes:
            return
            
        rect = self.nodes[node_id]['canvas_items']['rect']
        self.canvas.itemconfig(rect, outline='black', width=2)
        self.nodes[node_id]['highlight_state'] = False

    def on_node_enter(self, node_id):
        """Handle mouse enter event on a node."""
        # Only highlight if the node is not already highlighted by workflow execution
        if node_id in self.nodes and not self.nodes[node_id].get('highlight_state', False):
            self.highlight_node(node_id, is_workflow=False)
    
    def on_node_leave(self, node_id):
        """Handle mouse leave event on a node."""
        # Only remove highlight if it was set by mouse hover, not by workflow execution
        if node_id in self.nodes and not self.nodes[node_id].get('highlight_state', False):
            self.remove_highlight(node_id)

    def start_connection(self, event):
        """Start drawing a connection from an output connector."""
        tags = self.canvas.gettags('current')
        if len(tags) < 3:
            return
        output_name = next((tag.split('_', 1)[1] for tag in tags if tag.startswith('output_')), None)
        node_id = next((tags[i+1] for i, tag in enumerate(tags) if tag == 'node'), None)
        
        if not output_name or not node_id:
            return
            
        self.connection_start = (node_id, output_name)
        self.temp_line_start = self.get_connector_position(node_id, output_name, 'output')
        self.temp_line = self.canvas.create_line(
            self.temp_line_start[0], self.temp_line_start[1],
            event.x, event.y, fill='gray', dash=(2, 2)
        )
        self.canvas.bind("<Motion>", self.update_temp_line)
        self.canvas.bind("<ButtonRelease-1>", self.check_connection_end)
