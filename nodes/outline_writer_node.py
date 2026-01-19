from .base_node import BaseNode
from src.workflows.node_registry import register_node
from src.api.handler import process_api_request
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, 
                           QPushButton, QCheckBox, QApplication,
                           QMenu, QSizePolicy, QFileDialog, QMessageBox)
from PyQt5.QtCore import QThread, QObject, pyqtSignal, Qt, QTimer
import sys
import threading
import queue
import os
from datetime import datetime

class WorkflowTerminationRequested(Exception):
    """Exception raised to request workflow termination"""
    pass

class ReviewSignals(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    update_text = pyqtSignal(str)
    closed = pyqtSignal()  # New signal for close button

class ApiWorker(QThread):
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, callback_func, prompt, current_result):
        super().__init__()
        self.callback_func = callback_func
        self.prompt = prompt
        self.current_result = current_result

    def run(self):
        try:
            result = self.callback_func(self.prompt, self.current_result)
            self.result_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))

class ReviewWindow(QWidget):
    def __init__(self, initial_text, process_api_func):
        super().__init__()
        self.process_api_func = process_api_func
        self.signals = ReviewSignals()
        self.result_queue = queue.Queue()
        
        # Initialize UI without changing global DPI settings
        self.init_ui(initial_text)
        
        # Set window flags to be independent
        self.setWindowFlags(Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)

    def init_ui(self, initial_text):
        layout = QVBoxLayout()
        
        # Result text area with context menu
        self.result_text = QTextEdit()
        self.result_text.setPlainText(initial_text)
        self.result_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.result_text.customContextMenuRequested.connect(self.show_context_menu)
        self.result_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.result_text)
        
        # New prompt input with context menu
        self.new_prompt = QTextEdit()
        self.new_prompt.setPlaceholderText("Enter new prompt here...")
        self.new_prompt.setMaximumHeight(100)
        self.new_prompt.setContextMenuPolicy(Qt.CustomContextMenu)
        self.new_prompt.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.new_prompt)
        
        # Button layout for better organization
        button_layout = QVBoxLayout()
        
        # Submit button for new prompt
        self.submit_btn = QPushButton('Submit')
        self.submit_btn.clicked.connect(self.on_submit)
        button_layout.addWidget(self.submit_btn)
        
        # Save button
        self.save_btn = QPushButton('Save')
        self.save_btn.clicked.connect(self.on_save)
        button_layout.addWidget(self.save_btn)
        
        # Approve button
        self.approve_btn = QPushButton('Approve')
        self.approve_btn.clicked.connect(self.on_approve)
        button_layout.addWidget(self.approve_btn)

        # Close button
        self.close_btn = QPushButton('Close')
        self.close_btn.clicked.connect(self.on_close)
        self.close_btn.setStyleSheet("background-color: #ff6b6b;")  # Red background to indicate termination
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.setWindowTitle('Review Results')
        self.setGeometry(300, 300, 800, 600)

    def show_context_menu(self, position):
        sender = self.sender()
        menu = QMenu()
        
        copy_action = menu.addAction("Copy")
        paste_action = menu.addAction("Paste")
        select_all_action = menu.addAction("Select All")
        
        action = menu.exec_(sender.mapToGlobal(position))
        
        if action == copy_action:
            sender.copy()
        elif action == paste_action:
            sender.paste()
        elif action == select_all_action:
            sender.selectAll()

    def on_submit(self):
        try:
            self.submit_btn.setEnabled(False)
            new_prompt = self.new_prompt.toPlainText()
            current_result = self.result_text.toPlainText()
            
            # Create worker thread for API processing
            self.worker = ApiWorker(self.process_api_func, new_prompt, current_result)
            self.worker.result_ready.connect(self.handle_api_result)
            self.worker.error_occurred.connect(self.handle_api_error)
            self.worker.finished.connect(lambda: self.submit_btn.setEnabled(True))
            self.worker.start()
            
        except Exception as e:
            self.signals.error.emit(str(e))
            self.submit_btn.setEnabled(True)

    def handle_api_result(self, result):
        self.result_text.setPlainText(result)

    def handle_api_error(self, error_msg):
        print(f"API Error: {error_msg}")
        self.signals.error.emit(error_msg)

    def on_approve(self):
        try:
            final_text = self.result_text.toPlainText()
            self.result_queue.put(("approve", final_text))
            self.close()
        except Exception as e:
            self.signals.error.emit(str(e))

    def on_save(self):
        try:
            # Get current text
            content = self.result_text.toPlainText()
            if not content.strip():
                return
            
            # Generate default filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"outline_{timestamp}.txt"
            
            # Open file dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Outline",
                os.path.join(os.path.expanduser("~"), "Documents", default_filename),
                "Text Files (*.txt);;All Files (*.*)"
            )
            
            if file_path:
                # Add .txt extension if not present
                if not os.path.splitext(file_path)[1]:
                    file_path += '.txt'
                
                # Save the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
        except Exception as e:
            self.signals.error.emit(f"Error saving file: {str(e)}")

    def on_close(self):
        """Handle close button click"""
        self.result_queue.put(("terminate", None))
        self.signals.closed.emit()
        self.close()

    def closeEvent(self, event):
        """Override closeEvent to handle window X button"""
        if not self.result_queue.empty():
            # Already handled by approve or close button
            event.accept()
            return
        self.result_queue.put(("terminate", None))
        self.signals.closed.emit()
        event.accept()

