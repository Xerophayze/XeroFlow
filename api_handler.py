# api_handler.py
import requests
from ollama import Client

def process_api_request(api_details, prompt):
    """
    Handles the actual API call given API details and a prompt.
    Returns a standardized response dictionary.
    """
    api_type = api_details.get('api_type', 'OpenAI')
    model = api_details.get('model')
    max_tokens = api_details.get('max_tokens', 100)

    if api_type == "OpenAI":
        api_url = api_details['url'].rstrip('/') + api_details['models_endpoint']
        headers = {
            'Authorization': f"Bearer {api_details.get('api_key', '')}",
            'Content-Type': 'application/json'
        }
        data = {
            'model': model,
            'messages': [{"role": "user", "content": prompt}],
            'max_tokens': max_tokens
        }
        try:
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()  # Keep the original structure for further handling
        except requests.RequestException as e:
            return {'error': f"OpenAI API Error: {str(e)}"}

    elif api_type == "Ollama":
        try:
            client = Client(host=api_details['url'])
            messages = [{"role": "user", "content": prompt}]
            response = client.chat(model=model, messages=messages)
            return response  # Assuming Ollama returns {'response': '...'}
        except Exception as e:
            return {'error': f"Ollama API Error: {str(e)}"}

    else:
        return {'error': f"Unsupported API type '{api_type}'."}
