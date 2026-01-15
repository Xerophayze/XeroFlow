import requests
from .base_node import BaseNode
from node_registry import register_node

@register_node('WebSearchNode')
class WebSearchNode(BaseNode):

    def define_inputs(self):
        return ['input']  # User input for search query

    def define_outputs(self):
        return ['urls']  # Output the list of URLs

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'WebSearchNode'},
            'description': {'type': 'text', 'default': 'Performs web search and returns URLs only.'},
            'search_query': {'type': 'textarea', 'default': ''},  # User-defined search query
            'searxng_api_url': {'type': 'text', 'default': 'http://localhost:8888/search'},  # API URL for SearxNG
            'num_search_results': {'type': 'number', 'default': 5},  # Number of results to retrieve
            'num_results_to_skip': {'type': 'number', 'default': 0}  # Results to skip
        })
        return props

    def process(self, inputs):
        print("[WebSearchNode] Starting web search process.")

        # Retrieve properties and cast them to integers
        search_query = self.properties.get('search_query', {}).get('default', '')
        searxng_api_url = self.properties.get('searxng_api_url', {}).get('default', 'http://localhost:8888/search')
        
        # Ensure the num_results and num_results_to_skip are integers
        try:
            num_results = int(self.properties.get('num_search_results', {}).get('default', 5))
            num_results_to_skip = int(self.properties.get('num_results_to_skip', {}).get('default', 0))
        except ValueError:
            print("[WebSearchNode] num_results or num_results_to_skip is not a valid integer.")
            return {'urls': 'Error: num_results or num_results_to_skip is not a valid integer.'}

        # Use user input as search query if provided
        user_input = inputs.get('input', '').strip()
        query = f"{search_query}\n{user_input}" if user_input else search_query

        if not query.strip():
            print("[WebSearchNode] No query provided.")
            return {'urls': 'Error: No query provided.'}

        # Prepare search parameters for API request
        params = {
            'q': query,
            'format': 'json',
            'pageno': 1,
            'language': 'en',
            'n': num_results + num_results_to_skip
        }

        response = requests.get(searxng_api_url, params=params)
        if response.status_code != 200:
            print(f"[WebSearchNode] SearxNG API Error: {response.status_code}")
            return {'urls': f'Error: SearxNG API returned status {response.status_code}'}

        search_results = response.json().get('results', [])
        
        # Slice results using integer indices
        search_results = search_results[num_results_to_skip:num_results_to_skip + num_results]
        
        # Extract URLs and join them into a single string with each URL on a new line
        urls = [result.get('url') for result in search_results if 'url' in result]
        urls_string = '\n'.join(urls)
        print(f"[WebSearchNode] Retrieved URLs:\n{urls_string}")

        return {'urls': urls_string}  # Return combined URLs as a single string
