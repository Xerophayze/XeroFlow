"""
Pricing Service for XeroFlow.
Contains pricing information for various API models.
"""

import json
import os

class PricingService:
    """Service for calculating costs based on token usage and model type"""
    
    # Default pricing information (February 2025 pricing)
    DEFAULT_PRICING = {
        # OpenAI Text Models
        "gpt-4o": {
            "input_per_million": 2.50,
            "output_per_million": 10.00,
            "provider": "openai"
        },
        "gpt-4o-2024-08-06": {
            "input_per_million": 2.50,
            "output_per_million": 10.00,
            "provider": "openai"
        },
        "gpt-4o-audio-preview": {
            "input_per_million": 2.50,
            "output_per_million": 10.00,
            "provider": "openai"
        },
        "gpt-4o-audio-preview-2024-12-17": {
            "input_per_million": 2.50,
            "output_per_million": 10.00,
            "provider": "openai"
        },
        "gpt-4o-realtime-preview": {
            "input_per_million": 5.00,
            "output_per_million": 20.00,
            "provider": "openai"
        },
        "gpt-4o-realtime-preview-2024-12-17": {
            "input_per_million": 5.00,
            "output_per_million": 20.00,
            "provider": "openai"
        },
        "gpt-4o-mini": {
            "input_per_million": 0.15,
            "output_per_million": 0.60,
            "provider": "openai"
        },
        "gpt-4o-mini-2024-07-18": {
            "input_per_million": 0.15,
            "output_per_million": 0.60,
            "provider": "openai"
        },
        "gpt-4o-mini-audio-preview": {
            "input_per_million": 0.15,
            "output_per_million": 0.60,
            "provider": "openai"
        },
        "gpt-4o-mini-audio-preview-2024-12-17": {
            "input_per_million": 0.15,
            "output_per_million": 0.60,
            "provider": "openai"
        },
        "gpt-4o-mini-realtime-preview": {
            "input_per_million": 0.60,
            "output_per_million": 2.40,
            "provider": "openai"
        },
        "gpt-4o-mini-realtime-preview-2024-12-17": {
            "input_per_million": 0.60,
            "output_per_million": 2.40,
            "provider": "openai"
        },
        "o1": {
            "input_per_million": 15.00,
            "output_per_million": 60.00,
            "provider": "openai"
        },
        "o1-2024-12-17": {
            "input_per_million": 15.00,
            "output_per_million": 60.00,
            "provider": "openai"
        },
        "o3-mini": {
            "input_per_million": 1.10,
            "output_per_million": 4.40,
            "provider": "openai"
        },
        "o3-mini-2025-01-31": {
            "input_per_million": 1.10,
            "output_per_million": 4.40,
            "provider": "openai"
        },
        "o1-mini": {
            "input_per_million": 1.10,
            "output_per_million": 4.40,
            "provider": "openai"
        },
        "o1-mini-2024-09-12": {
            "input_per_million": 1.10,
            "output_per_million": 4.40,
            "provider": "openai"
        },
        
        # OpenAI Audio Token Models
        "gpt-4o-audio-preview-audio": {
            "audio_input_per_million": 40.00,
            "audio_output_per_million": 80.00,
            "provider": "openai"
        },
        "gpt-4o-audio-preview-2024-12-17-audio": {
            "audio_input_per_million": 40.00,
            "audio_output_per_million": 80.00,
            "provider": "openai"
        },
        "gpt-4o-mini-audio-preview-audio": {
            "audio_input_per_million": 10.00,
            "audio_output_per_million": 20.00,
            "provider": "openai"
        },
        "gpt-4o-mini-audio-preview-2024-12-17-audio": {
            "audio_input_per_million": 10.00,
            "audio_output_per_million": 20.00,
            "provider": "openai"
        },
        "gpt-4o-realtime-preview-audio": {
            "audio_input_per_million": 40.00,
            "audio_output_per_million": 80.00,
            "provider": "openai"
        },
        "gpt-4o-realtime-preview-2024-12-17-audio": {
            "audio_input_per_million": 40.00,
            "audio_output_per_million": 80.00,
            "provider": "openai"
        },
        "gpt-4o-mini-realtime-preview-audio": {
            "audio_input_per_million": 10.00,
            "audio_output_per_million": 20.00,
            "provider": "openai"
        },
        "gpt-4o-mini-realtime-preview-2024-12-17-audio": {
            "audio_input_per_million": 10.00,
            "audio_output_per_million": 20.00,
            "provider": "openai"
        },
        
        # OpenAI Other Models
        "chatgpt-4o-latest": {
            "input_per_million": 5.00,
            "output_per_million": 15.00,
            "provider": "openai"
        },
        "gpt-4-turbo": {
            "input_per_million": 10.00,
            "output_per_million": 30.00,
            "provider": "openai"
        },
        "gpt-4-turbo-2024-04-09": {
            "input_per_million": 10.00,
            "output_per_million": 30.00,
            "provider": "openai"
        },
        "gpt-4": {
            "input_per_million": 30.00,
            "output_per_million": 60.00,
            "provider": "openai"
        },
        "gpt-4-0613": {
            "input_per_million": 30.00,
            "output_per_million": 60.00,
            "provider": "openai"
        },
        "gpt-4-32k": {
            "input_per_million": 60.00,
            "output_per_million": 120.00,
            "provider": "openai"
        },
        "gpt-3.5-turbo": {
            "input_per_million": 0.50,
            "output_per_million": 1.50,
            "provider": "openai"
        },
        "gpt-3.5-turbo-0125": {
            "input_per_million": 0.50,
            "output_per_million": 1.50,
            "provider": "openai"
        },
        "gpt-3.5-turbo-instruct": {
            "input_per_million": 1.50,
            "output_per_million": 2.00,
            "provider": "openai"
        },
        "gpt-3.5-turbo-16k-0613": {
            "input_per_million": 3.00,
            "output_per_million": 4.00,
            "provider": "openai"
        },
        "davinci-002": {
            "input_per_million": 2.00,
            "output_per_million": 2.00,
            "provider": "openai"
        },
        "babbage-002": {
            "input_per_million": 0.40,
            "output_per_million": 0.40,
            "provider": "openai"
        },
        
        # OpenAI Embeddings
        "text-embedding-3-small": {
            "input_per_million": 0.02,
            "output_per_million": 0.02,
            "provider": "openai"
        },
        "text-embedding-3-large": {
            "input_per_million": 0.13,
            "output_per_million": 0.13,
            "provider": "openai"
        },
        "text-embedding-ada-002": {
            "input_per_million": 0.10,
            "output_per_million": 0.10,
            "provider": "openai"
        },
        
        # OpenAI Speech/Audio Models
        "whisper-1": {
            "per_minute": 0.006,
            "provider": "openai"
        },
        "tts-1": {
            "per_million_chars": 15.00,
            "provider": "openai"
        },
        "tts-1-hd": {
            "per_million_chars": 30.00,
            "provider": "openai"
        },
        
        # Groq Models - LLMs
        "deepseek-r1-distill-llama-70b": {
            "input_per_million": 0.75,
            "output_per_million": 0.99,
            "provider": "groq"
        },
        "deepseek-r1-distill-qwen-32b": {
            "input_per_million": 0.69,
            "output_per_million": 0.69,
            "provider": "groq"
        },
        "qwen-2.5-32b-instruct": {
            "input_per_million": 0.79,
            "output_per_million": 0.79,
            "provider": "groq"
        },
        "qwen-2.5-coder-32b-instruct": {
            "input_per_million": 0.79,
            "output_per_million": 0.79,
            "provider": "groq"
        },
        "mistral-saba-24b": {
            "input_per_million": 0.79,
            "output_per_million": 0.79,
            "provider": "groq"
        },
        "llama-3.2-1b": {
            "input_per_million": 0.04,
            "output_per_million": 0.04,
            "provider": "groq"
        },
        "llama-3.2-3b": {
            "input_per_million": 0.06,
            "output_per_million": 0.06,
            "provider": "groq"
        },
        "llama-3.3-70b-versatile": {
            "input_per_million": 0.59,
            "output_per_million": 0.79,
            "provider": "groq"
        },
        "llama-3.1-8b-instant": {
            "input_per_million": 0.05,
            "output_per_million": 0.08,
            "provider": "groq"
        },
        "llama-3-70b": {
            "input_per_million": 0.59,
            "output_per_million": 0.79,
            "provider": "groq"
        },
        "llama-3-8b": {
            "input_per_million": 0.05,
            "output_per_million": 0.08,
            "provider": "groq"
        },
        "mixtral-8x7b-instruct": {
            "input_per_million": 0.24,
            "output_per_million": 0.24,
            "provider": "groq"
        },
        "gemma-2-9b": {
            "input_per_million": 0.20,
            "output_per_million": 0.20,
            "provider": "groq"
        },
        "llama-guard-3-8b": {
            "input_per_million": 0.20,
            "output_per_million": 0.20,
            "provider": "groq"
        },
        "llama-3.3-70b-specdec": {
            "input_per_million": 0.59,
            "output_per_million": 0.99,
            "provider": "groq"
        },
        
        # Groq Models - ASR
        "whisper-v3-large": {
            "per_minute": 0.00185,  # $0.111 per hour / 60
            "provider": "groq"
        },
        "whisper-v3-turbo": {
            "per_minute": 0.00067,  # $0.04 per hour / 60
            "provider": "groq"
        },
        "distil-whisper": {
            "per_minute": 0.00033,  # $0.02 per hour / 60
            "provider": "groq"
        },
        
        # Groq Models - Vision
        "llama-3.2-11b-vision": {
            "input_per_million": 0.18,
            "output_per_million": 0.18,
            "provider": "groq"
        },
        "llama-3.2-90b-vision": {
            "input_per_million": 0.90,
            "output_per_million": 0.90,
            "provider": "groq"
        }
    }
    
    # Path to the custom pricing configuration file
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                             "config", "pricing_config.json")
    CURRENT_PRICING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "current-v1.json")
    
    # Current pricing data (will be loaded from config or defaults)
    _pricing_data = None
    
    @classmethod
    def _ensure_config_dir(cls):
        """Ensure the config directory exists"""
        config_dir = os.path.dirname(cls.CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

    @classmethod
    def _load_current_pricing_file(cls):
        """Load pricing data from current-v1.json if available."""
        if not os.path.exists(cls.CURRENT_PRICING_FILE):
            return {}

        try:
            with open(cls.CURRENT_PRICING_FILE, 'r') as f:
                data = json.load(f)

            pricing_data = {}
            for entry in data.get("prices", []):
                model_id = entry.get("id")
                input_cost = entry.get("input")
                output_cost = entry.get("output")
                provider = entry.get("vendor")

                if not model_id or input_cost is None or output_cost is None:
                    continue

                model_pricing = {
                    "input_per_million": float(input_cost),
                    "output_per_million": float(output_cost),
                    "provider": provider
                }
                input_cached = entry.get("input_cached")
                if input_cached is not None:
                    model_pricing["input_cached_per_million"] = float(input_cached)

                pricing_data[model_id] = model_pricing

            return pricing_data
        except Exception:
            return {}

    @staticmethod
    def normalize_model_name(model):
        """Normalize model identifiers to improve pricing lookups."""
        if not model:
            return model

        normalized = model.strip()
        if normalized.startswith("models/"):
            normalized = normalized.split("/", 1)[1]

        if "/" in normalized:
            normalized = normalized.split("/")[-1]

        return normalized

    @classmethod
    def _lookup_model_pricing(cls, pricing_data, model):
        if not model:
            return {}

        model_pricing = pricing_data.get(model, {})
        if model_pricing:
            return model_pricing

        normalized = cls.normalize_model_name(model)
        if normalized != model:
            return pricing_data.get(normalized, {})

        return {}
    
    @classmethod
    def load_pricing_data(cls):
        """Load pricing data from config file or use defaults"""
        if cls._pricing_data is not None:
            return cls._pricing_data

        try:
            current_pricing = cls._load_current_pricing_file()
            if current_pricing:
                config_exists = os.path.exists(cls.CONFIG_FILE)
                current_mtime = os.path.getmtime(cls.CURRENT_PRICING_FILE)
                config_mtime = os.path.getmtime(cls.CONFIG_FILE) if config_exists else 0

                if not config_exists or current_mtime >= config_mtime:
                    merged_pricing = dict(cls.DEFAULT_PRICING)
                    merged_pricing.update(current_pricing)
                    cls._pricing_data = merged_pricing
                    cls.save_pricing_data()
                    return cls._pricing_data

            if os.path.exists(cls.CONFIG_FILE):
                with open(cls.CONFIG_FILE, 'r') as f:
                    cls._pricing_data = json.load(f)
            else:
                cls._pricing_data = cls.DEFAULT_PRICING
                cls.save_pricing_data()  # Save defaults to file
        except Exception:
            cls._pricing_data = cls.DEFAULT_PRICING
            
        return cls._pricing_data
    
    @classmethod
    def save_pricing_data(cls):
        """Save current pricing data to config file"""
        cls._ensure_config_dir()
        with open(cls.CONFIG_FILE, 'w') as f:
            json.dump(cls._pricing_data, f, indent=4)
    
    @classmethod
    def get_model_pricing(cls, model):
        """Get pricing information for a specific model"""
        pricing_data = cls.load_pricing_data()
        return cls._lookup_model_pricing(pricing_data, model)
    
    @classmethod
    def update_model_pricing(cls, model, input_cost=None, output_cost=None, per_minute=None, 
                           per_million_chars=None, audio_input_cost=None, audio_output_cost=None):
        """Update pricing for a specific model"""
        pricing_data = cls.load_pricing_data()
        
        if model not in pricing_data:
            return False
            
        if input_cost is not None:
            pricing_data[model]["input_per_million"] = input_cost
            
        if output_cost is not None:
            pricing_data[model]["output_per_million"] = output_cost
            
        if per_minute is not None:
            pricing_data[model]["per_minute"] = per_minute
            
        if per_million_chars is not None:
            pricing_data[model]["per_million_chars"] = per_million_chars
            
        if audio_input_cost is not None:
            pricing_data[model]["audio_input_per_million"] = audio_input_cost
            
        if audio_output_cost is not None:
            pricing_data[model]["audio_output_per_million"] = audio_output_cost
            
        cls._pricing_data = pricing_data
        cls.save_pricing_data()
        return True
    
    @classmethod
    def get_all_models(cls):
        """Get a list of all available models"""
        pricing_data = cls.load_pricing_data()
        return list(pricing_data.keys())
    
    @classmethod
    def get_models_by_provider(cls, provider):
        """Get a list of models for a specific provider"""
        pricing_data = cls.load_pricing_data()
        models = [model for model, data in pricing_data.items() 
                if data.get("provider") == provider]
        # Sort models alphabetically for easier selection
        return sorted(models)

    @classmethod
    def get_providers(cls):
        """Get a list of available providers."""
        pricing_data = cls.load_pricing_data()
        providers = {data.get("provider") for data in pricing_data.values() if data.get("provider")}
        return sorted(providers)
    
    @classmethod
    def get_text_model_cost(cls, model, input_tokens, output_tokens):
        """Calculate cost for text model usage"""
        pricing_data = cls.load_pricing_data()
        model_pricing = cls._lookup_model_pricing(pricing_data, model)
        
        # Default to GPT-3.5-Turbo pricing if model not found
        if not model_pricing:
            model_pricing = pricing_data.get("gpt-3.5-turbo", {
                "input_per_million": 0.50,
                "output_per_million": 1.50
            })
        
        input_cost_per_million = model_pricing.get("input_per_million", 0)
        output_cost_per_million = model_pricing.get("output_per_million", 0)
        
        input_cost = (input_tokens / 1000000) * input_cost_per_million
        output_cost = (output_tokens / 1000000) * output_cost_per_million
        total_cost = input_cost + output_cost
        
        return input_cost, output_cost, total_cost
    
    @classmethod
    def get_whisper_cost(cls, duration_seconds):
        """Calculate cost for Whisper audio transcription"""
        pricing_data = cls.load_pricing_data()
        model_pricing = pricing_data.get("whisper-1", {})
        
        # Default pricing if not found
        per_minute_cost = model_pricing.get("per_minute", 0.006)
        
        # Convert seconds to minutes and calculate cost
        minutes = duration_seconds / 60
        cost = minutes * per_minute_cost
        
        return cost
    
    @classmethod
    def get_tts_cost(cls, model, character_count):
        """Calculate cost for TTS (Text-to-Speech) models"""
        pricing_data = cls.load_pricing_data()
        model_pricing = pricing_data.get(model, {})
        
        # Default pricing if not found
        per_million_chars_cost = model_pricing.get("per_million_chars", 15.00)  # Default to standard TTS pricing
        
        # Calculate cost based on character count
        cost = (character_count / 1000000) * per_million_chars_cost
        
        return cost
        
    @classmethod
    def get_audio_token_cost(cls, model, input_tokens, output_tokens):
        """Calculate cost for audio token model usage (special audio token rates)"""
        pricing_data = cls.load_pricing_data()
        model_pricing = pricing_data.get(model, {})
        
        # Default to GPT-4o audio pricing if model not found
        if not model_pricing:
            model_pricing = pricing_data.get("gpt-4o-audio-preview-audio", {
                "audio_input_per_million": 40.00,
                "audio_output_per_million": 80.00
            })
        
        input_cost_per_million = model_pricing.get("audio_input_per_million", 0)
        output_cost_per_million = model_pricing.get("audio_output_per_million", 0)
        
        input_cost = (input_tokens / 1000000) * input_cost_per_million
        output_cost = (output_tokens / 1000000) * output_cost_per_million
        total_cost = input_cost + output_cost
        
        return input_cost, output_cost, total_cost
    
    @classmethod
    def refresh_pricing_data(cls):
        """Reset the pricing data cache and reload from defaults"""
        cls._pricing_data = None
        return cls.load_pricing_data()
