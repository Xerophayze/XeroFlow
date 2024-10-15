# node_editor.py

import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import math
import os
import importlib
import inspect

from node_registry import NODE_REGISTRY  # Import the registry
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
        """
        Retrieve the node class based on the node type/name.
        """
        return NODE_REGISTRY.get(node_type)

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
        for node in self.nodes.values():
            node_type = node['type']
            self.node_counter[node_type] += 1

    def on_node_dropdown_select(self, event):
        pass  # Placeholder for any action on selection

    def on_add_button(self):
        node_type = self.node_var.get()
        if node_type:
            self.add_node(node_type)
            self.node_var.set('')  # Reset dropdown

    def add_node(self, node_type):
        node_class = self.get_node_class_by_type(node_type + 'Node')
        if not node_class:
            messagebox.showerror("Error", f"Node type '{node_type}' not found.")
            return

        node_id = str(uuid.uuid4())
        node_instance = node_class(node_id, self.config)

        node = {
            'id': node_instance.id,
            'type': node_class.__name__,
            'title': f"{node_type} Node {self.node_counter[node_class.__name__]+1}",
            'x': 50 + self.node_counter[node_class.__name__]*20,
            'y': 50 + self.node_counter[node_class.__name__]*20,
            'width': 150,
            'height': 80,  # Increased height for larger input field and checkboxes
            'properties': node_instance.properties,
            'inputs': node_instance.inputs,
            'outputs': node_instance.outputs,
            'connections': []
        }
        self.node_counter[node_class.__name__] += 1

        # Draw the node on the canvas
        self.nodes[node_id] = node
        self.draw_node(node)

        # Mark as modified
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
        width = node['width']
        height = node['height']
        node_type = node['type']

        # Calculate the minimum width based on the title length plus padding
        title_text = node['title']
        padding = 20  # Padding on each side
        temp_text = self.canvas.create_text(0, 0, text=title_text, font=('Arial', 12, 'bold'))
        text_bbox = self.canvas.bbox(temp_text)
        self.canvas.delete(temp_text)
        text_width = text_bbox[2] - text_bbox[0] if text_bbox else 0
        min_width = text_width + padding * 2

        # Ensure the node width is at least the minimum width
        if width < min_width:
            width = min_width
            node['width'] = min_width

        node['canvas_items'] = {}  # Initialize the canvas items dictionary

        # Draw rounded rectangle
        rect = self.create_rounded_rectangle(
            x, y, x + width, y + height,
            radius=20,
            fill='#ADD8E6',  # Light blue
            outline='black',
            width=2,
            tags=('node', node['id'], 'rect')
        )
        node['canvas_items']['rect'] = rect
        self.canvas.tag_bind(rect, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(rect, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(rect, "<ButtonRelease-1>", self.on_node_release)
        self.canvas.tag_bind(rect, "<Button-3>", self.on_right_click)
        self.canvas.tag_bind(rect, "<Enter>", lambda e, nid=node['id']: self.highlight_node(nid))
        self.canvas.tag_bind(rect, "<Leave>", lambda e, nid=node['id']: self.remove_highlight(nid))

        # Draw title
        title = self.canvas.create_text(
            x + width / 2, y + 15,
            text=node['title'],
            tags=('node', node['id'], 'title'),
            font=('Arial', 12, 'bold')
        )
        node['canvas_items']['title'] = title
        self.canvas.tag_bind(title, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(title, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(title, "<ButtonRelease-1>", self.on_node_release)
        self.canvas.tag_bind(title, "<Button-3>", self.on_right_click)
        self.canvas.tag_bind(title, "<Enter>", lambda e, nid=node['id']: self.highlight_node(nid))
        self.canvas.tag_bind(title, "<Leave>", lambda e, nid=node['id']: self.remove_highlight(nid))

        # Draw properties (description with character limit)
        properties_y = y + 40  # Adjust this value to move the description lower than the title
        description = node['properties'].get('description', {}).get('default', '')  # Get the description

        if description:
            # Calculate the maximum number of characters that can fit in the node width
            max_chars = self.calculate_max_chars(width - 40)  # Subtract padding
            truncated_description = description[:max_chars]  # Truncate the description

            # Draw the truncated description centered
            prop_item = self.canvas.create_text(
                x + width / 2, properties_y,
                text=truncated_description,
                anchor='n',  # Align text to top center
                tags=('node', node['id'], 'prop_description'),
                font=('Arial', 10),
                width=width - 40  # Wrap text within the node
            )
            node['canvas_items']['prop_description'] = prop_item

        # Draw input connectors
        input_x = x
        num_inputs = len(node['inputs'])
        input_gap = (height - 40) / (num_inputs + 1)
        for idx, input_name in enumerate(node['inputs']):
            connector_y = y + 20 + (idx + 1) * input_gap
            input_connector = self.canvas.create_oval(
                input_x, connector_y - 5,
                input_x + 10, connector_y + 5,
                fill='black',
                tags=('input', node['id'], f'input_{input_name}')
            )
            node['canvas_items'][f'input_{input_name}'] = input_connector
            self.canvas.tag_bind(input_connector, "<ButtonPress-1>", self.on_connector_press)
            self.canvas.tag_bind(input_connector, "<Enter>", lambda e: self.canvas.itemconfig(e.widget.find_withtag('current'), fill='red'))
            self.canvas.tag_bind(input_connector, "<Leave>", lambda e: self.canvas.itemconfig(e.widget.find_withtag('current'), fill='black'))

        # Draw output connectors
        output_x = x + width
        num_outputs = len(node['outputs'])
        output_gap = (height - 40) / (num_outputs + 1)
        for idx, output_name in enumerate(node['outputs']):
            connector_y = y + 20 + (idx + 1) * output_gap
            output_connector = self.canvas.create_oval(
                output_x - 10, connector_y - 5,
                output_x, connector_y + 5,
                fill='green',
                tags=('output', node['id'], f'output_{output_name}')
            )
            node['canvas_items'][f'output_{output_name}'] = output_connector
            self.canvas.tag_bind(output_connector, "<ButtonPress-1>", self.start_connection)
            self.canvas.tag_bind(output_connector, "<Enter>", lambda e: self.canvas.itemconfig(e.widget.find_withtag('current'), fill='lime'))
            self.canvas.tag_bind(output_connector, "<Leave>", lambda e: self.canvas.itemconfig(e.widget.find_withtag('current'), fill='green'))

        # Draw resize handle
        resize_handle_size = 10
        resize_handle = self.canvas.create_rectangle(
            x + width - resize_handle_size, y + height - resize_handle_size,
            x + width, y + height,
            fill='gray',
            tags=('node', node['id'], 'resize_handle')
        )
        node['canvas_items']['resize_handle'] = resize_handle
        self.canvas.tag_bind(resize_handle, "<ButtonPress-1>", self.on_resize_press)
        self.canvas.tag_bind(resize_handle, "<B1-Motion>", self.on_resize_move)
        self.canvas.tag_bind(resize_handle, "<ButtonRelease-1>", self.on_resize_release)
        self.canvas.tag_bind(resize_handle, "<Enter>", lambda e: self.canvas.itemconfig(e.widget.find_withtag('current'), fill='darkgray'))
        self.canvas.tag_bind(resize_handle, "<Leave>", lambda e: self.canvas.itemconfig(e.widget.find_withtag('current'), fill='gray'))

        # Redraw connections to ensure they're on top
        self.redraw_connections()

    def on_resize_move(self, event):
        if self.resizing_node_id:
            dx = event.x - self.resize_start_data['x']
            dy = event.y - self.resize_start_data['y']
            new_width = self.resize_start_data['width'] + dx
            new_height = self.resize_start_data['height'] + dy

            # Set minimum size based on the title text length
            node = self.nodes[self.resizing_node_id]
            title_text = node['title']
            padding = 20  # Padding on each side
            temp_text = self.canvas.create_text(0, 0, text=title_text, font=('Arial', 12, 'bold'))
            text_bbox = self.canvas.bbox(temp_text)
            self.canvas.delete(temp_text)
            text_width = text_bbox[2] - text_bbox[0] if text_bbox else 0
            min_width = text_width + padding * 2

            min_height = 100  # Minimum height for the node
            if new_width < min_width:
                new_width = min_width
            if new_height < min_height:
                new_height = min_height

            # Update node dimensions
            node['width'] = new_width
            node['height'] = new_height

            # Update the rounded rectangle
            rect = node['canvas_items']['rect']
            x1, y1 = node['x'], node['y']
            x2, y2 = x1 + new_width, y1 + new_height
            self.canvas.delete(rect)
            new_rect = self.create_rounded_rectangle(
                x1, y1, x2, y2,
                radius=20,
                fill='#ADD8E6',
                outline='black',
                width=2,
                tags=('node', node['id'], 'rect')
            )
            node['canvas_items']['rect'] = new_rect
            self.canvas.tag_bind(new_rect, "<ButtonPress-1>", self.on_node_press)
            self.canvas.tag_bind(new_rect, "<B1-Motion>", self.on_node_move)
            self.canvas.tag_bind(new_rect, "<ButtonRelease-1>", self.on_node_release)
            self.canvas.tag_bind(new_rect, "<Button-3>", self.on_right_click)
            self.canvas.tag_bind(new_rect, "<Enter>", lambda e, nid=node['id']: self.highlight_node(nid))
            self.canvas.tag_bind(new_rect, "<Leave>", lambda e, nid=node['id']: self.remove_highlight(nid))

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

            # Update the properties (description) position and text
            properties_y = y1 + 40
            description = node['properties'].get('description', {}).get('default', '')  # Get the description
            if description:
                max_chars = self.calculate_max_chars(new_width - 40)  # Subtract padding
                truncated_description = description[:max_chars]  # Truncate the description
                prop_item = node['canvas_items'].get('prop_description')
                if prop_item:
                    self.canvas.itemconfigure(prop_item, text=truncated_description, width=new_width - 40)
                    self.canvas.coords(prop_item, x1 + new_width / 2, properties_y)

            # Update input connectors
            input_x = x1
            num_inputs = len(node['inputs'])
            input_gap = (new_height - 40) / (num_inputs + 1)
            for idx, input_name in enumerate(node['inputs']):
                connector_y = y1 + 20 + (idx + 1) * input_gap
                input_connector = node['canvas_items'][f'input_{input_name}']
                self.canvas.coords(
                    input_connector,
                    input_x, connector_y - 5,
                    input_x + 10, connector_y + 5
                )

            # Update output connectors
            output_x = x1 + new_width
            num_outputs = len(node['outputs'])
            output_gap = (new_height - 40) / (num_outputs + 1)
            for idx, output_name in enumerate(node['outputs']):
                connector_y = y1 + 20 + (idx + 1) * output_gap
                output_connector = node['canvas_items'][f'output_{output_name}']
                self.canvas.coords(
                    output_connector,
                    output_x - 10, connector_y - 5,
                    output_x, connector_y + 5
                )

            # Redraw connections
            self.redraw_connections()

            # Raise all items except the rectangle to ensure they are visible
            for key, item in node['canvas_items'].items():
                if key != 'rect':
                    self.canvas.tag_raise(item)

            # Mark as modified
            self.is_modified = True
            self.update_save_button_state()

    def calculate_max_chars(self, width):
        """Calculate the maximum number of characters that can fit within the specified width."""
        test_text = "M"  # Use a character that is approximately the average width
        temp_text = self.canvas.create_text(0, 0, text=test_text, font=('Arial', 10))
        char_bbox = self.canvas.bbox(temp_text)
        char_width = char_bbox[2] - char_bbox[0] if char_bbox else 7
        self.canvas.delete(temp_text)
        max_chars = int((width) / char_width)  # Calculate how many characters fit
        return max_chars

    def on_node_press(self, event):
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
            # Move all items with the same node id
            tags = self.canvas.gettags(self.selected_node)
            node_id = tags[tags.index('node') + 1]
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
        if len(tags) < 3:
            return
        output_name = tags[2].split('_', 1)[1]  # e.g., output_response -> response
        node_id = tags[1]
        self.connection_start = (node_id, output_name)
        self.temp_line_start = self.get_connector_position(node_id, output_name, 'output')
        self.temp_line = self.canvas.create_line(
            self.temp_line_start[0], self.temp_line_start[1],
            event.x, event.y, fill='gray', dash=(2, 2)
        )
        self.canvas.bind("<Motion>", self.update_temp_line)
        self.canvas.bind("<ButtonRelease-1>", self.check_connection_end)

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

        # Get the item under the cursor
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in items:
            tags = self.canvas.gettags(item)
            if 'input' in tags:
                # Found an input connector
                if len(tags) < 3:
                    continue
                input_name = tags[2].split('_', 1)[1]
                to_node_id = tags[1]
                self.end_connection(to_node_id, input_name)
                return
        # If no input connector was found under cursor
        self.connection_start = None

    def end_connection(self, to_node_id, input_name):
        from_node_id, output_name = self.connection_start
        self.connection_start = None

        if from_node_id == to_node_id:
            messagebox.showerror("Invalid Connection", "Cannot connect a node to itself.")
            return

        # Removed the restriction on multiple connections to the same input

        # Create the connection
        connection = {
            'from_node': from_node_id,
            'from_output': output_name,
            'to_node': to_node_id,
            'to_input': input_name,
            'canvas_item': None  # Will be set when drawing
        }
        self.connections.append(connection)
        self.draw_connection(connection)

        # Mark as modified
        self.is_modified = True
        self.update_save_button_state()

    def draw_connection(self, conn, min_length=20):
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
        conn['canvas_item'] = line
        self.canvas.tag_bind(line, "<Button-3>", lambda e, c=conn: self.on_connection_right_click(e, c))

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

        # Scrollable frame setup
        content_frame = ttk.Frame(prop_window)
        content_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(content_frame)
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Packing scrollable area and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Property widgets
        prop_widgets = {}
        var_states = {}

        # Node name field
        if 'node_name' in node['properties']:
            prop_details = node['properties']['node_name']
            ttk.Label(scrollable_frame, text='node_name').pack(pady=5, anchor='w', padx=10)
            entry = ttk.Entry(scrollable_frame)
            entry.pack(pady=5, fill=tk.X, padx=10)
            entry.insert(0, prop_details.get('default', ''))
            prop_widgets['node_name'] = entry

        # Rest of the properties
        for prop_name, prop_details in node['properties'].items():
            if prop_name == 'node_name':
                continue

            ttk.Label(scrollable_frame, text=prop_name).pack(pady=5, anchor='w', padx=10)
            if prop_details['type'] == 'text':
                entry = ttk.Entry(scrollable_frame)
                entry.pack(pady=5, fill=tk.X, padx=10)
                entry.insert(0, prop_details.get('default', ''))
                prop_widgets[prop_name] = entry
            elif prop_details['type'] == 'dropdown':
                options = prop_details.get('options', [])
                combo = ttk.Combobox(scrollable_frame, values=options, state="readonly")
                combo.pack(pady=5, fill=tk.X, padx=10)
                combo.set(prop_details.get('default', options[0] if options else ''))
                prop_widgets[prop_name] = combo
            elif prop_details['type'] == 'textarea':
                text_widget = tk.Text(scrollable_frame, height=10, width=40)
                text_widget.pack(pady=5, fill=tk.BOTH, expand=True, padx=10)
                text_widget.insert("1.0", prop_details.get('default', ''))
                prop_widgets[prop_name] = text_widget
            elif prop_details['type'] == 'boolean':
                var = tk.BooleanVar()
                var.set(prop_details.get('default', False))
                check = ttk.Checkbutton(scrollable_frame, variable=var)
                check.pack(pady=5, anchor='w', padx=10)
                var_states[prop_name] = var
                prop_widgets[prop_name] = check
            else:
                entry = ttk.Entry(scrollable_frame)
                entry.pack(pady=5, fill=tk.X, padx=10)
                entry.insert(0, prop_details.get('default', ''))
                prop_widgets[prop_name] = entry

        # Centered button frame
        button_frame = ttk.Frame(prop_window)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10)

        inner_button_frame = ttk.Frame(button_frame)
        inner_button_frame.pack()

        save_btn = ttk.Button(inner_button_frame, text="Save", command=save_properties)
        save_btn.pack(side=tk.LEFT, padx=10)
        cancel_btn = ttk.Button(inner_button_frame, text="Cancel", command=prop_window.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=10)
    
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

    def on_resize_release(self, event):
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

    def highlight_node(self, node_id):
        """Highlight the specified node."""
        rect = self.nodes[node_id]['canvas_items']['rect']
        self.canvas.itemconfig(rect, outline='red', width=2)

    def remove_highlight(self, node_id):
        """Remove highlight from the specified node."""
        rect = self.nodes[node_id]['canvas_items']['rect']
        self.canvas.itemconfig(rect, outline='black', width=2)
