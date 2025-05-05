"""
API Service module for XeroFlow.
Handles all API-related operations in a unified way.
"""
from typing import Optional, Dict, Any, List
import logging
import re
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class APIRequest:
    def __init__(self, content: str, api_name: str, model: Optional[str] = None, max_tokens: Optional[int] = None, temperature: Optional[float] = None, additional_params: Optional[Dict[str, Any]] = None):
        self.content = content
        self.api_name = api_name
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.additional_params = additional_params or {}

class APIResponse:
    def __init__(self, content: str = "", raw_response: Any = None, success: bool = False, error: str = "", 
                 prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
        self.content = content
        self.raw_response = raw_response
        self.success = success
        self.error = error
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens

class APIService:
    """
    Unified API service for handling all API interactions.
    This service abstracts away the complexity of different API providers
    and provides a consistent interface for all nodes.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the API service with configuration.
        
        Args:
            config: Dictionary containing API configurations
        """
        self.config = config
        self._clients = {}
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize API clients for each configured interface"""
        interfaces = self.config.get('interfaces', {})
        for api_name, api_config in interfaces.items():
            try:
                self._init_client(api_name, api_config)
            except Exception as e:
                logger.error(f"Failed to initialize client for {api_name}: {str(e)}")

    def _init_client(self, api_name: str, api_config: Dict[str, Any]):
        """Initialize a specific API client"""
        api_type = api_config.get('type', '').lower()
        api_key = api_config.get('api_key')
        api_url = api_config.get('api_url', '').rstrip('/')

        if not api_type:
            logger.error(f"Missing API type for {api_name}")
            return

        try:
            if api_type == "searchengine":
                # SearchEngine doesn't need API key or client
                self._clients[api_name] = {
                    "type": api_type,
                    "api_url": api_url
                }
                logger.info(f"Initialized SearchEngine client with URL: {api_url}")
                return

            # For other API types, check for API key
            if not api_type == "ollama" and not api_key:
                logger.error(f"Missing API key for {api_name}")
                return

            if api_type == "openai":
                from openai import OpenAI
                # OpenAI's base URL should always end with /v1
                if api_url:
                    api_url = api_url.rstrip('/') + '/v1'
                client = OpenAI(api_key=api_key, base_url=api_url) if api_url else OpenAI(api_key=api_key)
                self._clients[api_name] = {"client": client, "type": api_type}
                logger.info(f"Initialized OpenAI client with URL: {api_url if api_url else 'default'}")

            elif api_type == "ollama":
                from ollama import Client
                client = Client(host=api_url)
                self._clients[api_name] = {"client": client, "type": api_type}
                logger.info(f"Initialized Ollama client with host: {api_url}")

            elif api_type == "groq":
                from groq import Groq
                client = Groq(api_key=api_key)
                self._clients[api_name] = {"client": client, "type": api_type}
                logger.info("Initialized Groq client")

            else:
                logger.warning(f"Unsupported API type: {api_type}")

        except Exception as e:
            logger.error(f"Error initializing {api_type} client: {str(e)}")

    def get_available_endpoints(self) -> List[str]:
        """Get list of available API endpoints"""
        return list(self.config.get('interfaces', {}).keys())

    def get_endpoint_details(self, api_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration details for a specific API endpoint"""
        return self.config.get('interfaces', {}).get(api_name)

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if a URL is valid and not a PDF."""
        if not url:
            return False
            
        # Check if it's a PDF
        if url.lower().endswith('.pdf'):
            return False
            
        # Validate URL format
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def clean_url(url: str) -> str:
        """Clean a URL by removing any trailing characters that shouldn't be there."""
        if not url:
            return ""
            
        # First clean any JSON formatting and quotes
        url = url.strip()
        url = re.sub(r'[\'"]\s*[,\]\}\)]*$', '', url)  # Remove quotes followed by JSON chars
        url = re.sub(r'[,\]\}\)]+$', '', url)          # Remove any remaining JSON chars
        url = url.strip('\'"')                         # Remove any remaining quotes
        
        # Handle URL fragments and query parameters
        url = url.split('#')[0]  # Remove fragment identifier
        
        # Final cleanup
        url = url.rstrip('.,;:')  # Remove any trailing punctuation
        url = url.strip()
        
        # Return empty string if it's not a valid URL
        return url if APIService.is_valid_url(url) else ""

    def send_request(self, request: APIRequest) -> APIResponse:
        """
        Send a request to the specified API endpoint.
        
        Args:
            request: APIRequest object containing request details
            
        Returns:
            APIResponse object containing the response
        """
        if request.api_name not in self._clients:
            return APIResponse(
                content="API endpoint not initialized",
                raw_response=None,
                success=False,
                error=f"API endpoint {request.api_name} not initialized"
            )

        client_info = self._clients[request.api_name]
        client = client_info.get("client")
        api_type = client_info["type"]

        try:
            logger.info(f"Sending request to {api_type} API")
            logger.debug(f"Request details: {request}")

            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            if api_type == "openai":
                # For OpenAI, build parameters based on what's supported
                params = {
                    "model": request.model,
                    "messages": [{"role": "user", "content": request.content}]
                }
                
                # Only add optional parameters if they're provided and supported
                if request.max_tokens:
                    params["max_completion_tokens"] = request.max_tokens
                    
                # Some models like o3-mini don't support temperature
                if request.temperature and not request.model.startswith('o3-'):
                    params["temperature"] = request.temperature
                
                response = client.chat.completions.create(**params)
                content = response.choices[0].message.content
                
                # Ensure markdown formatting is preserved for all models
                # No need to strip or modify the content
                
                # Capture token usage from OpenAI response
                if hasattr(response, 'usage') and response.usage:
                    prompt_tokens = getattr(response.usage, 'prompt_tokens', 0)
                    completion_tokens = getattr(response.usage, 'completion_tokens', 0)
                    total_tokens = getattr(response.usage, 'total_tokens', 0)
                    logger.info(f"OpenAI token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

            elif api_type == "ollama":
                response = client.chat(
                    model=request.model,
                    messages=[{"role": "user", "content": request.content}]
                )
                # Ollama response is a dictionary with 'message' key containing another dict with 'content'
                content = response['message']['content']

            elif api_type == "groq":
                response = client.chat.completions.create(
                    model=request.model,
                    messages=[{"role": "user", "content": request.content}],
                    max_tokens=request.max_tokens,
                    temperature=request.temperature or 0.7
                )
                content = response.choices[0].message.content
                
                # Capture token usage from Groq response
                if hasattr(response, 'usage') and response.usage:
                    prompt_tokens = getattr(response.usage, 'prompt_tokens', 0)
                    completion_tokens = getattr(response.usage, 'completion_tokens', 0)
                    total_tokens = getattr(response.usage, 'total_tokens', 0)
                    logger.info(f"Groq token usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

            elif api_type == "searchengine":
                import requests
                
                # Get API configuration
                client_info = self._clients.get(request.api_name, {})
                api_url = client_info.get('api_url', '')
                if not api_url:
                    raise ValueError(f"No API URL configured for {request.api_name}")
                
                # Get number of results from parameters
                num_results = request.additional_params.get('num_results', 3) if request.additional_params else 3
                
                # Extract parameters from additional_params
                params = {
                    'q': request.content,  # Search query
                    'format': 'json',
                    'n': num_results * 2  # Pass through the number of results, doubled for filtering
                }
                
                if request.additional_params:
                    params.update({
                        'skip': request.additional_params.get('skip', 0),
                        'language': 'en'
                    })
                
                # Make the search request
                logger.info(f"Making search request to {api_url}")
                logger.debug(f"Search params: {params}")
                response = requests.get(f"{api_url.rstrip('/')}/search", params=params)
                
                if response.status_code != 200:
                    raise ValueError(f"Search request failed with status {response.status_code}")
                
                # Parse results and clean URLs
                results = response.json()
                search_results = []
                clean_urls = []  # Store clean URLs as we process them
                
                # Only process up to num_results
                required_count = num_results
                for result in results.get('results', []):
                    title = result.get('title', '')
                    url = APIService.clean_url(result.get('url', ''))
                    if url:  # Only add if we have a valid URL
                        clean_urls.append(url)  # Store the clean URL
                        snippet = result.get('content', '')
                        search_results.append(f"Title: {title}\nURL: {url}\nSummary: {snippet}\n")
                    if len(clean_urls) >= required_count:
                        break
                
                content = "\n".join(search_results) if search_results else "No results found"
                
                logger.info(f"Returning {len(clean_urls)} search results (limited to {required_count})")
                logger.debug(f"Clean URLs: {clean_urls}")
                return APIResponse(
                    content=content, 
                    raw_response={'results': clean_urls}, 
                    success=True
                )

            else:
                return APIResponse(
                    content="",
                    raw_response=None,
                    success=False,
                    error=f"Unsupported API type: {api_type}"
                )

            return APIResponse(
                content=content,
                raw_response=response,
                success=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )

        except Exception as e:
            logger.error(f"Error in API request to {request.api_name}: {str(e)}")
            return APIResponse(
                content="",
                raw_response=None,
                success=False,
                error=str(e)
            )

    def validate_request(self, request: APIRequest) -> Optional[str]:
        """
        Validate an API request before sending.
        
        Args:
            request: APIRequest object to validate
            
        Returns:
            Error message if validation fails, None if validation succeeds
        """
        if not request.api_name:
            return "API name is required"
        if not request.content:
            return "Content is required"
        if request.api_name not in self._clients:
            return f"API endpoint {request.api_name} not available"
        return None
