"""
Token Logger Service for XeroFlow.
Provides centralized token usage logging functionality for all nodes.
"""
import csv
import uuid
from datetime import datetime
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TokenLogger:
    """
    A service for logging token usage across all API calls.
    This ensures consistent logging regardless of which node type makes the API call.
    """
    
    @staticmethod
    def setup_log_directory():
        """
        Set up the logs directory structure.
        
        Returns:
            Path: The path to the logs directory
        """
        try:
            # Create main logs directory
            logs_dir = Path("nodes") / "Logs"
            logs_dir.mkdir(exist_ok=True)
            
            return logs_dir
        except Exception as e:
            logger.error(f"Error setting up log directory: {str(e)}")
            return None
    
    @staticmethod
    def setup_token_log(node_name):
        """
        Set up the token usage log file for a specific node.
        
        Args:
            node_name: Name of the node
            
        Returns:
            Path: The path to the log file
        """
        try:
            logs_dir = TokenLogger.setup_log_directory()
            if not logs_dir:
                return None
            
            # Create node-specific subdirectory
            node_logs_dir = logs_dir / node_name
            node_logs_dir.mkdir(exist_ok=True)
            
            # Define the CSV file path
            log_file = node_logs_dir / "token_usage.csv"
            
            # If the file doesn't exist, create it with headers
            if not log_file.exists():
                with open(log_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['ID', 'Date', 'Time', 'API_Endpoint', 'Model', 'SubmitTokens', 'ReplyTokens', 'TotalTokens', 'AudioDuration(s)'])
                logger.info(f"Created new token usage log file: {log_file}")
            
            return log_file
        except Exception as e:
            logger.error(f"Error setting up token log: {str(e)}")
            return None
    
    @staticmethod
    def log_token_usage(node_name, api_endpoint, model, token_usage):
        """
        Logs token usage information to a CSV file.
        
        Args:
            node_name: Name of the node making the API call
            api_endpoint: The API endpoint used
            model: The model used
            token_usage: Dictionary containing token usage information
        """
        try:
            log_file = TokenLogger.setup_token_log(node_name)
            if not log_file:
                return
            
            # Extract token information
            prompt_tokens = token_usage.get('prompt_tokens', 0)
            completion_tokens = token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            audio_duration = token_usage.get('audio_duration', 0)
            
            # Get current time
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            
            # Generate a unique ID
            unique_id = str(uuid.uuid4())[:8]
            
            # Log the information
            with open(log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    unique_id, 
                    date_str, 
                    time_str, 
                    api_endpoint, 
                    model, 
                    prompt_tokens, 
                    completion_tokens, 
                    total_tokens,
                    audio_duration
                ])
            
            # Log message
            log_message = f"Token usage logged for {node_name}: {prompt_tokens} input, {completion_tokens} output, {total_tokens} total"
            if audio_duration > 0:
                minutes = audio_duration / 60
                log_message += f", {audio_duration:.1f}s ({minutes:.2f}min) audio"
            
            logger.info(log_message)
            return True
            
        except Exception as e:
            logger.error(f"Error logging token usage: {str(e)}")
            return False
