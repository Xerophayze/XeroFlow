"""
PreProcess module for XeroFlow.
This module preprocesses user requests by appending them to a preconfigured prompt
and submitting to a specified API endpoint.
"""
from typing import Dict, Any, Optional
import json
import os
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PreProcess:
    """
    PreProcess module for handling text preprocessing before API submission.
    This module can be called by other modules to preprocess text with a configured prompt
    and send it to a specified API endpoint.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the PreProcess module with configuration.
        
        Args:
            config: Dictionary containing configuration settings
        """
        self.config = config
        self.module_config = self._load_module_config()
        
    def _load_module_config(self) -> Dict[str, Any]:
        """
        Load module-specific configuration from the config directory.
        
        Returns:
            Dict containing module configuration
        """
        config_dir = Path("config")
        config_file = config_dir / "module_settings.json"
        
        # Create config directory if it doesn't exist
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create default module settings file if it doesn't exist
        if not config_file.exists():
            default_config = {
                "modules": {
                    "PreProcess": {
                        "prompt": "Process the following text: ",
                        "api_endpoint": ""
                    }
                }
            }
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
            
            return default_config.get("modules", {}).get("PreProcess", {})
        
        # Load existing module settings
        try:
            with open(config_file, 'r') as f:
                module_settings = json.load(f)
                return module_settings.get("modules", {}).get("PreProcess", {})
        except Exception as e:
            logger.error(f"Error loading module settings: {str(e)}")
            return {}
    
    def save_module_config(self, module_name: str, settings: Dict[str, Any]) -> bool:
        """
        Save module-specific configuration to the config directory.
        
        Args:
            module_name: Name of the module
            settings: Dictionary containing module settings
            
        Returns:
            bool: True if successful, False otherwise
        """
        config_dir = Path("config")
        config_file = config_dir / "module_settings.json"
        
        # Create config directory if it doesn't exist
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing settings or create new
        try:
            if config_file.exists():
                with open(config_file, 'r') as f:
                    module_settings = json.load(f)
            else:
                module_settings = {"modules": {}}
            
            # Update the specific module settings
            if "modules" not in module_settings:
                module_settings["modules"] = {}
                
            module_settings["modules"][module_name] = settings
            
            # Save updated settings
            with open(config_file, 'w') as f:
                json.dump(module_settings, f, indent=4)
                
            # Update current module config if this is for the PreProcess module
            if module_name == "PreProcess":
                self.module_config = settings
                
            return True
        except Exception as e:
            logger.error(f"Error saving module settings: {str(e)}")
            return False
    
    def get_available_modules(self) -> list:
        """
        Get a list of available modules from the config.
        
        Returns:
            list: List of module names
        """
        config_dir = Path("config")
        config_file = config_dir / "module_settings.json"
        
        if not config_file.exists():
            return ["PreProcess"]  # Return default if file doesn't exist
        
        try:
            with open(config_file, 'r') as f:
                module_settings = json.load(f)
                return list(module_settings.get("modules", {}).keys())
        except Exception as e:
            logger.error(f"Error loading module settings: {str(e)}")
            return ["PreProcess"]  # Return default on error
    
    def get_module_settings(self, module_name: str) -> Dict[str, Any]:
        """
        Get settings for a specific module.
        
        Args:
            module_name: Name of the module
            
        Returns:
            Dict: Module settings
        """
        config_dir = Path("config")
        config_file = config_dir / "module_settings.json"
        
        if not config_file.exists():
            return {}  # Return empty dict if file doesn't exist
        
        try:
            with open(config_file, 'r') as f:
                module_settings = json.load(f)
                return module_settings.get("modules", {}).get(module_name, {})
        except Exception as e:
            logger.error(f"Error loading module settings: {str(e)}")
            return {}  # Return empty dict on error
    
    def process_text(self, text: str, module_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Process the input text by appending it to the configured prompt
        and submitting to the specified API endpoint.
        
        Args:
            text: Input text to process
            module_name: Optional module name to use specific settings
            
        Returns:
            Dict containing the processed response
        """
        # Get module settings
        if module_name and module_name != "PreProcess":
            module_settings = self.get_module_settings(module_name)
        else:
            module_settings = self.module_config
        
        # Get prompt and API endpoint from settings
        prompt = module_settings.get("prompt", "")
        api_endpoint = module_settings.get("api_endpoint", "")
        
        if not api_endpoint:
            return {
                "success": False,
                "error": "No API endpoint configured",
                "content": ""
            }
        
        # Combine prompt with input text
        combined_text = f"{prompt}\n\n{text}"
        
        # Get API service from the config
        from services.api_service import APIService, APIRequest
        api_service = APIService(self.config)
        
        # Check if API endpoint exists
        if api_endpoint not in api_service.get_available_endpoints():
            return {
                "success": False,
                "error": f"API endpoint '{api_endpoint}' not found",
                "content": ""
            }
        
        # Create API request
        request = APIRequest(
            content=combined_text,
            api_name=api_endpoint
        )
        
        # Send request to API
        try:
            response = api_service.send_request(request)
            
            # Return response
            return {
                "success": response.success,
                "error": response.error,
                "content": response.content,
                "tokens": {
                    "prompt": response.prompt_tokens,
                    "completion": response.completion_tokens,
                    "total": response.total_tokens
                }
            }
        except Exception as e:
            logger.error(f"Error processing text: {str(e)}")
            return {
                "success": False,
                "error": f"Error processing text: {str(e)}",
                "content": ""
            }
