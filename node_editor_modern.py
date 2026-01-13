# node_editor_modern.py - Modern Node Editor with improved visuals

import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import math
import os
import importlib
import inspect
import json
from node_registry import NODE_REGISTRY
from nodes.missing_node import MissingNode
from nodes.base_node import BaseNode


class Theme:
    """Modern dark color scheme"""
    CANVAS_BG = '#1e1e2e'
    GRID_COLOR = '#2a2a3e'
    GRID_MAJOR_COLOR = '#353550'
    
    NODE_BG = '#2d2d44'
    NODE_HEADER = '#3d3d5c'
    NODE_BORDER = '#4a4a6a'
    NODE_BORDER_SELECTED = '#7c7cff'
    NODE_BORDER_HOVER = '#5a5a8a'
    NODE_SHADOW = '#15151f'
    
    NODE_TYPE_INPUT = '#2d5a2d'
    NODE_TYPE_OUTPUT = '#5a2d2d'
    NODE_TYPE_PROCESS = '#2d3d5a'
    NODE_TYPE_LOGIC = '#5a4a2d'
    NODE_TYPE_MISSING = '#8a2d2d'
    
    TEXT_PRIMARY = '#e0e0e0'
    TEXT_SECONDARY = '#a0a0a0'
    TEXT_MUTED = '#707080'
    
    CONNECTOR_INPUT = '#5599ff'
    CONNECTOR_OUTPUT = '#55ff99'
    CONNECTOR_HOVER = '#ffffff'
    
    CONNECTION_DEFAULT = '#5580aa'
    CONNECTION_ACTIVE = '#77aaff'
    CONNECTION_PREVIEW = '#ffffff'
    CONNECTION_FLOW = '#ffcc00'  # Yellow/gold for active data flow
    
    TOOLBAR_BG = '#252535'
    BUTTON_BG = '#3d3d5c'
    BUTTON_HOVER = '#4d4d6c'


def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))


