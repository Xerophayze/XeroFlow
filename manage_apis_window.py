# manage_apis_window.py

import tkinter as tk
from tkinter import ttk, messagebox
import yaml
import json
import requests
from typing import Dict, Any, Optional
import time
from config_utils import load_config, save_config
from services.pricing_service import PricingService

class APIConfigManager:
    def __init__(self):
        self.config = load_config()
        
    def fetch_available_models(self, api_type: str, api_key: str, base_url: str) -> list:
        """Fetch available models from the API provider."""
        try:
            if api_type.lower() == "openai":
                return self._fetch_openai_models(api_key, base_url)
            elif api_type.lower() == "ollama":
                return self._fetch_ollama_models(base_url)
            elif api_type.lower() == "groq":
                return self._fetch_groq_models(api_key, base_url)
            elif api_type.lower() == "claude":
                return self._fetch_claude_models(api_key, base_url)
            elif api_type.lower() == "google":
                return self._fetch_google_models(api_key)
            elif api_type.lower() == "searchengine":
                return self._fetch_searchengine_models(base_url)
            elif api_type.lower() == "lmstudio":
                return self._fetch_lmstudio_models(api_key, base_url)
            return []
        except Exception as e:
            print(f"Error fetching models: {str(e)}")
            return []
            
    def _fetch_openai_models(self, api_key: str, base_url: str) -> list:
        """Fetch available models from OpenAI."""
        try:
            url = f"{base_url.rstrip('/')}/v1/models"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                models = response.json().get('data', [])
                return [model['id'] for model in models if 'id' in model]
            return []
        except Exception as e:
            print(f"Error fetching OpenAI models: {str(e)}")
            return []
            
    def _fetch_ollama_models(self, base_url: str) -> list:
        """Fetch available models from Ollama."""
        try:
            url = f"{base_url.rstrip('/')}/api/tags"
            response = requests.get(url)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [model['name'] for model in models if 'name' in model]
            return []
        except Exception as e:
            print(f"Error fetching Ollama models: {str(e)}")
            return []
            
    def _fetch_groq_models(self, api_key: str, base_url: str) -> list:
        """Fetch available models from Groq."""
        try:
            # The correct endpoint according to Groq documentation
            url = f"{base_url.rstrip('/')}/openai/v1/models"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            print(f"Requesting Groq models from: {url}")
            response = requests.get(url, headers=headers)
            print(f"Groq API response status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Groq API response data: {data}")
                    models = data.get('data', [])
                    model_ids = [model['id'] for model in models if 'id' in model]
                    
                    # Sort models alphabetically for better organization
                    model_ids.sort()
                    
                    if model_ids:
                        return model_ids
                except Exception as e:
                    print(f"Error parsing Groq API response: {str(e)}")
            else:
                print(f"Groq API error response: {response.text}")
                
            # Fallback to known Groq models if API call fails
            print("Using fallback list of Groq models")
            return [
                # Production Models
                "llama-3.1-8b-instant",
                "llama-3.1-70b-versatile",
                "llama-3.1-405b-versatile",
                "llama-3-70b-versatile",
                "llama-3-8b-versatile",
                "gemma-2-9b-it",
                "mixtral-8x7b-instruct",
                "whisper-large-v3",
                "whisper-large-v3-turbo",
                "llama-guard-3-8b",
                
                # Preview Models
                "llama-3.3-70b-specdec",
                "llama-3.2-1b-preview",
                "llama-3.2-3b-preview",
                "llama-3.2-11b-vision",
                "llama-3.2-90b-vision-instruct",
                "qwen-qwq-32b",
                "mistral-saba-24b",
                "qwen-2.5-coder-32b",
                "qwen-2.5-32b",
                "deepseek-r1-distill-qwen-32b",
                "deepseek-r1-distill-llama-70b-specdec",
                "deepseek-r1-distill-llama-70b"
            ]
        except Exception as e:
            print(f"Error fetching Groq models: {str(e)}")
            # Fallback to known Groq models if exception occurs
            return [
                # Production Models
                "llama-3.1-8b-instant",
                "llama-3.1-70b-versatile",
                "llama-3.1-405b-versatile",
                "llama-3-70b-versatile",
                "llama-3-8b-versatile",
                "gemma-2-9b-it",
                "mixtral-8x7b-instruct",
                "whisper-large-v3",
                "whisper-large-v3-turbo",
                "llama-guard-3-8b",
                
                # Preview Models
                "llama-3.3-70b-specdec",
                "llama-3.2-1b-preview",
                "llama-3.2-3b-preview",
                "llama-3.2-11b-vision",
                "llama-3.2-90b-vision-instruct",
                "qwen-qwq-32b",
                "mistral-saba-24b",
                "qwen-2.5-coder-32b",
                "qwen-2.5-32b",
                "deepseek-r1-distill-qwen-32b",
                "deepseek-r1-distill-llama-70b-specdec",
                "deepseek-r1-distill-llama-70b"
            ]
            
    def _fetch_claude_models(self, api_key: str, base_url: str) -> list:
        """Fetch available models from AnthropX/Claude endpoints."""
        fallback_models = [
            "claude-3.5-sonnet-20241022",
            "claude-3.5-sonnet-20240620",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]

        try:
            if not api_key:
                print("Anthropic API key missing; returning fallback model list")
                return fallback_models

            api_root = base_url.rstrip('/') if base_url else "https://api.anthropic.com"
            url = f"{api_root}/v1/models"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "accept": "application/json",
            }

            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                model_ids = [model.get("id") for model in models if model.get("id")]
                if model_ids:
                    model_ids.sort()
                    return model_ids
                print("Anthropic model list empty; using fallback models")
                return fallback_models

            print(f"Anthropic API error {response.status_code}: {response.text}")
            return fallback_models
        except Exception as e:
            print(f"Error fetching Claude models: {str(e)}")
            return fallback_models
            
    def _fetch_google_models(self, api_key: str) -> list:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            models = []
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    models.append(model.name)
            return models
        except ImportError:
            return ["google-generativeai not installed"]
        except Exception as e:
            return [f"Error: {e}"]

    def _fetch_searchengine_models(self, base_url: str) -> list:
        """Fetch available models from SearchEngine."""
        try:
            url = f"{base_url.rstrip('/')}/search"
            response = requests.get(url)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [model['name'] for model in models if 'name' in model]
            return []
        except Exception as e:
            print(f"Error fetching SearchEngine models: {str(e)}")
            return []
        
    def _lmstudio_base(self, base_url: str) -> str:
        """Normalize LM Studio base URL to include /v1"""
        base = (base_url or "http://localhost:1234").rstrip('/')
        if base.endswith('/v1'):
            return base
        return f"{base}/v1"
    
    def _fetch_lmstudio_models(self, api_key: str, base_url: str) -> list:
        """Fetch available models from LM Studio."""
        try:
            url = f"{self._lmstudio_base(base_url)}/models"
            headers = {
                "Authorization": f"Bearer {api_key}" if api_key else None,
                "Content-Type": "application/json"
            }
            headers = {k: v for k, v in headers.items() if v}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = data.get("data") or data.get("models", [])
                # LM Studio returns {"data":[{"id": ...}]}, but fall back for newer schemas
                if isinstance(models, list):
                    names = []
                    for model in models:
                        if isinstance(model, dict):
                            if "id" in model:
                                names.append(model["id"])
                            elif "name" in model:
                                names.append(model["name"])
                        elif isinstance(model, str):
                            names.append(model)
                    return names
            print(f"LM Studio model fetch failed ({response.status_code}): {response.text[:200]}")
            return []
        except Exception as e:
            print(f"Error fetching LM Studio models: {str(e)}")
            return []
            
    def fetch_model_max_tokens(self, api_type: str, api_key: str, model: str, base_url: Optional[str] = None) -> Optional[int]:
        """Fetch the maximum token limit for a given model."""
        try:
            if api_type.lower() == "openai":
                return self._fetch_openai_max_tokens(api_key, model, base_url)
            elif api_type.lower() == "ollama":
                return self._fetch_ollama_max_tokens(model, base_url)
            elif api_type.lower() == "groq":
                return self._fetch_groq_max_tokens(api_key, model, base_url)
            elif api_type.lower() == "claude":
                return self._fetch_claude_max_tokens(model)
            elif api_type.lower() == "google":
                return self._fetch_google_max_tokens(api_key, model)
            elif api_type.lower() == "searchengine":
                return self._fetch_searchengine_max_tokens(model, base_url)
            elif api_type.lower() == "lmstudio":
                return self._fetch_lmstudio_max_tokens(api_key, model, base_url)
            return None
        except Exception as e:
            print(f"Error fetching max tokens: {str(e)}")
            return None
            
    def _fetch_openai_max_tokens(self, api_key: str, model: str, base_url: Optional[str] = None) -> Optional[int]:
        """Fetch max tokens for OpenAI models."""
        try:
            url = f"{base_url.rstrip('/')}/v1/models/{model}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                max_tokens = data.get('max_tokens') or data.get('limits', {}).get('max_tokens')
                if max_tokens:
                    return int(max_tokens)
                    
                # Fallback values for common models
                model_defaults = {
                    'gpt-4': 8192,
                    'gpt-4-32k': 32768,
                    'gpt-3.5-turbo': 4096,
                    'gpt-3.5-turbo-16k': 16384,
                    'gpt-4-turbo-preview': 128000
                }
                return model_defaults.get(model.lower())
            return None
        except Exception as e:
            print(f"Error fetching OpenAI max tokens: {str(e)}")
            return None
            
    def _fetch_ollama_max_tokens(self, model: str, base_url: Optional[str] = None) -> Optional[int]:
        """Fetch max tokens for Ollama models."""
        try:
            url = f"{base_url.rstrip('/')}/api/show"
            response = requests.post(url, json={"name": model})
            if response.status_code == 200:
                data = response.json()
                context_size = data.get('parameters', {}).get('context_length') or data.get('context_size')
                if context_size:
                    return int(context_size)
            return None
        except Exception as e:
            print(f"Error fetching Ollama max tokens: {str(e)}")
            return None
            
    def _fetch_groq_max_tokens(self, api_key: str, model: str, base_url: Optional[str] = None) -> Optional[int]:
        """Fetch max tokens for Groq models."""
        try:
            url = f"{base_url.rstrip('/')}/v1/models/{model}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                max_tokens = data.get('max_tokens') or data.get('limits', {}).get('max_tokens')
                if max_tokens:
                    return int(max_tokens)
            return None
        except Exception as e:
            print(f"Error fetching Groq max tokens: {str(e)}")
            return None
            
    def _fetch_claude_max_tokens(self, model: str) -> Optional[int]:
        """Return known max tokens for Claude models."""
        try:
            # Known context window sizes for Claude models
            claude_models = {
                "claude-3-opus-20240229": 200000,
                "claude-3-sonnet-20240229": 200000,
                "claude-3-haiku-20240307": 200000,
                "claude-2.1": 100000,
                "claude-2.0": 100000,
                "claude-instant-1.2": 100000
            }
            return claude_models.get(model.lower())
        except Exception as e:
            print(f"Error fetching Claude max tokens: {str(e)}")
            return None
            
    def _fetch_google_max_tokens(self, api_key: str, model: str) -> Optional[int]:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model_info = genai.get_model(model)
            return model_info.max_tokens
        except ImportError:
            return None
        except Exception as e:
            return None
            
    def _fetch_searchengine_max_tokens(self, model: str, base_url: Optional[str] = None) -> Optional[int]:
        """Fetch max tokens for SearchEngine models."""
        try:
            url = f"{base_url.rstrip('/')}/search"
            response = requests.get(url, params={"model": model})
            if response.status_code == 200:
                data = response.json()
                max_tokens = data.get('max_tokens')
                if max_tokens:
                    return int(max_tokens)
            return None
        except Exception as e:
            print(f"Error fetching SearchEngine max tokens: {str(e)}")
            return None
    
    def _fetch_lmstudio_max_tokens(self, api_key: str, model: str, base_url: Optional[str] = None) -> Optional[int]:
        """Attempt to fetch max tokens for LM Studio models."""
        try:
            url = f"{self._lmstudio_base(base_url)}/models/{model}"
            headers = {
                "Authorization": f"Bearer {api_key}" if api_key else None,
                "Content-Type": "application/json"
            }
            headers = {k: v for k, v in headers.items() if v}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                max_tokens = data.get('max_tokens') or data.get('context_window')
                if max_tokens:
                    return int(max_tokens)
            return None
        except Exception as e:
            print(f"Error fetching LM Studio max tokens: {str(e)}")
            return None