class WorkflowTerminationException(Exception):
    """Exception raised when workflow should be terminated"""
    pass

@register_node('OutlineWriterNode')
class OutlineWriterNode(BaseNode):
    def define_inputs(self):
        return ['input']

    def define_outputs(self):
        return ['output']

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'OutlineWriterNode'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Processes the input prompt with review capability.'
            },
            'Prompt': {
                'type': 'textarea',
                'label': 'Prompt',
                'default': 'Processing your request...'
            },
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            },
            'enable_review': {
                'type': 'boolean',
                'label': 'Enable Review',
                'default': True
            },
            'is_start_node': {
                'type': 'boolean',
                'label': 'Start Node',
                'default': False
            },
            'is_end_node': {
                'type': 'boolean',
                'label': 'End Node',
                'default': False
            }
        })
        return props

    def update_node_name(self, new_name):
        self.properties['node_name']['default'] = new_name
        print(f"[OutlineWriterNode] Node name updated to: {new_name}")

    def get_api_endpoints(self):
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[OutlineWriterNode] Available API endpoints: {api_list}")
        return api_list

    def process_with_api(self, prompt):
        try:
            selected_api = self.properties.get('api_endpoint', {}).get('default', '')
            if not selected_api:
                return "No API endpoint selected."
            
            api_details = self.config['interfaces'].get(selected_api, {})
            if not api_details:
                return "API details not found for the selected endpoint."
            
            # Use process_api_request instead of send_to_api
            api_response_content = process_api_request(api_details, prompt)
            
            # Extract the actual response based on API type
            api_type = api_details.get('api_type')
            if api_type == "OpenAI":
                response = api_response_content.get('choices', [{}])[0].get('message', {}).get('content', 'No response available')
            elif api_type == "Ollama":
                if isinstance(api_response_content, dict):
                    message = api_response_content.get('message', {})
                    response = message.get('content', 'No response available')
                elif isinstance(api_response_content, str):
                    response = api_response_content
                else:
                    response = 'No response available'
            else:
                response = 'Unsupported API type.'
                print(f"[OutlineWriterNode] Unsupported API type: {api_type}")
            
            return response
            
        except Exception as e:
            print(f"Error in process_with_api: {str(e)}")
            raise

    def process(self, inputs):
        try:
            incoming_input = inputs.get('input', '').strip()
            prompt = self.properties.get('Prompt', {}).get('default', '').strip()
            combined_input = f"{prompt} {incoming_input}".strip()
            
            # Get initial API response
            api_response = self.process_with_api(combined_input)
            
            # Check if review is enabled
            enable_review = self.properties.get('enable_review', {}).get('default', True)
            
            if not enable_review:
                return {'output': api_response}

            # Create event for synchronization
            self.review_completed = False
            self.review_result = None
            self.review_error = None
            self.workflow_terminated = False

            def process_api_callback(new_prompt, current_result):
                combined_input = f"Previous result: {current_result}\n\nNew request: {new_prompt}"
                return self.process_with_api(combined_input)

            # Create QApplication in the main thread
            app = QApplication.instance()
            if not app:
                app = QApplication(sys.argv)

            # Create review window
            self.review_window = ReviewWindow(api_response, process_api_callback)
            
            # Connect the closed signal
            self.review_window.signals.closed.connect(self.handle_window_close)
            
            self.review_window.show()

            # Process events until window is closed
            while not self.review_completed:
                app.processEvents()
                try:
                    action, result = self.review_window.result_queue.get_nowait()
                    if action == "approve":
                        self.review_result = result
                    elif action == "terminate":
                        self.workflow_terminated = True
                    self.review_completed = True
                except queue.Empty:
                    QThread.msleep(100)  # Sleep to prevent high CPU usage
                    continue

            if self.workflow_terminated:
                return None  # Return None to indicate workflow should stop

            return {'output': self.review_result} if self.review_result is not None else None

        except WorkflowTerminationRequested as e:
            print(f"Workflow termination requested: {str(e)}")
            return None  # Return None to indicate workflow should stop
        except Exception as e:
            print(f"Error in process: {str(e)}")
            raise

    def handle_window_close(self):
        """Handle window close event"""
        self.review_completed = True
