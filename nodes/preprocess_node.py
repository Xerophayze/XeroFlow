"""
PreProcess Node for XeroFlow.
This node uses the PreProcess module to preprocess text before sending to an API.
"""
from .base_node import BaseNode
from src.workflows.node_registry import register_node
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@register_node('PreProcessNode')
class PreProcessNode(BaseNode):
    """
    Node for preprocessing text using the PreProcess module.
    This node takes input text, preprocesses it with a configured prompt,
    sends it to a specified API endpoint, and returns the response.
    """
    
    def define_inputs(self):
        """Define the input connectors for the node."""
        return ['input']  # Single input named 'input'

    def define_outputs(self):
        """Define the output connectors for the node."""
        return ['output']  # Single output named 'output'

    def define_properties(self):
        """Define the properties for the node."""
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'PreProcess Node'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Preprocesses text using the PreProcess module.'
            },
            'module_name': {
                'type': 'dropdown',
                'label': 'Module Configuration',
                'options': self._get_available_modules(),
                'default': self._get_available_modules()[0] if self._get_available_modules() else ''
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
            },
            'is_persistent': {
                'type': 'boolean',
                'label': 'Persistent Node',
                'default': True,
                'description': 'If true, the node will remain active and accept more inputs.'
            }
        })
        return props
    
    def _get_available_modules(self):
        """Get available module configurations."""
        try:
            # Import the PreProcess module
            from modules.preprocess import PreProcess
            
            # Create an instance of the PreProcess module
            preprocess = PreProcess(self.config)
            
            # Get available modules
            modules = preprocess.get_available_modules()
            
            return modules
        except Exception as e:
            logger.error(f"Error getting available modules: {str(e)}")
            return ["PreProcess"]  # Default if module not available
    
    def update_node_name(self, new_name):
        """Update the name of the node dynamically."""
        self.properties['node_name']['default'] = new_name
        logger.info(f"[PreProcessNode] Node name updated to: {new_name}")

    def process(self, inputs):
        """
        Process the input by sending it to the PreProcess module.
        
        Args:
            inputs (dict): Dictionary of input values
            
        Returns:
            dict: Dictionary of output values
        """
        # Retrieve the incoming input
        incoming_input = inputs.get('input', '').strip()
        logger.info(f"[PreProcessNode] Incoming input: '{incoming_input[:50]}...' (truncated)")
        
        if not incoming_input:
            logger.warning("[PreProcessNode] No input provided")
            return {'output': "No input provided."}
        
        try:
            # Get the selected module name
            module_name = self.properties.get('module_name', {}).get('default', 'PreProcess')
            
            # Import the PreProcess module
            from modules.preprocess import PreProcess
            
            # Create an instance of the PreProcess module
            preprocess = PreProcess(self.config)
            
            # Process the input text
            result = preprocess.process_text(incoming_input, module_name)
            
            if not result.get('success', False):
                error_message = result.get('error', 'Unknown error occurred')
                logger.error(f"[PreProcessNode] Error: {error_message}")
                return {'output': f"Error: {error_message}"}
            
            # Return the processed output
            processed_output = result.get('content', '')
            logger.info(f"[PreProcessNode] Processed output: '{processed_output[:50]}...' (truncated)")
            
            return {'output': processed_output}
        except Exception as e:
            logger.error(f"[PreProcessNode] Error processing input: {str(e)}")
            return {'output': f"Error processing input: {str(e)}"}
    
    def requires_api_call(self):
        """Indicates whether this node requires an API call."""
        return True  # This node makes an API call via the PreProcess module
