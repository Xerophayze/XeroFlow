import requests
from ollama import Client
from openai import OpenAI
from openai import OpenAIError
import os
import traceback
import json
from typing import Dict, Any, Optional, List
from services.api_service import APIService, APIRequest
import re
import math

# --- Parameter Sanitization Helpers ---
def _sanitize_openai_params(model: Optional[str], params: Dict[str, Any]) -> Dict[str, Any]:
    """Apply OpenAI model-specific parameter rules.

    - o3-* reasoning models: ensure temperature is not sent.
    - gpt-5* models: only default temperature=1 is supported; omit any provided value.
    """
    try:
        model_norm = (model or "").lower()
        # Remove temperature for o3 models (plain or with suffix)
        if model_norm.startswith('o3'):
            if 'temperature' in params:
                print("[DEBUG] Sanitization: removing temperature for o3 model")
                params.pop('temperature', None)
            return params

        # GPT-5: omit temperature entirely to use default=1
        if model_norm.startswith('gpt-5'):
            if 'temperature' in params and params.get('temperature') != 1:
                print("[DEBUG] Sanitization: removing non-default temperature for GPT-5 (must be 1)")
            params.pop('temperature', None)
            return params
    except Exception as e:
        # Do not let sanitization errors block request
        print(f"[DEBUG] Sanitization error (OpenAI): {e}")
    return params
try:
    import mutagen
    from mutagen.wave import WAVE
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.aac import AAC
    from mutagen.mp4 import MP4
    # In newer versions of mutagen, OggVorbis is in its own module
    try:
        from mutagen.oggvorbis import OggVorbis
        from mutagen.ogg import OggFileType
    except ImportError:
        # Fallback for older versions
        from mutagen.ogg import OggFileType, OggVorbis
    MUTAGEN_AVAILABLE = True
    print("[INFO] Successfully imported mutagen")
except ImportError as e:
    MUTAGEN_AVAILABLE = False
    print("[WARNING] mutagen library not available. Audio duration calculation will be limited.")
    print("[DEBUG] Import error details:", str(e))

# Optional imports for audio duration detection
LIBROSA_AVAILABLE = False
SOUNDFILE_AVAILABLE = False
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    pass

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    pass

# Optional imports for different API providers
ANTHROPIC_AVAILABLE = False
GROQ_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    print("[API Handler] Anthropic (Claude) API support not available. Run 'pip install anthropic' to enable.")

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    print("[API Handler] Groq API support not available. Run 'pip install groq' to enable.")

GOOGLE_GENAI_AVAILABLE = False
try:
    import google.genai as genai
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    print("[API Handler] Google Gemini API support not available. Run 'pip install google-genai' to enable.")