def manage_apis_window(parent, config, refresh_callback):
    """Create and manage the APIs configuration window."""
    
    api_config = APIConfigManager()
    
    def refresh_api_list():
        """Refresh the list of APIs in the listbox."""
        api_manage_listbox.delete(0, tk.END)
        for key in config['interfaces']:
            api_manage_listbox.insert(tk.END, key)
            
    def fetch_available_models():
        """Fetch available models based on current API configuration."""
        try:
            api_type = api_type_var.get().strip()
            api_key = api_key_entry.get().strip()
            base_url = url_entry.get().strip()
            
            if not all([api_type, base_url]):
                messagebox.showwarning("Warning", "Please fill in API type and URL first")
                return
                
            print(f"Fetching models for: Type={api_type}, URL={base_url}")
            models = api_config.fetch_available_models(api_type, api_key, base_url)
            
            if models:
                model_dropdown['values'] = models
                messagebox.showinfo("Success", f"Found {len(models)} available models")
            else:
                messagebox.showwarning("Warning", "No models found or couldn't fetch models")
        except Exception as e:
            print(f"Error fetching models: {str(e)}")
            messagebox.showerror("Error", f"Error fetching models: {str(e)}")
            
    def save_interface(name: str, is_new: bool = True):
        """Save or update an API interface configuration."""
        try:
            url = url_entry.get().strip()
            api_key = api_key_entry.get().strip()
            api_type = api_type_var.get().strip()
            model = model_var.get().strip()
            max_tokens = max_tokens_entry.get().strip()
            pricing_match = PricingService.get_model_pricing(model) if model else {}
            pricing_model = PricingService.normalize_model_name(model) if pricing_match else None
            
            if not all([name, url, api_type]):
                messagebox.showwarning("Warning", "Please fill in all required fields")
                return

            if model and not pricing_match:
                messagebox.showwarning(
                    "Pricing Not Found",
                    f"The selected model '{model}' is not in the pricing catalog. "
                    "Costs may be inaccurate until pricing is added."
                )
                
            # Determine models endpoint based on API type
            models_endpoint = {
                'OpenAI': '/v1/chat/completions',
                'Ollama': '/api/tags',
                'Groq': '/v1/chat/completions',
                'Claude': '/v1/messages',
                'Google': '/v1/generate',
                'SearchEngine': '/search',  # Default search endpoint, can be overridden by URL
                'LMStudio': '/v1/chat/completions'
            }.get(api_type, '/v1/chat/completions')
            
            interface_config = {
                'api_url': url,
                'api_key': api_key,
                'type': api_type,
                'selected_model': model,
                'pricing_model': pricing_model,
                'max_tokens': int(max_tokens) if max_tokens.isdigit() else None,
                'models_endpoint': models_endpoint
            }
            
            config['interfaces'][name] = interface_config
            save_config(config)
            
            refresh_api_list()
            refresh_callback()
            
            action = "added" if is_new else "updated"
            messagebox.showinfo("Success", f"API interface {action} successfully")
            clear_form()
            
        except Exception as e:
            print(f"Error saving interface: {str(e)}")
            messagebox.showerror("Error", f"Failed to save interface: {str(e)}")
            
    def save_new_interface():
        """Save a new API interface."""
        name = name_entry.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter an API name")
            return
            
        if name in config['interfaces']:
            messagebox.showwarning("Warning", "An API with this name already exists")
            return
            
        save_interface(name, True)
        
    def save_edited_interface(original_name: str):
        """Save changes to an existing API interface."""
        new_name = name_entry.get().strip()
        if not new_name:
            messagebox.showwarning("Warning", "Please enter an API name")
            return
            
        if new_name != original_name and new_name in config['interfaces']:
            messagebox.showwarning("Warning", "An API with this name already exists")
            return
            
        if new_name != original_name:
            config['interfaces'].pop(original_name, None)
            
        save_interface(new_name, False)
        
    def load_interface_details(event=None):
        """Load selected API interface details into the form."""
        selection = api_manage_listbox.curselection()
        if not selection:
            return
            
        selected_interface = api_manage_listbox.get(selection[0])
        interface_details = config['interfaces'].get(selected_interface, {})
        
        name_entry.delete(0, tk.END)
        name_entry.insert(0, selected_interface)
        
        url_entry.delete(0, tk.END)
        url_entry.insert(0, interface_details.get('api_url', ''))
        
        api_key_entry.delete(0, tk.END)
        api_key_entry.insert(0, interface_details.get('api_key', ''))
        
        api_type = interface_details.get('type', '')
        api_type_var.set(api_type)
        
        max_tokens_value = interface_details.get('max_tokens')
        max_tokens_entry.delete(0, tk.END)
        if max_tokens_value is not None:
            max_tokens_entry.insert(0, str(max_tokens_value))
            
        model = interface_details.get('selected_model', '')
        if model:
            model_var.set(model)
        update_pricing_match()
            
        save_button.config(text="Save Changes", 
                         command=lambda: save_edited_interface(selected_interface))
                         
    def delete_interface():
        """Delete the selected API interface."""
        selection = api_manage_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an API to delete")
            return
            
        selected_interface = api_manage_listbox.get(selection[0])
        if messagebox.askyesno("Confirm Delete", 
                             f"Are you sure you want to delete the API interface '{selected_interface}'?"):
            config['interfaces'].pop(selected_interface, None)
            save_config(config)
            refresh_api_list()
            refresh_callback()
            clear_form()
            messagebox.showinfo("Success", "API interface deleted successfully")
            
    def clear_form():
        """Clear all form fields."""
        name_entry.delete(0, tk.END)
        url_entry.delete(0, tk.END)
        api_key_entry.delete(0, tk.END)
        api_type_var.set('')
        model_var.set('')
        max_tokens_entry.delete(0, tk.END)
        pricing_status_var.set("")
        save_button.config(text="Add API Interface", command=save_new_interface)

    def update_pricing_match(event=None):
        """Update pricing status label based on selected model."""
        model = model_var.get().strip()
        if not model:
            pricing_status_var.set("")
            return

        pricing = PricingService.get_model_pricing(model)
        if pricing:
            normalized = PricingService.normalize_model_name(model)
            if normalized != model:
                pricing_status_var.set(f"Pricing matched: {normalized}")
            else:
                pricing_status_var.set("Pricing matched")
        else:
            pricing_status_var.set("Pricing: not found in catalog")
        
    def update_max_tokens():
        """Update max tokens based on selected API and model."""
        try:
            api_type = api_type_var.get().strip()
            api_key = api_key_entry.get().strip()
            model = model_var.get().strip()
            base_url = url_entry.get().strip()
            
            requires_key = api_type not in ("Ollama", "LMStudio", "SearchEngine")
            if not api_type or not model or not base_url or (requires_key and not api_key):
                messagebox.showwarning("Warning", "Please fill in API type, URL, model, and key if required")
                return
                
            print(f"Fetching max tokens for: Type={api_type}, Model={model}, URL={base_url}")
            max_tokens = api_config.fetch_model_max_tokens(api_type, api_key, model, base_url)
            
            if max_tokens:
                max_tokens_entry.delete(0, tk.END)
                max_tokens_entry.insert(0, str(max_tokens))
                messagebox.showinfo("Success", f"Successfully retrieved max tokens: {max_tokens}")
            else:
                messagebox.showwarning("Warning", "Could not automatically determine max tokens. Please enter manually.")
        except Exception as e:
            print(f"Error in update_max_tokens: {str(e)}")
            messagebox.showerror("Error", f"Error fetching max tokens: {str(e)}")
            
    def on_api_type_change(event=None):
        """Auto-fill the API URL based on the selected API type."""
        api_type = api_type_var.get()
        if api_type == "OpenAI":
            url_entry.delete(0, tk.END)
            url_entry.insert(0, "https://api.openai.com")
        elif api_type == "Groq":
            url_entry.delete(0, tk.END)
            url_entry.insert(0, "https://api.groq.com")
        elif api_type == "Claude":
            url_entry.delete(0, tk.END)
            url_entry.insert(0, "https://api.anthropic.com")
        elif api_type == "Google":
            url_entry.delete(0, tk.END)
            url_entry.insert(0, "https://api.google.com")
        elif api_type == "LMStudio":
            url_entry.delete(0, tk.END)
            url_entry.insert(0, "http://localhost:1234")
        # Don't auto-fill for Llama/Ollama as it's typically local and varies
    
    # Create main frame
    main_frame = ttk.Frame(parent)
    main_frame.grid(row=0, column=0, sticky="nsew")
    
    # Left side - API List
    list_frame = ttk.LabelFrame(main_frame, text="API Interfaces")
    list_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
    
    api_manage_listbox = tk.Listbox(list_frame, height=10)
    api_manage_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    api_manage_listbox.bind('<<ListboxSelect>>', load_interface_details)
    
    button_frame = ttk.Frame(list_frame)
    button_frame.pack(fill=tk.X, padx=5, pady=5)
    
    delete_button = ttk.Button(button_frame, text="Delete Selected", command=delete_interface)
    delete_button.pack(side=tk.LEFT, padx=5)
    
    clear_button = ttk.Button(button_frame, text="Clear Form", command=clear_form)
    clear_button.pack(side=tk.LEFT, padx=5)
    
    # Right side - Form
    form_frame = ttk.LabelFrame(main_frame, text="API Configuration")
    form_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
    
    # Name
    ttk.Label(form_frame, text="API Name:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
    name_entry = ttk.Entry(form_frame)
    name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
    
    # URL
    ttk.Label(form_frame, text="API URL:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
    url_entry = ttk.Entry(form_frame)
    url_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
    
    # API Key
    ttk.Label(form_frame, text="API Key:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
    api_key_entry = ttk.Entry(form_frame, show="*")
    api_key_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
    
    # API Type
    ttk.Label(form_frame, text="API Type:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
    api_type_var = tk.StringVar()
    api_type_dropdown = ttk.Combobox(form_frame, textvariable=api_type_var, 
                                   values=["OpenAI", "Ollama", "Groq", "Claude", "Google", "SearchEngine", "LMStudio"], 
                                   state="readonly")
    api_type_dropdown.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
    api_type_dropdown.bind("<<ComboboxSelected>>", on_api_type_change)
    
    # Fetch Models Button
    fetch_models_button = ttk.Button(form_frame, text="Fetch Available Models", 
                                   command=fetch_available_models)
    fetch_models_button.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
    
    # Model
    ttk.Label(form_frame, text="Model:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
    model_var = tk.StringVar()
    model_dropdown = ttk.Combobox(form_frame, textvariable=model_var, state="readonly")
    model_dropdown.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
    model_dropdown.bind("<<ComboboxSelected>>", update_pricing_match)

    pricing_status_var = tk.StringVar()
    pricing_status_label = ttk.Label(form_frame, textvariable=pricing_status_var, foreground="#6c757d")
    pricing_status_label.grid(row=6, column=1, padx=5, pady=(0, 5), sticky="w")
    
    # Max Tokens with Auto-Fetch
    max_tokens_frame = ttk.Frame(form_frame)
    max_tokens_frame.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
    
    ttk.Label(max_tokens_frame, text="Max Tokens:").pack(side=tk.LEFT)
    max_tokens_entry = ttk.Entry(max_tokens_frame)
    max_tokens_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    fetch_tokens_btn = ttk.Button(max_tokens_frame, text="Auto-Fetch", 
                                command=update_max_tokens)
    fetch_tokens_btn.pack(side=tk.LEFT, padx=5)
    
    # Save Button
    save_button = ttk.Button(form_frame, text="Add API Interface", command=save_new_interface)
    save_button.grid(row=8, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
    
    # Configure grid weights
    main_frame.columnconfigure(1, weight=1)
    main_frame.rowconfigure(0, weight=1)
    form_frame.columnconfigure(1, weight=1)
    
    # Initialize
    refresh_api_list()
    
    return main_frame