class ModernNodeEditor:
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
        self.node_counter['MissingNode'] = 0
        self.node_drag_data = {'x': 0, 'y': 0}
        self.connection_start = None
        self.temp_line = None
        self.instruction_name = existing_name
        self.save_callback = save_callback
        self.close_callback = close_callback
        self.resizing_node_id = None
        self.resize_start_data = None
        self.is_modified = False
        self.moving_node_id = None
        
        # Zoom and pan - applied as world transform
        self.zoom_level = 1.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        self.panning = False
        self.pan_start = {'x': 0, 'y': 0}
        
        self.grid_size = 25
        self.snap_to_grid = True
        self.show_grid = True
        
        # Minimum node dimensions
        self.min_node_width = 140
        self.min_node_height = 80

        self.create_editor_window()

        if existing_graph:
            self.load_graph(existing_graph)
            self.redraw_canvas()
    
    # ==================== COORDINATE TRANSFORMS ====================
    def world_to_screen(self, wx, wy):
        """Convert world coordinates to screen coordinates."""
        sx = wx * self.zoom_level + self.pan_offset_x
        sy = wy * self.zoom_level + self.pan_offset_y
        return sx, sy
    
    def screen_to_world(self, sx, sy):
        """Convert screen coordinates to world coordinates."""
        wx = (sx - self.pan_offset_x) / self.zoom_level
        wy = (sy - self.pan_offset_y) / self.zoom_level
        return wx, wy

    def is_open(self):
        return self.editor_window.winfo_exists()

    def load_node_classes(self):
        return list(NODE_REGISTRY.values())

    def get_node_class_by_type(self, node_type):
        try:
            return NODE_REGISTRY.get(node_type, lambda: MissingNode(original_type=node_type))
        except Exception as e:
            print(f"Error getting node class for type {node_type}: {e}")
            return lambda: MissingNode(original_type=node_type)

    def create_editor_window(self):
        self.editor_window = tk.Toplevel(self.parent)
        self.editor_window.title("Node-Based Instruction Editor")
        self.editor_window.geometry("1200x800")
        self.editor_window.resizable(True, True)
        self.editor_window.configure(bg=Theme.CANVAS_BG)
        self.editor_window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.create_toolbar()

        canvas_frame = tk.Frame(self.editor_window, bg=Theme.CANVAS_BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        self.canvas = tk.Canvas(canvas_frame, bg=Theme.CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        self.create_bottom_panel()
        self.editor_window.after(100, self.draw_grid)

    def create_toolbar(self):
        toolbar = tk.Frame(self.editor_window, bg=Theme.TOOLBAR_BG, height=45)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text="Add Node:", bg=Theme.TOOLBAR_BG, fg=Theme.TEXT_PRIMARY, font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(10, 5), pady=10)

        self.node_var = tk.StringVar()
        node_names = sorted([cls.__name__.replace('Node', '') for cls in self.node_classes])
        self.node_dropdown = ttk.Combobox(toolbar, textvariable=self.node_var, values=node_names, state="readonly", width=20)
        self.node_dropdown.pack(side=tk.LEFT, padx=5, pady=10)

        self.create_button(toolbar, "Add", self.on_add_button).pack(side=tk.LEFT, padx=5, pady=10)

        tk.Frame(toolbar, width=2, bg=Theme.GRID_MAJOR_COLOR).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=8)

        tk.Label(toolbar, text="Zoom:", bg=Theme.TOOLBAR_BG, fg=Theme.TEXT_PRIMARY, font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(10, 5), pady=10)
        self.create_button(toolbar, "−", lambda: self.zoom(-0.1), width=3).pack(side=tk.LEFT, padx=2, pady=10)
        self.zoom_label = tk.Label(toolbar, text="100%", bg=Theme.TOOLBAR_BG, fg=Theme.TEXT_PRIMARY, font=('Segoe UI', 9), width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2, pady=10)
        self.create_button(toolbar, "+", lambda: self.zoom(0.1), width=3).pack(side=tk.LEFT, padx=2, pady=10)
        self.create_button(toolbar, "Reset View", self.reset_view).pack(side=tk.LEFT, padx=10, pady=10)

        self.grid_var = tk.BooleanVar(value=True)
        tk.Checkbutton(toolbar, text="Grid", variable=self.grid_var, bg=Theme.TOOLBAR_BG, fg=Theme.TEXT_PRIMARY,
                       selectcolor=Theme.NODE_BG, activebackground=Theme.TOOLBAR_BG, command=self.toggle_grid).pack(side=tk.LEFT, padx=10, pady=10)

        self.snap_var = tk.BooleanVar(value=True)
        tk.Checkbutton(toolbar, text="Snap", variable=self.snap_var, bg=Theme.TOOLBAR_BG, fg=Theme.TEXT_PRIMARY,
                       selectcolor=Theme.NODE_BG, activebackground=Theme.TOOLBAR_BG, command=self.toggle_snap).pack(side=tk.LEFT, padx=5, pady=10)

    def create_button(self, parent, text, command, width=None):
        btn = tk.Button(parent, text=text, bg=Theme.BUTTON_BG, fg=Theme.TEXT_PRIMARY,
                        activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY,
                        relief='flat', padx=10, pady=2, command=command)
        if width:
            btn.config(width=width)
        return btn

    def create_bottom_panel(self):
        bottom = tk.Frame(self.editor_window, bg=Theme.TOOLBAR_BG, height=50)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        bottom.pack_propagate(False)

        tk.Label(bottom, text="Instruction Set Name:", bg=Theme.TOOLBAR_BG, fg=Theme.TEXT_PRIMARY, font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(10, 5), pady=12)
        
        self.name_var = tk.StringVar(value=self.instruction_name)
        name_entry = tk.Entry(bottom, textvariable=self.name_var, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                              insertbackground=Theme.TEXT_PRIMARY, relief='flat', font=('Segoe UI', 10))
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=12)

        self.save_btn = self.create_button(bottom, "Save", self.save_node_graph)
        self.save_btn.config(state='disabled')
        self.save_btn.pack(side=tk.RIGHT, padx=5, pady=12)

        self.create_button(bottom, "Cancel", self.on_close).pack(side=tk.RIGHT, padx=5, pady=12)

    def draw_grid(self):
        self.canvas.delete('grid')
        if not self.show_grid:
            return
            
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        if w <= 1 or h <= 1:
            return
            
        grid_size = int(self.grid_size * self.zoom_level)
        if grid_size < 5:
            return  # Grid too small to draw
            
        # Calculate grid offset based on pan
        offset_x = self.pan_offset_x % grid_size
        offset_y = self.pan_offset_y % grid_size
        
        # Draw minor grid
        for x in range(int(offset_x), w + grid_size, grid_size):
            self.canvas.create_line(x, 0, x, h, fill=Theme.GRID_COLOR, tags='grid')
        for y in range(int(offset_y), h + grid_size, grid_size):
            self.canvas.create_line(0, y, w, y, fill=Theme.GRID_COLOR, tags='grid')
            
        # Draw major grid (every 4 cells)
        major_grid = grid_size * 4
        if major_grid >= 20:
            major_offset_x = self.pan_offset_x % major_grid
            major_offset_y = self.pan_offset_y % major_grid
            
            for x in range(int(major_offset_x), w + major_grid, major_grid):
                self.canvas.create_line(x, 0, x, h, fill=Theme.GRID_MAJOR_COLOR, tags='grid')
            for y in range(int(major_offset_y), h + major_grid, major_grid):
                self.canvas.create_line(0, y, w, y, fill=Theme.GRID_MAJOR_COLOR, tags='grid')
            
        self.canvas.tag_lower('grid')

    def zoom(self, delta, center_x=None, center_y=None):
        old_zoom = self.zoom_level
        new_zoom = max(0.25, min(2.0, self.zoom_level + delta))
        
        if new_zoom == old_zoom:
            return
            
        # If center point provided, zoom towards that point
        if center_x is not None and center_y is not None:
            # Convert center to world coords at old zoom
            world_x = (center_x - self.pan_offset_x) / old_zoom
            world_y = (center_y - self.pan_offset_y) / old_zoom
            
            # Update zoom
            self.zoom_level = new_zoom
            
            # Adjust pan so the world point stays at the same screen position
            self.pan_offset_x = center_x - world_x * new_zoom
            self.pan_offset_y = center_y - world_y * new_zoom
        else:
            self.zoom_level = new_zoom
            
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self.redraw_canvas()

    def reset_view(self):
        self.zoom_level = 1.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        self.zoom_label.config(text="100%")
        self.redraw_canvas()

    def toggle_grid(self):
        self.show_grid = self.grid_var.get()
        self.draw_grid()

    def toggle_snap(self):
        self.snap_to_grid = self.snap_var.get()

    def on_canvas_configure(self, event):
        self.draw_grid()

    def on_mouse_wheel(self, event):
        delta = 0.1 if event.delta > 0 else -0.1
        # Zoom centered on mouse position
        self.zoom(delta, event.x, event.y)

    def on_pan_start(self, event):
        self.panning = True
        self.pan_start = {'x': event.x, 'y': event.y}

    def on_pan_move(self, event):
        if self.panning:
            dx = event.x - self.pan_start['x']
            dy = event.y - self.pan_start['y']
            self.pan_offset_x += dx
            self.pan_offset_y += dy
            self.pan_start = {'x': event.x, 'y': event.y}
            self.redraw_canvas()

    def on_pan_end(self, event):
        self.panning = False

    def snap_position(self, x, y):
        if self.snap_to_grid:
            grid = self.grid_size
            x = round(x / grid) * grid
            y = round(y / grid) * grid
        return x, y

    def update_save_button_state(self):
        self.save_btn.config(state='normal' if self.is_modified else 'disabled')

    def on_close(self):
        if self.is_modified:
            if not messagebox.askokcancel("Quit", "You have unsaved changes. Discard and exit?"):
                return
        if self.close_callback:
            self.close_callback(self)
        self.editor_window.destroy()

    def load_graph(self, graph_data):
        self.nodes = graph_data.get('nodes', {})
        self.connections = graph_data.get('connections', [])
        self.node_counter = {cls.__name__: 0 for cls in self.node_classes}
        self.node_counter['MissingNode'] = 0
        for node in self.nodes.values():
            node_type = node['type']
            if node_type not in self.node_counter:
                self.node_counter[node_type] = 0
            self.node_counter[node_type] += 1
        
        # Restore viewport state if available
        viewport = graph_data.get('viewport', {})
        if viewport:
            # Restore window size
            window_width = viewport.get('window_width', 1200)
            window_height = viewport.get('window_height', 800)
            self.editor_window.geometry(f"{window_width}x{window_height}")
            
            # Restore zoom and pan
            self.zoom_level = viewport.get('zoom_level', 1.0)
            self.pan_offset_x = viewport.get('pan_offset_x', 0)
            self.pan_offset_y = viewport.get('pan_offset_y', 0)

    def on_add_button(self):
        node_type = self.node_var.get()
        if node_type:
            self.add_node(node_type)
            self.node_var.set('')

    def add_node(self, node_type):
        node_id = str(uuid.uuid4())
        node_class = self.get_node_class_by_type(node_type + 'Node')
        if not node_class:
            return

        node_instance = node_class(node_id, self.config)
        properties = node_instance.define_properties()

        x, y = self.snap_position(150, 150)
        
        node = {
            'id': node_id,
            'type': node_type + 'Node',
            'title': node_type,
            'x': x,
            'y': y,
            'width': 180,
            'height': 120,
            'properties': properties,
            'inputs': node_instance.define_inputs(),
            'outputs': node_instance.define_outputs(),
            'canvas_items': {},
            'highlight_state': False
        }

        self.nodes[node_id] = node
        self.draw_node(node)
        self.is_modified = True
        self.update_save_button_state()

    def get_node_header_color(self, node_type):
        node_type_lower = node_type.lower()
        if 'input' in node_type_lower or 'start' in node_type_lower or 'basic' in node_type_lower:
            return Theme.NODE_TYPE_PROCESS
        elif 'output' in node_type_lower or 'end' in node_type_lower:
            return Theme.NODE_TYPE_OUTPUT
        elif 'splitter' in node_type_lower or 'merger' in node_type_lower or 'conditional' in node_type_lower or 'router' in node_type_lower:
            return Theme.NODE_TYPE_LOGIC
        elif node_type not in NODE_REGISTRY:
            return Theme.NODE_TYPE_MISSING
        else:
            return Theme.NODE_HEADER

    def draw_node(self, node):
        # Get world coordinates and transform to screen
        wx, wy = node['x'], node['y']
        ww, wh = node.get('width', 180), node.get('height', 120)
        
        # Transform to screen coordinates
        x, y = self.world_to_screen(wx, wy)
        width = ww * self.zoom_level
        height = wh * self.zoom_level
        
        node_type = node.get('type', 'Unknown')
        header_height = 28 * self.zoom_level
        is_missing = node_type not in NODE_REGISTRY
        
        node['canvas_items'] = {}
        
        # Shadow
        shadow_offset = 4 * self.zoom_level
        shadow = self.canvas.create_rectangle(
            x + shadow_offset, y + shadow_offset,
            x + width + shadow_offset, y + height + shadow_offset,
            fill=Theme.NODE_SHADOW, outline='', tags=('node', node['id'], 'shadow')
        )
        node['canvas_items']['shadow'] = shadow
        
        # Body
        body = self.canvas.create_rectangle(
            x, y + header_height, x + width, y + height,
            fill=Theme.NODE_BG, outline=Theme.NODE_BORDER, width=2,
            tags=('node', node['id'], 'body')
        )
        node['canvas_items']['body'] = body
        
        # Header
        header_color = self.get_node_header_color(node_type)
        header = self.canvas.create_rectangle(
            x, y, x + width, y + header_height,
            fill=header_color, outline=Theme.NODE_BORDER, width=2,
            tags=('node', node['id'], 'header', 'draggable')
        )
        node['canvas_items']['header'] = header
        
        self.canvas.tag_bind(header, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(header, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(header, "<ButtonRelease-1>", self.on_node_release)
        
        self.canvas.tag_bind(body, "<Button-3>", self.on_right_click)
        self.canvas.tag_bind(body, "<Enter>", lambda e, nid=node['id']: self.on_node_enter(nid))
        self.canvas.tag_bind(body, "<Leave>", lambda e, nid=node['id']: self.on_node_leave(nid))
        self.canvas.tag_bind(header, "<Button-3>", self.on_right_click)

        # Title - scale font size with zoom
        title = node.get('title', node_type.replace('Node', ''))
        if is_missing:
            title = f"Missing: {node_type}"
        
        # Truncate title to fit width
        font_size = max(7, int(9 * self.zoom_level))
        max_title_chars = max(8, int(width / (font_size * 0.7)))
        if len(title) > max_title_chars:
            title = title[:max_title_chars-2] + "..."
            
        title_item = self.canvas.create_text(
            x + width/2, y + header_height/2,
            text=title, fill=Theme.TEXT_PRIMARY,
            font=('Segoe UI', font_size, 'bold'), anchor='center',
            tags=('node', node['id'], 'title', 'draggable')
        )
        node['canvas_items']['title'] = title_item
        
        self.canvas.tag_bind(title_item, "<ButtonPress-1>", self.on_node_press)
        self.canvas.tag_bind(title_item, "<B1-Motion>", self.on_node_move)
        self.canvas.tag_bind(title_item, "<ButtonRelease-1>", self.on_node_release)

        # Description - only show if there's enough space
        content_height = height - header_height
        if 'properties' in node and content_height > 40 * self.zoom_level:
            description = node['properties'].get('description', {}).get('default', '')
            if description:
                desc_font_size = max(6, int(8 * self.zoom_level))
                max_desc_chars = max(10, int((width - 20) / (desc_font_size * 0.6)))
                if len(description) > max_desc_chars:
                    description = description[:max_desc_chars-3] + "..."
                desc_item = self.canvas.create_text(
                    x + width/2, y + header_height + 15 * self.zoom_level,
                    text=description, fill=Theme.TEXT_SECONDARY,
                    font=('Segoe UI', desc_font_size), anchor='center',
                    width=width - 20 * self.zoom_level,
                    tags=('node', node['id'], 'description')
                )
                node['canvas_items']['description'] = desc_item

        self.draw_connectors(node, x, y, width, height, header_height)
        
        # Resize handle
        handle_size = 10 * self.zoom_level
        resize_handle = self.canvas.create_polygon(
            x + width, y + height - handle_size,
            x + width, y + height,
            x + width - handle_size, y + height,
            fill=Theme.NODE_BORDER, outline='',
            tags=('node', node['id'], 'resize_handle')
        )
        node['canvas_items']['resize_handle'] = resize_handle
        
        self.canvas.tag_bind(resize_handle, '<ButtonPress-1>', self.on_resize_start)
        self.canvas.tag_bind(resize_handle, '<B1-Motion>', self.on_resize_move)
        self.canvas.tag_bind(resize_handle, '<ButtonRelease-1>', self.on_resize_end)

    def draw_connectors(self, node, x, y, width, height, header_height):
        connector_radius = max(5, 7 * self.zoom_level)
        content_height = height - header_height
        label_font_size = max(6, int(8 * self.zoom_level))
        
        if 'inputs' in node:
            num_inputs = len(node['inputs'])
            gap = content_height / (num_inputs + 1) if num_inputs > 0 else content_height / 2
            for idx, input_name in enumerate(node['inputs']):
                cy = y + header_height + (idx + 1) * gap
                
                connector = self.canvas.create_oval(
                    x - connector_radius, cy - connector_radius,
                    x + connector_radius, cy + connector_radius,
                    fill=Theme.CONNECTOR_INPUT, outline=Theme.TEXT_PRIMARY, width=2,
                    tags=('node', node['id'], f'input_{input_name}', 'connector')
                )
                node['canvas_items'][f'input_{input_name}'] = connector
                self.canvas.tag_bind(connector, '<Button-1>', self.on_connector_press)
                self.canvas.tag_bind(connector, '<Enter>', lambda e, c=connector: self.on_connector_enter(c))
                self.canvas.tag_bind(connector, '<Leave>', lambda e, c=connector: self.on_connector_leave(c))
                
                # Only show labels if there's enough space
                if width > 80 * self.zoom_level:
                    label = self.canvas.create_text(
                        x + connector_radius + 5 * self.zoom_level, cy,
                        text=input_name, fill=Theme.TEXT_MUTED,
                        font=('Segoe UI', label_font_size), anchor='w',
                        tags=('node', node['id'], f'input_label_{input_name}')
                    )
                    node['canvas_items'][f'input_label_{input_name}'] = label

        if 'outputs' in node:
            num_outputs = len(node['outputs'])
            gap = content_height / (num_outputs + 1) if num_outputs > 0 else content_height / 2
            for idx, output_name in enumerate(node['outputs']):
                cy = y + header_height + (idx + 1) * gap
                
                connector = self.canvas.create_oval(
                    x + width - connector_radius, cy - connector_radius,
                    x + width + connector_radius, cy + connector_radius,
                    fill=Theme.CONNECTOR_OUTPUT, outline=Theme.TEXT_PRIMARY, width=2,
                    tags=('node', node['id'], f'output_{output_name}', 'connector')
                )
                node['canvas_items'][f'output_{output_name}'] = connector
                self.canvas.tag_bind(connector, '<Button-1>', self.start_connection)
                self.canvas.tag_bind(connector, '<Enter>', lambda e, c=connector: self.on_connector_enter(c))
                self.canvas.tag_bind(connector, '<Leave>', lambda e, c=connector: self.on_connector_leave(c))
                
                # Only show labels if there's enough space
                if width > 80 * self.zoom_level:
                    label = self.canvas.create_text(
                        x + width - connector_radius - 5 * self.zoom_level, cy,
                        text=output_name, fill=Theme.TEXT_MUTED,
                        font=('Segoe UI', label_font_size), anchor='e',
                        tags=('node', node['id'], f'output_label_{output_name}')
                    )
                    node['canvas_items'][f'output_label_{output_name}'] = label

    def on_connector_enter(self, connector):
        self.canvas.itemconfig(connector, outline=Theme.CONNECTOR_HOVER, width=3)

    def on_connector_leave(self, connector):
        self.canvas.itemconfig(connector, outline=Theme.TEXT_PRIMARY, width=2)

    def on_node_press(self, event):
        clicked_item = self.canvas.find_withtag('current')[0]
        tags = self.canvas.gettags(clicked_item)
        
        if 'draggable' not in tags:
            return
            
        try:
            node_id = tags[tags.index('node') + 1]
            self.moving_node_id = node_id
            self.node_drag_data['x'] = event.x
            self.node_drag_data['y'] = event.y
        except (ValueError, IndexError):
            self.moving_node_id = None

    def on_node_move(self, event):
        if not self.moving_node_id:
            return
        try:
            node_id = self.moving_node_id
            
            # Calculate screen delta
            screen_dx = event.x - self.node_drag_data['x']
            screen_dy = event.y - self.node_drag_data['y']
            
            # Convert to world delta (account for zoom)
            world_dx = screen_dx / self.zoom_level
            world_dy = screen_dy / self.zoom_level
            
            # Update world coordinates
            node = self.nodes[node_id]
            node['x'] += world_dx
            node['y'] += world_dy
            
            # Move all canvas items by screen delta (don't redraw - that breaks drag)
            items = self.canvas.find_withtag(node_id)
            for item in items:
                self.canvas.move(item, screen_dx, screen_dy)
            
            self.node_drag_data['x'] = event.x
            self.node_drag_data['y'] = event.y
            
            # Only redraw connections (they need recalculation)
            self.redraw_connections()
            
            self.is_modified = True
            self.update_save_button_state()
        except (ValueError, IndexError, KeyError):
            pass

    def on_node_release(self, event):
        if self.moving_node_id and self.snap_to_grid:
            node = self.nodes[self.moving_node_id]
            old_x, old_y = node['x'], node['y']
            new_x, new_y = self.snap_position(old_x, old_y)
            
            if new_x != old_x or new_y != old_y:
                node['x'], node['y'] = new_x, new_y
                # Redraw the node at snapped position
                for item_id in node['canvas_items'].values():
                    self.canvas.delete(item_id)
                self.draw_node(node)
                self.redraw_connections()
                
        self.moving_node_id = None

    def redraw_canvas(self):
        self.canvas.delete("all")
        self.draw_grid()
        for node_id in self.nodes:
            self.draw_node(self.nodes[node_id])
        self.redraw_connections()

    def redraw_connections(self):
        for item in self.canvas.find_withtag('connection'):
            self.canvas.delete(item)
        # Clear existing line segments tracking
        self.existing_line_segments = []
        for conn in self.connections:
            self.draw_connection(conn)

    def draw_connection(self, conn):
        from_x, from_y = self.get_connector_position(conn['from_node'], conn['from_output'], 'output')
        to_x, to_y = self.get_connector_position(conn['to_node'], conn['to_input'], 'input')
        
        if from_x == 0 and from_y == 0:
            return
        if to_x == 0 and to_y == 0:
            return

        # Get ALL node bounding boxes including source and target for proper routing
        all_boxes = self.get_node_bounding_boxes(exclude_nodes=[])
        
        # Get source and target node boxes separately for special handling
        source_box = self.get_single_node_box(conn['from_node'])
        target_box = self.get_single_node_box(conn['to_node'])
        
        # Get existing line segments for separation
        existing_segments = getattr(self, 'existing_line_segments', [])
        
        # Use A* pathfinding through visibility graph
        waypoints = self.astar_orthogonal_path(from_x, from_y, to_x, to_y, all_boxes, source_box, target_box, existing_segments)
        
        # Apply line separation to avoid parallel lines being too close
        waypoints = self.apply_line_separation(waypoints, existing_segments)
        
        # Store this connection's segments for future connections
        self.store_line_segments(waypoints)
        
        # Draw the connection as gradient-colored segments
        line_width = max(2, int(3 * self.zoom_level))
        self.draw_gradient_path(conn, waypoints, line_width)
    
    def store_line_segments(self, points):
        """Store line segments from a drawn connection for future separation calculations."""
        if not hasattr(self, 'existing_line_segments'):
            self.existing_line_segments = []
        
        # Convert flat points list to segments
        if len(points) < 4:
            return
        
        for i in range(0, len(points) - 2, 2):
            x1, y1 = points[i], points[i + 1]
            x2, y2 = points[i + 2], points[i + 3]
            
            # Determine if horizontal or vertical
            is_horizontal = abs(y1 - y2) < 5
            is_vertical = abs(x1 - x2) < 5
            
            if is_horizontal or is_vertical:
                self.existing_line_segments.append({
                    'x1': min(x1, x2),
                    'y1': min(y1, y2),
                    'x2': max(x1, x2),
                    'y2': max(y1, y2),
                    'horizontal': is_horizontal
                })
    
    def apply_line_separation(self, points, existing_segments):
        """Nudge line segments that run parallel and too close to existing lines."""
        if len(points) < 4 or not existing_segments:
            return points
        
        min_separation = 12 * self.zoom_level  # Minimum distance between parallel lines
        
        # Convert to list of (x, y) tuples for easier manipulation
        waypoints = []
        for i in range(0, len(points), 2):
            waypoints.append([points[i], points[i + 1]])
        
        # Check each segment of the new path
        for i in range(len(waypoints) - 1):
            p1 = waypoints[i]
            p2 = waypoints[i + 1]
            
            is_horizontal = abs(p1[1] - p2[1]) < 5
            is_vertical = abs(p1[0] - p2[0]) < 5
            
            if not (is_horizontal or is_vertical):
                continue
            
            # Check against existing segments
            for seg in existing_segments:
                # Only compare same orientation segments
                if is_horizontal and seg['horizontal']:
                    # Both horizontal - check if they overlap in X and are too close in Y
                    seg_min_x, seg_max_x = seg['x1'], seg['x2']
                    new_min_x, new_max_x = min(p1[0], p2[0]), max(p1[0], p2[0])
                    
                    # Check X overlap
                    if new_max_x > seg_min_x and new_min_x < seg_max_x:
                        # They overlap horizontally, check Y distance
                        y_dist = abs(p1[1] - seg['y1'])
                        if 0 < y_dist < min_separation:
                            # Too close - nudge this segment
                            nudge = min_separation - y_dist
                            if p1[1] > seg['y1']:
                                nudge = nudge  # Move down
                            else:
                                nudge = -nudge  # Move up
                            
                            # Only nudge middle waypoints, not start/end
                            if i > 0:
                                waypoints[i][1] += nudge
                            if i + 1 < len(waypoints) - 1:
                                waypoints[i + 1][1] += nudge
                
                elif is_vertical and not seg['horizontal']:
                    # Both vertical - check if they overlap in Y and are too close in X
                    seg_min_y, seg_max_y = seg['y1'], seg['y2']
                    new_min_y, new_max_y = min(p1[1], p2[1]), max(p1[1], p2[1])
                    
                    # Check Y overlap
                    if new_max_y > seg_min_y and new_min_y < seg_max_y:
                        # They overlap vertically, check X distance
                        x_dist = abs(p1[0] - seg['x1'])
                        if 0 < x_dist < min_separation:
                            # Too close - nudge this segment
                            nudge = min_separation - x_dist
                            if p1[0] > seg['x1']:
                                nudge = nudge  # Move right
                            else:
                                nudge = -nudge  # Move left
                            
                            # Only nudge middle waypoints, not start/end
                            if i > 0:
                                waypoints[i][0] += nudge
                            if i + 1 < len(waypoints) - 1:
                                waypoints[i + 1][0] += nudge
        
        # Convert back to flat list
        result = []
        for wp in waypoints:
            result.extend(wp)
        
        return result
    
    def get_single_node_box(self, node_id):
        """Get bounding box for a single node."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        
        padding = 10 * self.zoom_level
        sx, sy = self.world_to_screen(node['x'], node['y'])
        sw = node.get('width', 180) * self.zoom_level
        sh = node.get('height', 120) * self.zoom_level
        
        return {
            'id': node_id,
            'x1': sx - padding,
            'y1': sy - padding,
            'x2': sx + sw + padding,
            'y2': sy + sh + padding,
            'cx': sx + sw / 2,
            'cy': sy + sh / 2
        }
    
    def get_node_bounding_boxes(self, exclude_nodes=None):
        """Get bounding boxes for all nodes (in screen coordinates) for collision detection."""
        exclude_nodes = exclude_nodes or []
        boxes = []
        padding = 15 * self.zoom_level  # Padding around nodes
        
        for node_id, node in self.nodes.items():
            if node_id in exclude_nodes:
                continue
            
            # Convert world coords to screen coords
            sx, sy = self.world_to_screen(node['x'], node['y'])
            sw = node.get('width', 180) * self.zoom_level
            sh = node.get('height', 120) * self.zoom_level
            
            # Add padding
            boxes.append({
                'id': node_id,
                'x1': sx - padding,
                'y1': sy - padding,
                'x2': sx + sw + padding,
                'y2': sy + sh + padding,
                'cx': sx + sw / 2,  # Center X
                'cy': sy + sh / 2   # Center Y
            })
        
        return boxes
    
    def line_intersects_box(self, x1, y1, x2, y2, box):
        """Check if a line segment intersects a bounding box."""
        # Check if line is completely outside box
        if max(x1, x2) < box['x1'] or min(x1, x2) > box['x2']:
            return False
        if max(y1, y2) < box['y1'] or min(y1, y2) > box['y2']:
            return False
        
        # Check if either endpoint is inside the box
        if box['x1'] <= x1 <= box['x2'] and box['y1'] <= y1 <= box['y2']:
            return True
        if box['x1'] <= x2 <= box['x2'] and box['y1'] <= y2 <= box['y2']:
            return True
        
        # Check line intersection with box edges
        edges = [
            (box['x1'], box['y1'], box['x2'], box['y1']),  # Top
            (box['x1'], box['y2'], box['x2'], box['y2']),  # Bottom
            (box['x1'], box['y1'], box['x1'], box['y2']),  # Left
            (box['x2'], box['y1'], box['x2'], box['y2']),  # Right
        ]
        
        for ex1, ey1, ex2, ey2 in edges:
            if self.lines_intersect(x1, y1, x2, y2, ex1, ey1, ex2, ey2):
                return True
        
        return False
    
    def lines_intersect(self, x1, y1, x2, y2, x3, y3, x4, y4):
        """Check if two line segments intersect."""
        def ccw(ax, ay, bx, by, cx, cy):
            return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
        
        return (ccw(x1, y1, x3, y3, x4, y4) != ccw(x2, y2, x3, y3, x4, y4) and
                ccw(x1, y1, x2, y2, x3, y3) != ccw(x1, y1, x2, y2, x4, y4))
    
    def astar_orthogonal_path(self, from_x, from_y, to_x, to_y, node_boxes, source_box=None, target_box=None, existing_segments=None):
        """Use A* pathfinding on an orthogonal visibility graph to find optimal path.
        
        Key rules:
        - Output connections MUST go RIGHT first (away from source node)
        - Input connections MUST come from LEFT (into target node)
        """
        import heapq
        
        existing_segments = existing_segments or []
        offset = 25 * self.zoom_level
        corner_radius = 5 * self.zoom_level
        
        # Calculate mandatory exit/entry points
        # Output MUST go right first - exit point is to the RIGHT of source node
        if source_box:
            exit_x = source_box['x2'] + offset  # Right edge of source + offset
        else:
            exit_x = from_x + offset
        exit_point = (exit_x, from_y)
        
        # Input MUST come from left - entry point is to the LEFT of target node
        if target_box:
            entry_x = target_box['x1'] - offset  # Left edge of target - offset
        else:
            entry_x = to_x - offset
        entry_point = (entry_x, to_y)
        
        # Build visibility graph nodes from node box corners and edges
        graph_points = set()
        
        # Add mandatory waypoints
        graph_points.add(exit_point)
        graph_points.add(entry_point)
        
        # Add corner points around each obstacle (with margin)
        margin = 8 * self.zoom_level
        for box in node_boxes:
            # Four corners of each box (with margin)
            corners = [
                (box['x1'] - margin, box['y1'] - margin),  # Top-left
                (box['x2'] + margin, box['y1'] - margin),  # Top-right
                (box['x1'] - margin, box['y2'] + margin),  # Bottom-left
                (box['x2'] + margin, box['y2'] + margin),  # Bottom-right
            ]
            for c in corners:
                graph_points.add(c)
        
        # Add horizontal/vertical alignment points for better orthogonal routing
        all_x = set([p[0] for p in graph_points])
        all_y = set([p[1] for p in graph_points])
        
        # Add intersection points of horizontal and vertical lines
        for x in all_x:
            for y in all_y:
                # Check if this point is not inside any obstacle
                inside = False
                for box in node_boxes:
                    if box['x1'] <= x <= box['x2'] and box['y1'] <= y <= box['y2']:
                        inside = True
                        break
                if not inside:
                    graph_points.add((x, y))
        
        graph_points = list(graph_points)
        
        # Build adjacency - only orthogonal connections (horizontal or vertical)
        def can_connect(p1, p2):
            """Check if two points can be connected orthogonally without crossing obstacles."""
            x1, y1 = p1
            x2, y2 = p2
            
            # Must be orthogonal (same x or same y)
            if abs(x1 - x2) > 1 and abs(y1 - y2) > 1:
                return False
            
            # Check if line crosses any obstacle
            for box in node_boxes:
                if self.line_intersects_box(x1, y1, x2, y2, box):
                    return False
            return True
        
        def heuristic(p1, p2):
            """Manhattan distance heuristic for A*."""
            return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
        
        def get_neighbors(point):
            """Get orthogonally connected neighbors."""
            neighbors = []
            px, py = point
            
            for other in graph_points:
                if other == point:
                    continue
                ox, oy = other
                
                # Only orthogonal connections
                is_horizontal = abs(py - oy) < 1
                is_vertical = abs(px - ox) < 1
                
                if (is_horizontal or is_vertical) and can_connect(point, other):
                    # Cost includes distance + bend penalty
                    dist = abs(px - ox) + abs(py - oy)
                    neighbors.append((other, dist))
            
            return neighbors
        
        # A* algorithm - start from exit_point, goal is entry_point
        open_set = [(0, exit_point, [exit_point])]  # (f_score, current, path)
        closed_set = set()
        g_scores = {exit_point: 0}
        
        while open_set:
            _, current, path = heapq.heappop(open_set)
            
            if current in closed_set:
                continue
            
            # Check if we reached the entry point (close enough)
            if abs(current[0] - entry_point[0]) < offset and abs(current[1] - entry_point[1]) < offset:
                # Construct final path: connector -> exit_point -> path -> entry_point -> connector
                final_path = [(from_x, from_y)] + path + [entry_point, (to_x, to_y)]
                return self.smooth_waypoints(self.simplify_waypoints(final_path), corner_radius)
            
            closed_set.add(current)
            
            for neighbor, cost in get_neighbors(current):
                if neighbor in closed_set:
                    continue
                
                # Add bend penalty to encourage straighter paths
                bend_penalty = 0
                if len(path) >= 2:
                    prev = path[-2] if len(path) > 1 else path[-1]
                    curr = path[-1]
                    # Check if this creates a bend
                    prev_horiz = abs(prev[1] - curr[1]) < 1
                    next_horiz = abs(curr[1] - neighbor[1]) < 1
                    if prev_horiz != next_horiz:
                        bend_penalty = 50 * self.zoom_level  # Penalty for each bend
                
                tentative_g = g_scores[current] + cost + bend_penalty
                
                if neighbor not in g_scores or tentative_g < g_scores[neighbor]:
                    g_scores[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor, entry_point)
                    heapq.heappush(open_set, (f_score, neighbor, path + [neighbor]))
        
        # Fallback: simple direct path if A* fails
        return self.simple_orthogonal_fallback(from_x, from_y, to_x, to_y, corner_radius, source_box, target_box)
    
    def simple_orthogonal_fallback(self, from_x, from_y, to_x, to_y, corner_radius, source_box=None, target_box=None):
        """Simple fallback routing when A* doesn't find a path."""
        offset = 25 * self.zoom_level
        
        # Calculate proper exit and entry points
        if source_box:
            exit_x = source_box['x2'] + offset
        else:
            exit_x = from_x + offset
            
        if target_box:
            entry_x = target_box['x1'] - offset
        else:
            entry_x = to_x - offset
        
        # Check if we can do a simple path or need to go around
        if exit_x < entry_x:
            # Simple S-curve - exit is left of entry
            mid_x = (exit_x + entry_x) / 2
            waypoints = [
                (from_x, from_y),
                (exit_x, from_y),
                (mid_x, from_y),
                (mid_x, to_y),
                (entry_x, to_y),
                (to_x, to_y)
            ]
        else:
            # Need to go around - exit is right of or at entry
            route_y = max(from_y, to_y) + offset * 4
            waypoints = [
                (from_x, from_y),
                (exit_x, from_y),
                (exit_x, route_y),
                (entry_x, route_y),
                (entry_x, to_y),
                (to_x, to_y)
            ]
        
        return self.smooth_waypoints(self.simplify_waypoints(waypoints), corner_radius)
    
    def calculate_smart_path(self, from_x, from_y, to_x, to_y, node_boxes):
        """Calculate a path from source to target that avoids nodes.
        
        Rules:
        - Always exit OUTPUT going RIGHT
        - Always enter INPUT coming from LEFT
        - Use orthogonal (right-angle) routing
        - Add waypoints as needed to route around nodes
        """
        dx = to_x - from_x
        dy = to_y - from_y
        offset = 25 * self.zoom_level
        corner_radius = 6 * self.zoom_level
        
        # Generate candidate paths and pick the first clear one
        paths = self.generate_routing_candidates(from_x, from_y, to_x, to_y, node_boxes, offset)
        
        for waypoints in paths:
            if not self.path_intersects_nodes(waypoints, node_boxes):
                return self.smooth_waypoints(waypoints, corner_radius)
        
        # If all fail, use the last (most aggressive) routing
        return self.smooth_waypoints(paths[-1] if paths else [(from_x, from_y), (to_x, to_y)], corner_radius)
    
    def generate_routing_candidates(self, from_x, from_y, to_x, to_y, node_boxes, offset):
        """Generate multiple routing candidates in order of preference."""
        dx = to_x - from_x
        dy = to_y - from_y
        paths = []
        
        # Calculate useful reference points
        min_exit_x = from_x + offset  # Minimum X after exiting (go right first)
        max_enter_x = to_x - offset   # Maximum X before entering (come from left)
        
        # Get bounds of all nodes for routing around them
        if node_boxes:
            all_left = min(b['x1'] for b in node_boxes)
            all_right = max(b['x2'] for b in node_boxes)
            all_top = min(b['y1'] for b in node_boxes)
            all_bottom = max(b['y2'] for b in node_boxes)
        else:
            all_left = all_right = from_x
            all_top = all_bottom = from_y
        
        # CASE 1: Target is to the RIGHT and roughly same level - simple 2-turn path
        if dx > offset * 2 and abs(dy) < offset:
            # Direct horizontal with small vertical adjustment
            mid_x = from_x + dx / 2
            paths.append([
                (from_x, from_y),
                (mid_x, from_y),
                (mid_x, to_y),
                (to_x, to_y)
            ])
        
        # CASE 2: Target is to the RIGHT - standard S-curve (2 turns)
        if dx > offset * 2:
            mid_x = from_x + dx / 2
            paths.append([
                (from_x, from_y),
                (mid_x, from_y),
                (mid_x, to_y),
                (to_x, to_y)
            ])
        
        # CASE 3: Target is BELOW and to the right - go right, down, right
        if dx > 0 and dy > 0:
            paths.append([
                (from_x, from_y),
                (min_exit_x, from_y),
                (min_exit_x, to_y),
                (to_x, to_y)
            ])
        
        # CASE 4: Target is ABOVE and to the right - go right, up, right  
        if dx > 0 and dy < 0:
            paths.append([
                (from_x, from_y),
                (min_exit_x, from_y),
                (min_exit_x, to_y),
                (to_x, to_y)
            ])
        
        # CASE 5: Target is to the LEFT or only slightly right - need 4+ turns
        # Pattern: right → down/up → left → down/up → right into input
        if dx <= offset * 2:
            # Determine if we go above or below
            if dy >= 0:
                # Target is below-left: go right, down past target, left, up to target level, right into input
                route_y = max(from_y, to_y) + offset * 2
                # But check if we need to go below all nodes
                route_y = max(route_y, all_bottom + offset)
            else:
                # Target is above-left: go right, up past target, left, down to target level, right into input
                route_y = min(from_y, to_y) - offset * 2
                route_y = min(route_y, all_top - offset)
            
            paths.append([
                (from_x, from_y),
                (min_exit_x, from_y),
                (min_exit_x, route_y),
                (max_enter_x, route_y),
                (max_enter_x, to_y),
                (to_x, to_y)
            ])
        
        # CASE 6: Route completely around all nodes (fallback)
        # Go right past everything, then vertical, then left to target
        far_right = max(all_right + offset, from_x + offset, to_x + offset * 2)
        
        if dy >= 0:
            far_y = all_bottom + offset * 2
        else:
            far_y = all_top - offset * 2
        
        paths.append([
            (from_x, from_y),
            (far_right, from_y),
            (far_right, far_y),
            (max_enter_x, far_y),
            (max_enter_x, to_y),
            (to_x, to_y)
        ])
        
        # CASE 7: Even more aggressive - go way around
        very_far_right = all_right + offset * 3
        if dy >= 0:
            very_far_y = all_bottom + offset * 3
        else:
            very_far_y = all_top - offset * 3
        
        paths.append([
            (from_x, from_y),
            (very_far_right, from_y),
            (very_far_right, very_far_y),
            (to_x - offset * 2, very_far_y),
            (to_x - offset * 2, to_y),
            (to_x, to_y)
        ])
        
        return paths
    
    def path_intersects_nodes(self, waypoints, node_boxes):
        """Check if a path (list of waypoints) intersects any node boxes."""
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            for box in node_boxes:
                if self.line_intersects_box(x1, y1, x2, y2, box):
                    return True
        return False
    
    def simplify_waypoints(self, waypoints):
        """Remove redundant waypoints (collinear points, zero-length segments)."""
        if len(waypoints) < 3:
            return waypoints
        
        simplified = [waypoints[0]]
        
        for i in range(1, len(waypoints) - 1):
            prev = simplified[-1]
            curr = waypoints[i]
            next_pt = waypoints[i + 1]
            
            # Skip if this point is same as previous
            if abs(curr[0] - prev[0]) < 1 and abs(curr[1] - prev[1]) < 1:
                continue
            
            # Skip if collinear (all on same horizontal or vertical line)
            prev_horiz = abs(prev[1] - curr[1]) < 1
            next_horiz = abs(curr[1] - next_pt[1]) < 1
            prev_vert = abs(prev[0] - curr[0]) < 1
            next_vert = abs(curr[0] - next_pt[0]) < 1
            
            if prev_horiz and next_horiz:
                continue  # All horizontal, skip middle point
            if prev_vert and next_vert:
                continue  # All vertical, skip middle point
            
            simplified.append(curr)
        
        simplified.append(waypoints[-1])
        return simplified
    
    def smooth_waypoints(self, waypoints, corner_radius):
        """Convert waypoints to a smooth path with rounded corners."""
        if len(waypoints) < 2:
            return []
        
        # First simplify to remove redundant points
        waypoints = self.simplify_waypoints(waypoints)
        
        if len(waypoints) < 2:
            return []
        
        points = []
        
        for i, (x, y) in enumerate(waypoints):
            if i == 0:
                # Start point
                points.extend([x, y])
            elif i == len(waypoints) - 1:
                # End point
                points.extend([x, y])
            else:
                # Middle point - add rounded corner
                prev_x, prev_y = waypoints[i - 1]
                next_x, next_y = waypoints[i + 1]
                
                # Calculate direction vectors
                dx1 = x - prev_x
                dy1 = y - prev_y
                dx2 = next_x - x
                dy2 = next_y - y
                
                # Normalize and calculate corner points
                len1 = max(1, (dx1**2 + dy1**2)**0.5)
                len2 = max(1, (dx2**2 + dy2**2)**0.5)
                
                # Limit corner radius to half the segment length
                r = min(corner_radius, len1 / 3, len2 / 3)
                
                if r < 2:
                    # Too small for a curve, just add the point
                    points.extend([x, y])
                    continue
                
                # Points before and after the corner
                corner_start_x = x - (dx1 / len1) * r
                corner_start_y = y - (dy1 / len1) * r
                corner_end_x = x + (dx2 / len2) * r
                corner_end_y = y + (dy2 / len2) * r
                
                # Add corner curve points
                points.extend([corner_start_x, corner_start_y])
                
                # Add intermediate points for smooth corner curve (quadratic bezier)
                for t in [0.33, 0.67]:
                    mt = 1 - t
                    bx = mt*mt*corner_start_x + 2*mt*t*x + t*t*corner_end_x
                    by = mt*mt*corner_start_y + 2*mt*t*y + t*t*corner_end_y
                    points.extend([bx, by])
                
                points.extend([corner_end_x, corner_end_y])
        
        return points
    
    def draw_gradient_path(self, conn, points, line_width):
        """Draw a path with gradient coloring from start to end."""
        if len(points) < 4:
            return
        
        # Gradient colors (green output -> blue input)
        start_color = (85, 255, 153)   # #55ff99 - green (output)
        end_color = (85, 153, 255)     # #5599ff - blue (input)
        
        # Calculate total path length for gradient
        total_length = 0
        segments = []
        for i in range(0, len(points) - 2, 2):
            x1, y1 = points[i], points[i + 1]
            x2, y2 = points[i + 2], points[i + 3]
            seg_len = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
            segments.append((x1, y1, x2, y2, seg_len))
            total_length += seg_len
        
        if total_length == 0:
            return
        
        # Draw segments with interpolated colors
        canvas_items = []
        cumulative_length = 0
        
        for x1, y1, x2, y2, seg_len in segments:
            # Calculate color at start of segment
            t = cumulative_length / total_length
            r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
            color = f'#{r:02x}{g:02x}{b:02x}'
            
            line = self.canvas.create_line(
                x1, y1, x2, y2,
                fill=color, width=line_width,
                capstyle='round', joinstyle='round',
                tags=('connection', f'conn_{id(conn)}')
            )
            canvas_items.append(line)
            cumulative_length += seg_len
        
        # Store reference and bind events to all segments
        conn['canvas_items'] = canvas_items
        conn['canvas_item'] = canvas_items[0] if canvas_items else None
        
        for line in canvas_items:
            self.canvas.tag_bind(line, "<Button-3>", lambda e, c=conn: self.on_connection_right_click(e, c))
            self.canvas.tag_bind(line, "<Enter>", lambda e, items=canvas_items: self.highlight_connection(items, True))
            self.canvas.tag_bind(line, "<Leave>", lambda e, items=canvas_items: self.highlight_connection(items, False))
            self.canvas.tag_lower(line, 'node')
    
    def highlight_connection(self, items, highlight):
        """Highlight or unhighlight a connection."""
        for item in items:
            if highlight:
                self.canvas.itemconfig(item, width=4)
            else:
                self.canvas.itemconfig(item, width=max(2, int(3 * self.zoom_level)))

    def highlight_connection_flow(self, from_node_id, to_node_id):
        """Highlight a connection with marching ants animation to show data flow."""
        # Find the connection between these nodes
        for conn in self.connections:
            if conn['from_node'] == from_node_id and conn['to_node'] == to_node_id:
                canvas_items = conn.get('canvas_items', [])
                if canvas_items:
                    # Store original colors for restoration
                    if 'original_colors' not in conn:
                        conn['original_colors'] = []
                        for item in canvas_items:
                            try:
                                color = self.canvas.itemcget(item, 'fill')
                                conn['original_colors'].append(color)
                            except:
                                conn['original_colors'].append(Theme.CONNECTION_DEFAULT)
                    
                    # Mark connection as flowing
                    conn['is_flowing'] = True
                    conn['flow_offset'] = 0
                    
                    # Start the marching ants animation
                    self._animate_connection_flow(conn)
                break
    
    def _animate_connection_flow(self, conn):
        """Animate the marching ants effect on a flowing connection."""
        if not conn.get('is_flowing', False):
            return
        
        canvas_items = conn.get('canvas_items', [])
        if not canvas_items:
            return
        
        # Update dash offset for marching ants effect
        offset = conn.get('flow_offset', 0)
        dash_pattern = (8, 4)  # 8 pixels on, 4 pixels off
        
        for item in canvas_items:
            try:
                # Apply marching ants style with yellow/gold color
                self.canvas.itemconfig(
                    item, 
                    fill=Theme.CONNECTION_FLOW,
                    width=max(3, int(4 * self.zoom_level)),
                    dash=dash_pattern,
                    dashoffset=offset
                )
            except:
                pass
        
        # Increment offset for animation
        conn['flow_offset'] = (offset + 2) % 12
        
        # Schedule next frame if still flowing
        if conn.get('is_flowing', False):
            self.canvas.after(50, lambda: self._animate_connection_flow(conn))
    
    def remove_connection_flow(self, from_node_id, to_node_id):
        """Remove the flow highlight from a connection."""
        for conn in self.connections:
            if conn['from_node'] == from_node_id and conn['to_node'] == to_node_id:
                conn['is_flowing'] = False
                canvas_items = conn.get('canvas_items', [])
                original_colors = conn.get('original_colors', [])
                
                for i, item in enumerate(canvas_items):
                    try:
                        # Restore original color and remove dash
                        color = original_colors[i] if i < len(original_colors) else Theme.CONNECTION_DEFAULT
                        self.canvas.itemconfig(
                            item,
                            fill=color,
                            width=max(2, int(3 * self.zoom_level)),
                            dash='',
                            dashoffset=0
                        )
                    except:
                        pass
                break
    
    def highlight_incoming_connections(self, node_id):
        """Highlight all connections leading into a node with flow animation."""
        for conn in self.connections:
            if conn['to_node'] == node_id:
                self.highlight_connection_flow(conn['from_node'], node_id)
    
    def remove_incoming_connection_highlights(self, node_id):
        """Remove flow highlights from all connections leading into a node."""
        for conn in self.connections:
            if conn['to_node'] == node_id:
                self.remove_connection_flow(conn['from_node'], node_id)

    def bezier_curve(self, x0, y0, x1, y1, x2, y2, x3, y3, steps=20):
        points = []
        for i in range(steps + 1):
            t = i / steps
            t2 = t * t
            t3 = t2 * t
            mt = 1 - t
            mt2 = mt * mt
            mt3 = mt2 * mt
            
            x = mt3 * x0 + 3 * mt2 * t * x1 + 3 * mt * t2 * x2 + t3 * x3
            y = mt3 * y0 + 3 * mt2 * t * y1 + 3 * mt * t2 * y2 + t3 * y3
            points.extend([x, y])
        return points

    def get_connector_position(self, node_id, connector_name, connector_type):
        node = self.nodes.get(node_id)
        if not node:
            return (0, 0)
        key = f'{connector_type}_{connector_name}'
        item = node['canvas_items'].get(key)
        if not item:
            return (0, 0)
        coords = self.canvas.coords(item)
        if len(coords) < 4:
            return (0, 0)
        x = (coords[0] + coords[2]) / 2
        y = (coords[1] + coords[3]) / 2
        return (x, y)

    def start_connection(self, event):
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
            event.x, event.y, fill=Theme.CONNECTION_PREVIEW, width=3, dash=(5, 5)
        )
        self.canvas.bind("<Motion>", self.update_temp_line)
        self.canvas.bind("<ButtonRelease-1>", self.check_connection_end)

    def update_temp_line(self, event):
        if self.temp_line:
            self.canvas.coords(self.temp_line, self.temp_line_start[0], self.temp_line_start[1], event.x, event.y)

    def check_connection_end(self, event):
        self.canvas.unbind("<Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        if self.temp_line:
            self.canvas.delete(self.temp_line)
            self.temp_line = None

        if not self.connection_start:
            return

        items = self.canvas.find_overlapping(event.x-15, event.y-15, event.x+15, event.y+15)
        target_item = None
        target_tags = None

        for item in items:
            tags = self.canvas.gettags(item)
            if any('input_' in tag for tag in tags):
                target_item = item
                target_tags = tags
                break

        if target_item and target_tags:
            try:
                node_index = target_tags.index('node')
                node_id = target_tags[node_index + 1] if node_index + 1 < len(target_tags) else None
            except ValueError:
                node_id = None

            input_name = next((tag.split('_', 1)[1] for tag in target_tags if tag.startswith('input_')), None)

            if node_id and input_name:
                from_node_id, output_name = self.connection_start

                if from_node_id == node_id:
                    messagebox.showerror("Invalid Connection", "Cannot connect a node to itself.")
                    self.connection_start = None
                    return

                for conn in self.connections:
                    if (conn['from_node'] == from_node_id and conn['to_node'] == node_id and
                        conn['from_output'] == output_name and conn['to_input'] == input_name):
                        messagebox.showinfo("Connection exists", "This connection already exists.")
                        self.connection_start = None
                        return

                connection = {
                    'from_node': from_node_id,
                    'from_output': output_name,
                    'to_node': node_id,
                    'to_input': input_name
                }
                self.connections.append(connection)
                self.draw_connection(connection)
                self.is_modified = True
                self.update_save_button_state()

        self.connection_start = None

    def on_right_click(self, event):
        item = self.canvas.find_withtag('current')
        if item:
            tags = self.canvas.gettags(item[0])
            if 'node' in tags:
                node_id = tags[tags.index('node') + 1]
                node = self.nodes.get(node_id)
                if node:
                    self.show_context_menu(event, node)
                    return "break"

    def show_context_menu(self, event, node):
        menu = tk.Menu(self.canvas, tearoff=0, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                       activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY)
        menu.add_command(label="Edit Properties", command=lambda: self.edit_node_properties(node))
        menu.add_separator()
        menu.add_command(label="Delete Node", command=lambda: self.delete_node(node))
        menu.post(event.x_root, event.y_root)

    def delete_node(self, node):
        self.connections = [c for c in self.connections if c['from_node'] != node['id'] and c['to_node'] != node['id']]
        del self.nodes[node['id']]
        self.redraw_canvas()
        self.is_modified = True
        self.update_save_button_state()

    def on_canvas_right_click(self, event):
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        on_node = any('node' in self.canvas.gettags(item) for item in items)
        
        if not on_node:
            menu = tk.Menu(self.canvas, tearoff=0, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                           activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY)
            add_menu = tk.Menu(menu, tearoff=0, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                               activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY)
            
            node_names = sorted([cls.__name__.replace('Node', '') for cls in self.node_classes])
            for node_name in node_names:
                add_menu.add_command(label=node_name, command=lambda n=node_name, x=event.x, y=event.y: self.add_node_at(n, x, y))
            menu.add_cascade(label="Add Node", menu=add_menu)
            menu.post(event.x_root, event.y_root)

    def add_node_at(self, node_type, screen_x, screen_y):
        node_id = str(uuid.uuid4())
        node_class = self.get_node_class_by_type(node_type + 'Node')
        if not node_class:
            return

        node_instance = node_class(node_id, self.config)
        properties = node_instance.define_properties()

        # Convert screen coordinates to world coordinates
        world_x, world_y = self.screen_to_world(screen_x, screen_y)
        world_x, world_y = self.snap_position(world_x, world_y)
        
        node = {
            'id': node_id,
            'type': node_type + 'Node',
            'title': node_type,
            'x': world_x,
            'y': world_y,
            'width': 180,
            'height': 120,
            'properties': properties,
            'inputs': node_instance.define_inputs(),
            'outputs': node_instance.define_outputs(),
            'canvas_items': {},
            'highlight_state': False
        }

        self.nodes[node_id] = node
        self.draw_node(node)
        self.is_modified = True
        self.update_save_button_state()

    def on_connection_right_click(self, event, conn):
        menu = tk.Menu(self.canvas, tearoff=0, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                       activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY)
        menu.add_command(label="Delete Connection", command=lambda: self.delete_connection(conn))
        menu.post(event.x_root, event.y_root)

    def delete_connection(self, conn):
        # Delete all canvas items (connections are now multi-segment)
        if 'canvas_items' in conn:
            for item in conn['canvas_items']:
                self.canvas.delete(item)
        elif 'canvas_item' in conn and conn['canvas_item']:
            self.canvas.delete(conn['canvas_item'])
        if conn in self.connections:
            self.connections.remove(conn)
        self.is_modified = True
        self.update_save_button_state()

    def on_connector_press(self, event):
        pass

    def on_resize_start(self, event):
        item = self.canvas.find_withtag('current')[0]
        tags = self.canvas.gettags(item)
        node_id = tags[tags.index('node') + 1]
        self.resizing_node_id = node_id
        node = self.nodes[node_id]
        self.resize_start_data = {
            'screen_x': event.x, 
            'screen_y': event.y, 
            'width': node['width'], 
            'height': node['height']
        }

    def on_resize_move(self, event):
        if not self.resizing_node_id or not self.resize_start_data:
            return

        node = self.nodes[self.resizing_node_id]
        
        # Calculate delta in screen space, convert to world space
        screen_dx = event.x - self.resize_start_data['screen_x']
        screen_dy = event.y - self.resize_start_data['screen_y']
        world_dx = screen_dx / self.zoom_level
        world_dy = screen_dy / self.zoom_level
        
        # Calculate new dimensions in world space
        new_width = max(self.resize_start_data['width'] + world_dx, self.min_node_width)
        new_height = max(self.resize_start_data['height'] + world_dy, self.min_node_height)

        node['width'] = new_width
        node['height'] = new_height

        for item_id in node['canvas_items'].values():
            self.canvas.delete(item_id)
        self.draw_node(node)
        self.redraw_connections()
        self.is_modified = True
        self.update_save_button_state()

    def on_resize_end(self, event):
        if self.resizing_node_id and self.snap_to_grid:
            node = self.nodes[self.resizing_node_id]
            node['width'] = max(self.min_node_width, round(node['width'] / self.grid_size) * self.grid_size)
            node['height'] = max(self.min_node_height, round(node['height'] / self.grid_size) * self.grid_size)
            for item_id in node['canvas_items'].values():
                self.canvas.delete(item_id)
            self.draw_node(node)
            self.redraw_connections()
        self.resizing_node_id = None
        self.resize_start_data = None

    def clear_all_highlights(self):
        for node_id, node_data in self.nodes.items():
            body = node_data['canvas_items'].get('body')
            header = node_data['canvas_items'].get('header')
            if body:
                self.canvas.itemconfig(body, outline=Theme.NODE_BORDER, width=2)
            if header:
                self.canvas.itemconfig(header, outline=Theme.NODE_BORDER, width=2)
            node_data['highlight_state'] = False

    def highlight_node(self, node_id, is_workflow=True):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        body = node['canvas_items'].get('body')
        header = node['canvas_items'].get('header')
        if body:
            self.canvas.itemconfig(body, outline=Theme.NODE_BORDER_SELECTED, width=3)
        if header:
            self.canvas.itemconfig(header, outline=Theme.NODE_BORDER_SELECTED, width=3)
        if is_workflow:
            node['highlight_state'] = True
            # Also highlight incoming connections with marching ants
            self.highlight_incoming_connections(node_id)

    def remove_highlight(self, node_id):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        body = node['canvas_items'].get('body')
        header = node['canvas_items'].get('header')
        if body:
            self.canvas.itemconfig(body, outline=Theme.NODE_BORDER, width=2)
        if header:
            self.canvas.itemconfig(header, outline=Theme.NODE_BORDER, width=2)
        node['highlight_state'] = False
        # Also remove connection flow highlights
        self.remove_incoming_connection_highlights(node_id)

    def on_node_enter(self, node_id):
        if node_id in self.nodes and not self.nodes[node_id].get('highlight_state', False):
            node = self.nodes[node_id]
            body = node['canvas_items'].get('body')
            header = node['canvas_items'].get('header')
            if body:
                self.canvas.itemconfig(body, outline=Theme.NODE_BORDER_HOVER, width=2)
            if header:
                self.canvas.itemconfig(header, outline=Theme.NODE_BORDER_HOVER, width=2)

    def on_node_leave(self, node_id):
        if node_id in self.nodes and not self.nodes[node_id].get('highlight_state', False):
            node = self.nodes[node_id]
            body = node['canvas_items'].get('body')
            header = node['canvas_items'].get('header')
            if body:
                self.canvas.itemconfig(body, outline=Theme.NODE_BORDER, width=2)
            if header:
                self.canvas.itemconfig(header, outline=Theme.NODE_BORDER, width=2)

    def edit_node_properties(self, node):
        def save_properties():
            for prop_name, widget in prop_widgets.items():
                prop_details = node['properties'].get(prop_name, fresh_properties.get(prop_name, {}))
                prop_type = prop_details.get('type', 'text')

                if prop_type == 'text':
                    value = widget.get()
                elif prop_type == 'dropdown':
                    value = widget.get()
                elif prop_type == 'textarea':
                    value = widget.get("1.0", tk.END).strip()
                elif prop_type == 'boolean':
                    value = var_states.get(prop_name, tk.BooleanVar(value=False)).get()
                elif prop_type == 'folder':
                    value = widget.get()
                else:
                    value = widget.get()

                if prop_name not in node['properties']:
                    node['properties'][prop_name] = {}
                node['properties'][prop_name]['default'] = value

            if 'node_name' in node['properties']:
                new_node_name = node['properties']['node_name']['default']
                node['title'] = new_node_name

            prop_window.destroy()
            self.redraw_canvas()
            self.is_modified = True
            self.update_save_button_state()

        prop_window = tk.Toplevel(self.editor_window)
        prop_window.title(f"Edit: {node['title']}")
        prop_window.geometry("450x650")
        prop_window.configure(bg=Theme.CANVAS_BG)
        prop_window.minsize(400, 450)

        node_class = self.get_node_class_by_type(node['type'])
        node_instance = node_class(node_id=node['id'], config=self.config)
        fresh_properties = node_instance.define_properties()

        for prop_name, prop_details in fresh_properties.items():
            if prop_name in node['properties']:
                existing_default = node['properties'][prop_name].get('default', prop_details.get('default'))
                node['properties'][prop_name] = {**prop_details, 'default': existing_default}
            else:
                node['properties'][prop_name] = prop_details

        # Header with node type info
        header_frame = tk.Frame(prop_window, bg=Theme.NODE_HEADER, height=50)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text=f"Node: {node['title']}", bg=Theme.NODE_HEADER, 
                 fg=Theme.TEXT_PRIMARY, font=('Segoe UI', 11, 'bold')).pack(side=tk.LEFT, padx=15, pady=12)
        tk.Label(header_frame, text=f"Type: {node['type']}", bg=Theme.NODE_HEADER, 
                 fg=Theme.TEXT_SECONDARY, font=('Segoe UI', 9)).pack(side=tk.RIGHT, padx=15, pady=12)

        # Content area with scrolling
        content_frame = tk.Frame(prop_window, bg=Theme.CANVAS_BG)
        content_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(content_frame, bg=Theme.CANVAS_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=Theme.CANVAS_BG)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        prop_window.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width-4))
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        prop_widgets = {}
        var_states = {}

        for prop_name, prop_details in fresh_properties.items():
            current_value = node['properties'].get(prop_name, {}).get('default', prop_details.get('default', ''))
            label_text = prop_details.get('label', prop_name)
            
            # Property container with subtle background
            prop_container = tk.Frame(scrollable_frame, bg=Theme.CANVAS_BG)
            prop_container.pack(fill='x', padx=10, pady=5)
            
            # Label with better styling
            tk.Label(prop_container, text=label_text, bg=Theme.CANVAS_BG, fg=Theme.TEXT_PRIMARY,
                     font=('Segoe UI', 9, 'bold')).pack(pady=(8, 4), anchor='w', padx=5)

            if prop_details['type'] == 'text':
                # Wrapper frame for border effect
                entry_frame = tk.Frame(prop_container, bg=Theme.NODE_BORDER, padx=1, pady=1)
                entry_frame.pack(fill='x', padx=5, pady=2)
                widget = tk.Entry(entry_frame, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                                  insertbackground=Theme.TEXT_PRIMARY, relief='flat', 
                                  font=('Segoe UI', 10), bd=0)
                widget.insert(0, str(current_value))
                widget.pack(fill='x', ipady=8, ipadx=5)
            elif prop_details['type'] == 'dropdown':
                widget = ttk.Combobox(prop_container, state="readonly", font=('Segoe UI', 10))
                options = prop_details['options']() if callable(prop_details['options']) else prop_details['options']
                widget['values'] = options
                if current_value in options:
                    widget.set(current_value)
                elif options:
                    widget.set(options[0])
                widget.pack(fill='x', padx=5, pady=2)
            elif prop_details['type'] == 'textarea':
                # Wrapper frame for border effect
                text_frame = tk.Frame(prop_container, bg=Theme.NODE_BORDER, padx=1, pady=1)
                text_frame.pack(fill='x', padx=5, pady=2)
                widget = tk.Text(text_frame, height=6, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                                 insertbackground=Theme.TEXT_PRIMARY, relief='flat', 
                                 font=('Segoe UI', 10), bd=0, wrap=tk.WORD)
                widget.insert("1.0", str(current_value))
                widget.pack(fill='x', padx=3, pady=3)
            elif prop_details['type'] == 'boolean':
                var_states[prop_name] = tk.BooleanVar(value=current_value)
                bool_frame = tk.Frame(prop_container, bg=Theme.CANVAS_BG)
                bool_frame.pack(fill='x', padx=5, pady=2)
                widget = tk.Checkbutton(bool_frame, variable=var_states[prop_name], text="Enabled",
                                        bg=Theme.CANVAS_BG, fg=Theme.TEXT_PRIMARY, selectcolor=Theme.NODE_BG,
                                        activebackground=Theme.CANVAS_BG, activeforeground=Theme.TEXT_PRIMARY,
                                        font=('Segoe UI', 9))
                widget.pack(anchor='w')
            elif prop_details['type'] == 'folder':
                # Folder browser with text entry and browse button
                folder_frame = tk.Frame(prop_container, bg=Theme.CANVAS_BG)
                folder_frame.pack(fill='x', padx=5, pady=2)
                
                entry_frame = tk.Frame(folder_frame, bg=Theme.NODE_BORDER, padx=1, pady=1)
                entry_frame.pack(side='left', fill='x', expand=True)
                widget = tk.Entry(entry_frame, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                                  insertbackground=Theme.TEXT_PRIMARY, relief='flat', 
                                  font=('Segoe UI', 10), bd=0)
                widget.insert(0, str(current_value))
                widget.pack(fill='x', ipady=8, ipadx=5)
                
                def browse_folder(entry_widget=widget):
                    from tkinter import filedialog
                    folder = filedialog.askdirectory(title="Select Output Folder")
                    if folder:
                        entry_widget.delete(0, tk.END)
                        entry_widget.insert(0, folder)
                
                browse_btn = tk.Button(folder_frame, text="Browse...", bg=Theme.BUTTON_BG, fg=Theme.TEXT_PRIMARY,
                                       activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY,
                                       relief='flat', padx=10, pady=4, font=('Segoe UI', 9),
                                       command=browse_folder)
                browse_btn.pack(side='right', padx=(5, 0))
            else:
                entry_frame = tk.Frame(prop_container, bg=Theme.NODE_BORDER, padx=1, pady=1)
                entry_frame.pack(fill='x', padx=5, pady=2)
                widget = tk.Entry(entry_frame, bg=Theme.NODE_BG, fg=Theme.TEXT_PRIMARY,
                                  insertbackground=Theme.TEXT_PRIMARY, relief='flat', 
                                  font=('Segoe UI', 10), bd=0)
                widget.insert(0, str(current_value))
                widget.pack(fill='x', ipady=8, ipadx=5)

            prop_widgets[prop_name] = widget
            
            # Add separator line
            tk.Frame(scrollable_frame, bg=Theme.GRID_COLOR, height=1).pack(fill='x', padx=15, pady=5)

        # Bottom button bar (fixed at bottom)
        btn_bar = tk.Frame(prop_window, bg=Theme.TOOLBAR_BG, height=60)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_bar.pack_propagate(False)
        
        save_btn = tk.Button(btn_bar, text="Save Changes", bg='#3d6a3d', fg=Theme.TEXT_PRIMARY,
                             activebackground='#4d7a4d', activeforeground=Theme.TEXT_PRIMARY,
                             relief='flat', padx=25, pady=8, font=('Segoe UI', 10),
                             command=save_properties)
        save_btn.pack(side='right', padx=15, pady=12)
        
        cancel_btn = tk.Button(btn_bar, text="Cancel", bg=Theme.BUTTON_BG, fg=Theme.TEXT_PRIMARY,
                               activebackground=Theme.BUTTON_HOVER, activeforeground=Theme.TEXT_PRIMARY,
                               relief='flat', padx=20, pady=8, font=('Segoe UI', 10),
                               command=prop_window.destroy)
        cancel_btn.pack(side='right', padx=5, pady=12)

    def save_node_graph(self):
        # Save viewport state (window size, zoom, pan position)
        viewport_data = {
            'window_width': self.editor_window.winfo_width(),
            'window_height': self.editor_window.winfo_height(),
            'zoom_level': self.zoom_level,
            'pan_offset_x': self.pan_offset_x,
            'pan_offset_y': self.pan_offset_y
        }
        
        graph_data = {
            'nodes': self.nodes, 
            'connections': self.connections,
            'viewport': viewport_data
        }

        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Input Required", "Please enter a name for the instruction set.")
            return
        self.instruction_name = name

        self.configured_graph = graph_data
        self.configured_name = self.instruction_name

        if self.save_callback:
            self.save_callback(self)

        self.is_modified = False
        self.update_save_button_state()
        self.on_close()


# Alias for backward compatibility
NodeEditor = ModernNodeEditor