def process_api_request(api_name: str, config: Dict[str, Any], request_data: Dict[str, Any], is_whisper: bool = False) -> Optional[Dict[str, Any]]:
    """
    Process an API request using the specified endpoint.
    
    Args:
        api_name (str): Name of the API endpoint to use
        config (dict): Configuration containing API settings
        request_data (dict): Data to send to the API
        is_whisper (bool): Whether this is a Whisper API request
    
    Returns:
        dict: API response
    """
    try:
        print(f"[DEBUG] Processing API request: api_name={api_name}, is_whisper={is_whisper}")
        print(f"[DEBUG] Request data: {request_data}")
        
        # Get API configuration
        interfaces = config.get('interfaces', {})
        if not interfaces:
            print("[DEBUG] No interfaces found in config")
            return None
            
        if api_name not in interfaces:
            print(f"[DEBUG] API endpoint '{api_name}' not found in interfaces. Available endpoints: {list(interfaces.keys())}")
            return None

        api_config = interfaces[api_name]
        print(f"[DEBUG] API config: {api_config}")
        
        # Get configuration values, supporting both old and new key names
        api_type = api_config.get('type') or api_config.get('api_type')
        api_key = api_config.get('api_key')
        api_url = (api_config.get('api_url') or api_config.get('url', '')).rstrip('/')
        selected_model = api_config.get('selected_model') or api_config.get('model')

        if not api_type:
            print(f"[DEBUG] API type is missing for endpoint '{api_name}'")
            return None
            
        if api_type != "SearchEngine" and not api_key:
            print(f"[DEBUG] API key is missing for endpoint '{api_name}'")
            return None

        print(f"[DEBUG] API type: {api_type}, URL: {api_url}, Model: {selected_model}")

        if api_type == "OpenAI":
            from openai import OpenAI

            # Initialize OpenAI client
            try:
                if api_url == "https://api.openai.com":
                    print("[DEBUG] Using default OpenAI API URL")
                    client = OpenAI(api_key=api_key)
                else:
                    print(f"[DEBUG] Using custom API URL: {api_url}")
                    client = OpenAI(api_key=api_key, base_url=api_url)
            except Exception as e:
                print(f"[DEBUG] Error initializing OpenAI client: {str(e)}")
                return None

            if is_whisper:
                if 'file' not in request_data:
                    print("[DEBUG] Error: No audio file provided for transcription")
                    return None

                audio_file = request_data['file']
                model = request_data.get('model', 'whisper-1')

                print(f"[DEBUG] Processing audio file: {audio_file} with model: {model}")

                try:
                    # Make the transcription request
                    with open(audio_file, 'rb') as audio:
                        print("[DEBUG] Successfully opened audio file")
                        print(f"[DEBUG] Audio file size: {os.path.getsize(audio_file) / (1024*1024):.2f} MB")
                        
                        try:
                            # Force the base URL to be OpenAI's API URL for Whisper requests
                            original_base_url = client.base_url
                            client.base_url = "https://api.openai.com/v1"
                            
                            response = client.audio.transcriptions.create(
                                model=model,
                                file=audio,
                                response_format="text"
                            )
                            
                            # Restore the original base URL
                            client.base_url = original_base_url
                            
                            print("[DEBUG] Got transcription response")
                            print(f"[DEBUG] Response type: {type(response)}")
                            
                            # For Whisper API, we need to estimate token usage
                            result = {}
                            
                            if hasattr(response, 'text'):
                                transcribed_text = response.text
                                result = {'text': transcribed_text}
                            elif isinstance(response, str):
                                transcribed_text = response
                                result = {'text': transcribed_text}
                            else:
                                print(f"[DEBUG] Unexpected response format: {response}")
                                return None
                            
                            # Estimate token usage based on text length
                            # Using approximation of 1 token per 4 characters
                            text_length = len(transcribed_text)
                            estimated_tokens = max(1, text_length // 4)
                            
                            # Add estimated token usage to response
                            result['token_usage'] = {
                                'prompt_tokens': 0,  # Audio input doesn't use text tokens
                                'completion_tokens': estimated_tokens,
                                'total_tokens': estimated_tokens
                            }
                            
                            # Calculate audio duration using mutagen library
                            if LIBROSA_AVAILABLE:
                                try:
                                    audio_duration = librosa.get_duration(filename=audio_file)
                                    audio_duration = round(audio_duration, 2)  # Round to 2 decimal places
                                    result['audio_duration'] = audio_duration
                                    print(f"[DEBUG] Audio duration via librosa: {audio_duration:.2f} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Error calculating audio duration with librosa: {str(e)}")
                            elif SOUNDFILE_AVAILABLE:
                                try:
                                    info = sf.info(audio_file)
                                    audio_duration = round(info.duration, 2)  # Round to 2 decimal places
                                    result['audio_duration'] = audio_duration
                                    print(f"[DEBUG] Audio duration via soundfile: {audio_duration:.2f} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Error calculating audio duration with soundfile: {str(e)}")
                            elif MUTAGEN_AVAILABLE:
                                audio_duration = 0
                                duration_source = "unknown"
                                
                                # First try auto-detection
                                try:
                                    print(f"[DEBUG] Attempting auto-detection of audio format for {audio_file}")
                                    audio = mutagen.File(audio_file)
                                    if audio is not None and hasattr(audio.info, 'length'):
                                        audio_duration = audio.info.length
                                        duration_source = "auto-detect"
                                        print(f"[DEBUG] Audio duration via auto-detection: {audio_duration:.2f} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Auto-detection failed: {str(e)}")
                                
                                # If auto-detection failed or returned 0, try specific format detection
                                if audio_duration <= 0:
                                    try:
                                        print(f"[DEBUG] Trying format-specific detection")
                                        if audio_file.lower().endswith('.wav'):
                                            audio = WAVE(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "WAVE"
                                        elif audio_file.lower().endswith('.mp3'):
                                            audio = MP3(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "MP3"
                                        elif audio_file.lower().endswith('.flac'):
                                            audio = FLAC(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "FLAC"
                                        elif audio_file.lower().endswith('.aac'):
                                            audio = AAC(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "AAC"
                                        elif audio_file.lower().endswith('.mp4') or audio_file.lower().endswith('.m4a'):
                                            audio = MP4(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "MP4"
                                        elif audio_file.lower().endswith('.ogg'):
                                            audio = OggFileType(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "OGG"
                                        
                                        print(f"[DEBUG] Audio duration via {duration_source}: {audio_duration:.2f} seconds")
                                    except Exception as e:
                                        print(f"[DEBUG] Format-specific detection failed: {str(e)}")
                                
                                # Sanity check for unreasonably low durations
                                if audio_duration > 0:
                                    # Get file size in MB for reference
                                    file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
                                    print(f"[DEBUG] File size: {file_size_mb:.2f} MB")
                                    
                                    # Estimate duration based on file size for comparison
                                    if audio_file.lower().endswith('.wav'):
                                        estimated_duration = file_size_mb / 10 * 60  # WAV: ~10MB/min
                                    elif audio_file.lower().endswith('.mp3'):
                                        estimated_duration = file_size_mb / 1 * 60   # MP3: ~1MB/min
                                    else:
                                        estimated_duration = file_size_mb / 2 * 60   # Default: ~2MB/min
                                    
                                    print(f"[DEBUG] Size-based duration estimate: {estimated_duration:.2f} seconds")
                                    
                                    # If detected duration is much lower than file-size estimate (more than 3x difference)
                                    # This helps catch cases where mutagen incorrectly reports a short duration
                                    if audio_duration * 3 < estimated_duration:
                                        print(f"[DEBUG] Warning: Detected duration ({audio_duration:.2f}s) much shorter than expected ({estimated_duration:.2f}s)")
                                        print(f"[DEBUG] Using file size estimate instead")
                                        audio_duration = estimated_duration
                                        duration_source = "file-size-override"
                                
                                result['audio_duration'] = round(audio_duration, 2)  # Round to 2 decimal places
                                print(f"[DEBUG] Final audio duration: {audio_duration:.2f} seconds via {duration_source}")
                            else:
                                # Fallback: estimate duration based on file size
                                # Estimate duration based on file extension and typical bitrates
                                try:
                                    file_size_bytes = os.path.getsize(audio_file)
                                    file_size_mb = file_size_bytes / (1024 * 1024)
                                    
                                    if audio_file.endswith('.wav'):
                                        # WAV: ~10MB per minute (16-bit, 44.1kHz, stereo)
                                        audio_duration = file_size_mb / 10 * 60
                                    elif audio_file.endswith('.mp3'):
                                        # MP3: ~1MB per minute (128kbps)
                                        audio_duration = file_size_mb / 1 * 60
                                    elif audio_file.endswith('.flac'):
                                        # FLAC: ~5MB per minute (typical compression ratio)
                                        audio_duration = file_size_mb / 5 * 60
                                    elif audio_file.endswith('.aac'):
                                        # AAC: ~0.9MB per minute (128kbps)
                                        audio_duration = file_size_mb / 0.9 * 60
                                    elif audio_file.endswith('.mp4'):
                                        # MP4 audio: ~1MB per minute (128kbps)
                                        audio_duration = file_size_mb / 1 * 60
                                    elif audio_file.endswith('.ogg'):
                                        # OGG: ~0.8MB per minute (128kbps)
                                        audio_duration = file_size_mb / 0.8 * 60
                                    elif audio_file.endswith('.m4a'):
                                        # M4A: ~1MB per minute (128kbps)
                                        audio_duration = file_size_mb / 1 * 60
                                    else:
                                        # Default estimate for unknown formats
                                        audio_duration = file_size_mb / 2 * 60
                                    
                                    # Round up to nearest second
                                    audio_duration = round(audio_duration, 2)  # Round to 2 decimal places
                                    result['audio_duration'] = audio_duration
                                    print(f"[DEBUG] Estimated audio duration from file size: {audio_duration} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Error estimating audio duration from file size: {str(e)}")
                            
                            print(f"[DEBUG] Estimated token usage for Whisper: {estimated_tokens} tokens")
                            return result
                        except OpenAIError as oe:
                            print(f"[DEBUG] OpenAI API Error: {str(oe)}")
                            if hasattr(oe, 'response'):
                                print(f"[DEBUG] API Response: {oe.response}")
                            return None
                            
                except Exception as e:
                    print(f"[DEBUG] Error during transcription: {str(e)}")
                    print(f"[DEBUG] Error type: {type(e)}")
                    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                    return None
            else:
                try:
                    messages = []
                    if 'system_message' in request_data:
                        messages.append({"role": "system", "content": request_data['system_message']})
                    
                    # Handle different message formats
                    if 'messages' in request_data and isinstance(request_data['messages'], list):
                        messages = request_data['messages']
                    elif 'content' in request_data:
                        messages.append({"role": "user", "content": request_data['content']})
                    elif 'prompt' in request_data:
                        messages.append({"role": "user", "content": request_data['prompt']})
                    
                    # Get max tokens from config or request data
                    max_tokens = request_data.get('max_tokens', api_config.get('max_tokens', 2000))
                    
                    # Create completion request parameters
                    completion_params = {
                        'model': selected_model,
                        'messages': messages,
                    }
                    
                    # Add model-specific parameters
                    if selected_model and selected_model.lower().startswith('o3'):
                        completion_params['max_completion_tokens'] = max_tokens
                    else:
                        completion_params['max_tokens'] = max_tokens
                        completion_params['temperature'] = request_data.get('temperature', 0.7)

                    # Sanitize params for model-specific constraints (e.g., GPT-5 temperature)
                    completion_params = _sanitize_openai_params(selected_model, completion_params)
                    
                    print(f"[DEBUG] Sending OpenAI request with messages: {messages}")
                    response = client.chat.completions.create(**completion_params)
                    print("[DEBUG] Got chat completion response")
                    
                    # Extract token usage information
                    token_usage = {}
                    if hasattr(response, 'usage') and response.usage:
                        token_usage = {
                            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
                            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
                            'total_tokens': getattr(response.usage, 'total_tokens', 0)
                        }
                        print(f"[DEBUG] Token usage: {token_usage}")
                    
                    # Extract content from response
                    content = None
                    try:
                        if hasattr(response, 'choices') and len(response.choices) > 0:
                            if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                                content = response.choices[0].message.content
                                # Ensure we preserve the original content including markdown formatting
                                # No need to strip or modify the content
                    except Exception as content_error:
                        print(f"[DEBUG] Error extracting content from response: {str(content_error)}")
                        print(f"[DEBUG] Response structure: {response}")
                    
                    if content is None:
                        print("[DEBUG] Failed to extract content from response")
                        return None
                    
                    # Return content and token usage
                    return {
                        'content': content,
                        'token_usage': token_usage
                    }
                except Exception as e:
                    print(f"[DEBUG] Error during chat completion: {str(e)}")
                    return None

        elif api_type == "SearchEngine":
            try:
                # Get the number of results from request data
                num_results = request_data.get('num_results', 3)
                try:
                    num_results = int(num_results)
                except (TypeError, ValueError):
                    num_results = 3
                
                print(f"[DEBUG] Making search request with query: {request_data.get('content', '')}")
                
                # Create API request
                api_request = APIRequest(
                    content=request_data.get('content', ''),
                    api_name=api_name,
                    additional_params={
                        'num_results': num_results,
                        'skip': request_data.get('skip', 0),
                        'format': 'json'
                    }
                )
                
                # Send request through API service
                api_service = APIService(config)
                response = api_service.send_request(api_request)
                
                if response.success and response.raw_response:
                    # Get URLs from response and ensure they're clean
                    urls = response.raw_response.get('results', [])
                    
                    # Additional cleaning and filtering
                    clean_urls = []
                    for url in urls:
                        clean_url = APIService.clean_url(url)
                        if clean_url:
                            clean_urls.append(clean_url)
                    
                    print(f"[DEBUG] Search successful, found {len(clean_urls)} valid URLs")
                    if clean_urls:
                        print("[DEBUG] Cleaned URLs:")
                        for url in clean_urls:
                            print(f"[DEBUG] - {url}")
                    return {'urls': clean_urls}
                else:
                    print(f"[DEBUG] Search API Error: {response.error}")
                    return f"Error: Search request failed - {response.error}"
                    
            except Exception as e:
                print(f"[DEBUG] Error during search request: {str(e)}")
                print(f"[DEBUG] Error type: {type(e)}")
                return f"Error during search: {str(e)}"

        elif api_type == "Groq":
            if not GROQ_AVAILABLE:
                print("[DEBUG] Groq API support not available")
                return None

            try:
                print("[DEBUG] Initializing Groq client")
                client = Groq(api_key=api_key)
                messages = []
                if 'system_message' in request_data:
                    messages.append({"role": "system", "content": request_data['system_message']})
                messages.append({"role": "user", "content": request_data['content']})
                response = client.chat.completions.create(
                    model=api_config.get('selected_model', 'mixtral-8x7b-32768'),
                    messages=messages,
                    max_tokens=api_config.get('max_tokens')
                )
                print("[DEBUG] Successfully got Groq response")
                return response
            except Exception as e:
                print(f"[DEBUG] Error in Groq chat completion: {str(e)}")
                return None

        elif api_type == "Ollama":
            try:
                print("[DEBUG] Using Ollama API")
                client = Client(host=api_url)
                messages = []
                if 'system_message' in request_data:
                    messages.append({"role": "system", "content": request_data['system_message']})
                messages.append({"role": "user", "content": request_data['content']})
                response = client.chat(
                    model=api_config.get('selected_model', 'llama2'),
                    messages=messages
                )
                return response
            except Exception as e:
                print(f"[DEBUG] Error in Ollama chat: {str(e)}")
                return None

        else:
            print(f"[DEBUG] Unsupported API type: {api_type}")
            return {'error': f"Unsupported API type '{api_type}'"}
    
    except Exception as e:
        print(f"[DEBUG] Error in process_api_request: {str(e)}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return None

def process_api_request_v2(api_name: str, config: Dict[str, Any], request_data: Dict[str, Any], is_whisper: bool = False) -> Optional[Dict[str, Any]]:
    """
    Process an API request using the specified endpoint.
    
    Args:
        api_name (str): Name of the API endpoint to use
        config (dict): Configuration containing API settings
        request_data (dict): Data to send to the API
        is_whisper (bool): Whether this is a Whisper API request
    
    Returns:
        dict: API response
    """
    try:
        # Get API configuration
        interfaces = config.get('interfaces', {})
        if not interfaces:
            print("[DEBUG] No interfaces found in config")
            return None
            
        if api_name not in interfaces:
            print(f"[DEBUG] API endpoint '{api_name}' not found in interfaces. Available endpoints: {list(interfaces.keys())}")
            return None

        api_config = interfaces[api_name]
        print(f"[DEBUG] API config: {api_config}")
        
        api_type = api_config.get('type')
        api_key = api_config.get('api_key')
        api_url = api_config.get('api_url', '').rstrip('/')

        if not api_type:
            print(f"[DEBUG] API type is missing for endpoint '{api_name}'")
            return None
            
        if api_type != "SearchEngine" and not api_key:
            print(f"[DEBUG] API key is missing for endpoint '{api_name}'")
            return None

        print(f"[DEBUG] API type: {api_type}, URL: {api_url}")

        if api_type == "OpenAI":
            from openai import OpenAI

            # Initialize OpenAI client
            try:
                if api_url == "https://api.openai.com":
                    print("[DEBUG] Using default OpenAI API URL")
                    client = OpenAI(api_key=api_key)
                else:
                    print(f"[DEBUG] Using custom API URL: {api_url}")
                    client = OpenAI(api_key=api_key, base_url=api_url)
            except Exception as e:
                print(f"[DEBUG] Error initializing OpenAI client: {str(e)}")
                return None

            if is_whisper:
                if 'file' not in request_data:
                    print("[DEBUG] Error: No audio file provided for transcription")
                    return None

                audio_file = request_data['file']
                model = request_data.get('model', 'whisper-1')

                print(f"[DEBUG] Processing audio file: {audio_file} with model: {model}")

                try:
                    with open(audio_file, 'rb') as audio:
                        print("[DEBUG] Successfully opened audio file")
                        print(f"[DEBUG] Audio file size: {os.path.getsize(audio_file) / (1024*1024):.2f} MB")
                        try:
                            original_base_url = client.base_url
                            client.base_url = "https://api.openai.com/v1"
                            
                            response = client.audio.transcriptions.create(
                                model=model,
                                file=audio,
                                response_format="text"
                            )
                            
                            client.base_url = original_base_url
                            
                            print("[DEBUG] Got transcription response")
                            
                            # For Whisper API, we need to estimate token usage
                            # since it doesn't provide a usage object
                            result = {}
                            
                            if hasattr(response, 'text'):
                                transcribed_text = response.text
                                result = {'text': transcribed_text}
                            elif isinstance(response, str):
                                transcribed_text = response
                                result = {'text': transcribed_text}
                            else:
                                print(f"[DEBUG] Unexpected response format: {response}")
                                return None
                            
                            # Estimate token usage based on text length
                            # Using approximation of 1 token per 4 characters
                            text_length = len(transcribed_text)
                            estimated_tokens = max(1, text_length // 4)
                            
                            # Add estimated token usage to response
                            result['token_usage'] = {
                                'prompt_tokens': 0,  # Audio input doesn't use text tokens
                                'completion_tokens': estimated_tokens,
                                'total_tokens': estimated_tokens
                            }
                            
                            # Calculate audio duration using mutagen library
                            if LIBROSA_AVAILABLE:
                                try:
                                    audio_duration = librosa.get_duration(filename=audio_file)
                                    audio_duration = round(audio_duration, 2)  # Round to 2 decimal places
                                    result['audio_duration'] = audio_duration
                                    print(f"[DEBUG] Audio duration via librosa: {audio_duration:.2f} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Error calculating audio duration with librosa: {str(e)}")
                            elif SOUNDFILE_AVAILABLE:
                                try:
                                    info = sf.info(audio_file)
                                    audio_duration = round(info.duration, 2)  # Round to 2 decimal places
                                    result['audio_duration'] = audio_duration
                                    print(f"[DEBUG] Audio duration via soundfile: {audio_duration:.2f} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Error calculating audio duration with soundfile: {str(e)}")
                            elif MUTAGEN_AVAILABLE:
                                audio_duration = 0
                                duration_source = "unknown"
                                
                                # First try auto-detection
                                try:
                                    print(f"[DEBUG] Attempting auto-detection of audio format for {audio_file}")
                                    audio = mutagen.File(audio_file)
                                    if audio is not None and hasattr(audio.info, 'length'):
                                        audio_duration = audio.info.length
                                        duration_source = "auto-detect"
                                        print(f"[DEBUG] Audio duration via auto-detection: {audio_duration:.2f} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Auto-detection failed: {str(e)}")
                                
                                # If auto-detection failed or returned 0, try specific format detection
                                if audio_duration <= 0:
                                    try:
                                        print(f"[DEBUG] Trying format-specific detection")
                                        if audio_file.lower().endswith('.wav'):
                                            audio = WAVE(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "WAVE"
                                        elif audio_file.lower().endswith('.mp3'):
                                            audio = MP3(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "MP3"
                                        elif audio_file.lower().endswith('.flac'):
                                            audio = FLAC(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "FLAC"
                                        elif audio_file.lower().endswith('.aac'):
                                            audio = AAC(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "AAC"
                                        elif audio_file.lower().endswith('.mp4') or audio_file.lower().endswith('.m4a'):
                                            audio = MP4(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "MP4"
                                        elif audio_file.lower().endswith('.ogg'):
                                            audio = OggFileType(audio_file)
                                            audio_duration = audio.info.length
                                            duration_source = "OGG"
                                        
                                        print(f"[DEBUG] Audio duration via {duration_source}: {audio_duration:.2f} seconds")
                                    except Exception as e:
                                        print(f"[DEBUG] Format-specific detection failed: {str(e)}")
                                
                                # Sanity check for unreasonably low durations
                                if audio_duration > 0:
                                    # Get file size in MB for reference
                                    file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
                                    print(f"[DEBUG] File size: {file_size_mb:.2f} MB")
                                    
                                    # Estimate duration based on file size for comparison
                                    if audio_file.lower().endswith('.wav'):
                                        estimated_duration = file_size_mb / 10 * 60  # WAV: ~10MB/min
                                    elif audio_file.lower().endswith('.mp3'):
                                        estimated_duration = file_size_mb / 1 * 60   # MP3: ~1MB/min
                                    else:
                                        estimated_duration = file_size_mb / 2 * 60   # Default: ~2MB/min
                                    
                                    print(f"[DEBUG] Size-based duration estimate: {estimated_duration:.2f} seconds")
                                    
                                    # If detected duration is much lower than file-size estimate (more than 3x difference)
                                    # This helps catch cases where mutagen incorrectly reports a short duration
                                    if audio_duration * 3 < estimated_duration:
                                        print(f"[DEBUG] Warning: Detected duration ({audio_duration:.2f}s) much shorter than expected ({estimated_duration:.2f}s)")
                                        print(f"[DEBUG] Using file size estimate instead")
                                        audio_duration = estimated_duration
                                        duration_source = "file-size-override"
                                
                                result['audio_duration'] = round(audio_duration, 2)  # Round to 2 decimal places
                                print(f"[DEBUG] Final audio duration: {audio_duration:.2f} seconds via {duration_source}")
                            else:
                                # Fallback: estimate duration based on file size
                                # Estimate duration based on file extension and typical bitrates
                                try:
                                    file_size_bytes = os.path.getsize(audio_file)
                                    file_size_mb = file_size_bytes / (1024 * 1024)
                                    
                                    if audio_file.endswith('.wav'):
                                        # WAV: ~10MB per minute (16-bit, 44.1kHz, stereo)
                                        audio_duration = file_size_mb / 10 * 60
                                    elif audio_file.endswith('.mp3'):
                                        # MP3: ~1MB per minute (128kbps)
                                        audio_duration = file_size_mb / 1 * 60
                                    elif audio_file.endswith('.flac'):
                                        # FLAC: ~5MB per minute (typical compression ratio)
                                        audio_duration = file_size_mb / 5 * 60
                                    elif audio_file.endswith('.aac'):
                                        # AAC: ~0.9MB per minute (128kbps)
                                        audio_duration = file_size_mb / 0.9 * 60
                                    elif audio_file.endswith('.mp4'):
                                        # MP4 audio: ~1MB per minute (128kbps)
                                        audio_duration = file_size_mb / 1 * 60
                                    elif audio_file.endswith('.ogg'):
                                        # OGG: ~0.8MB per minute (128kbps)
                                        audio_duration = file_size_mb / 0.8 * 60
                                    elif audio_file.endswith('.m4a'):
                                        # M4A: ~1MB per minute (128kbps)
                                        audio_duration = file_size_mb / 1 * 60
                                    else:
                                        # Default estimate for unknown formats
                                        audio_duration = file_size_mb / 2 * 60
                                    
                                    # Round up to nearest second
                                    audio_duration = round(audio_duration, 2)  # Round to 2 decimal places
                                    result['audio_duration'] = audio_duration
                                    print(f"[DEBUG] Estimated audio duration from file size: {audio_duration} seconds")
                                except Exception as e:
                                    print(f"[DEBUG] Error estimating audio duration from file size: {str(e)}")
                            
                            print(f"[DEBUG] Estimated token usage for Whisper: {estimated_tokens} tokens")
                            return result
                        except OpenAIError as oe:
                            print(f"[DEBUG] OpenAI API Error: {str(oe)}")
                            if hasattr(oe, 'response'):
                                print(f"[DEBUG] API Response: {oe.response}")
                            return None
                            
                except Exception as e:
                    print(f"[DEBUG] Error during transcription: {str(e)}")
                    print(f"[DEBUG] Error type: {type(e)}")
                    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                    return None
            else:
                try:
                    messages = []
                    if 'system_message' in request_data:
                        messages.append({"role": "system", "content": request_data['system_message']})
                    
                    # Handle different message formats
                    if 'messages' in request_data and isinstance(request_data['messages'], list):
                        messages = request_data['messages']
                    elif 'content' in request_data:
                        messages.append({"role": "user", "content": request_data['content']})
                    elif 'prompt' in request_data:
                        messages.append({"role": "user", "content": request_data['prompt']})
                    
                    # Get max tokens from config or request data
                    max_tokens = request_data.get('max_tokens', api_config.get('max_tokens', 2000))
                    
                    # Create completion request parameters
                    completion_params = {
                        'model': api_config.get('selected_model', 'gpt-3.5-turbo'),
                        'messages': messages,
                    }
                    
                    # Add model-specific parameters
                    selected_model_v2 = api_config.get('selected_model', 'gpt-3.5-turbo')
                    if selected_model_v2 and selected_model_v2.lower().startswith('o3'):
                        completion_params['max_completion_tokens'] = max_tokens
                    else:
                        completion_params['max_tokens'] = max_tokens
                        completion_params['temperature'] = request_data.get('temperature', 0.7)

                    # Sanitize params for model-specific constraints (o3/gpt-5)
                    completion_params = _sanitize_openai_params(selected_model_v2, completion_params)

                    print(f"[DEBUG] Sending OpenAI request with messages: {messages}")
                    response = client.chat.completions.create(**completion_params)
                    print("[DEBUG] Got chat completion response")
                    
                    # Extract token usage information
                    token_usage = {}
                    if hasattr(response, 'usage') and response.usage:
                        token_usage = {
                            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
                            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
                            'total_tokens': getattr(response.usage, 'total_tokens', 0)
                        }
                        print(f"[DEBUG] Token usage: {token_usage}")
                    
                    # Extract content from response
                    content = None
                    try:
                        if hasattr(response, 'choices') and len(response.choices) > 0:
                            if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                                content = response.choices[0].message.content
                                # Ensure we preserve the original content including markdown formatting
                                # No need to strip or modify the content
                    except Exception as content_error:
                        print(f"[DEBUG] Error extracting content from response: {str(content_error)}")
                        print(f"[DEBUG] Response structure: {response}")
                    
                    if content is None:
                        print("[DEBUG] Failed to extract content from response")
                        return None
                    
                    # Return content and token usage
                    return {
                        'content': content,
                        'token_usage': token_usage
                    }
                except Exception as e:
                    print(f"[DEBUG] Error during chat completion: {str(e)}")
                    return None
            
        elif api_type == "Groq":
            if not GROQ_AVAILABLE:
                print("[DEBUG] Groq API support not available")
                return None

            try:
                print("[DEBUG] Initializing Groq client")
                client = Groq(api_key=api_key)
                messages = []
                if 'system_message' in request_data:
                    messages.append({"role": "system", "content": request_data['system_message']})
                messages.append({"role": "user", "content": request_data['content']})
                response = client.chat.completions.create(
                    model=api_config.get('selected_model', 'mixtral-8x7b-32768'),
                    messages=messages,
                    max_tokens=api_config.get('max_tokens')
                )
                print("[DEBUG] Successfully got Groq response")
                
                # Extract token usage information
                token_usage = {}
                if hasattr(response, 'usage') and response.usage:
                    token_usage = {
                        'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
                        'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
                        'total_tokens': getattr(response.usage, 'total_tokens', 0)
                    }
                    print(f"[DEBUG] Token usage: {token_usage}")
                
                # Return both content and token usage
                return {
                    'content': response.choices[0].message.content,
                    'token_usage': token_usage
                }
            except Exception as e:
                print(f"[DEBUG] Error in Groq chat completion: {str(e)}")
                return None

        elif api_type == "Google":
            if not GOOGLE_GENAI_AVAILABLE:
                return {"error": "Google Gemini API support not available. Run 'pip install google-genai' to enable."}
            try:
                # Initialize the new google.genai client
                client = genai.Client(api_key=api_key)
                model_name = api_config.get('selected_model', 'gemini-pro')

                messages = request_data.get("messages", [])
                if not messages:
                    prompt = request_data.get("prompt") or request_data.get("content")
                    if prompt:
                        messages = [{'role': 'user', 'content': prompt}]

                # Convert messages to Google's format
                gemini_messages = []
                for msg in messages:
                    role = msg.get('role')
                    if role == 'assistant':
                        role = 'model'
                    
                    content = msg.get('content') or msg.get('parts')
                    if content:
                        gemini_messages.append({'role': role, 'parts': [content] if isinstance(content, str) else content})

                # Use new API: client.models.generate_content
                response = client.models.generate_content(
                    model=model_name,
                    contents=gemini_messages
                )

                # Token counting with new API
                prompt_token_count = client.models.count_tokens(
                    model=model_name,
                    contents=gemini_messages
                )
                completion_token_count = client.models.count_tokens(
                    model=model_name,
                    contents=response.text
                )
                
                prompt_tokens = prompt_token_count.total_tokens
                completion_tokens = completion_token_count.total_tokens
                total_tokens = prompt_tokens + completion_tokens

                return {
                    "content": response.text,
                    "token_usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens
                    }
                }
            except Exception as e:
                print(f"[DEBUG] Error in Google Gemini API call: {str(e)}")
                return {"error": str(e)}

        elif api_type == "Ollama":
            try:
                print("[DEBUG] Using Ollama API")
                client = Client(host=api_url)
                messages = []
                if 'system_message' in request_data:
                    messages.append({"role": "system", "content": request_data['system_message']})
                messages.append({"role": "user", "content": request_data['content']})
                response = client.chat(
                    model=api_config.get('selected_model', 'llama2'),
                    messages=messages
                )
                return response
            except Exception as e:
                print(f"[DEBUG] Error in Ollama chat: {str(e)}")
                return None

        else:
            print(f"[DEBUG] Unsupported API type: {api_type}")
            return {'error': f"Unsupported API type '{api_type}'"}
    
    except Exception as e:
        print(f"[DEBUG] Error in process_api_request_v2: {str(e)}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return None
