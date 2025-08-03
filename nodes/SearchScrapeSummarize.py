import subprocess
import sys
import re
import tkinter as tk
from tkinter import messagebox

# Function to install missing modules
def install_missing_modules(modules):
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            print(f"[SearchScrapeSummarizeNode] Module '{module}' not found. Installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])

# Ensure required modules are installed
required_modules = ['requests', 'bs4']
install_missing_modules(required_modules)

import requests
from bs4 import BeautifulSoup

from .base_node import BaseNode
from node_registry import register_node
from api_handler import process_api_request

@register_node('SearchScrapeSummarizeNode')
class SearchScrapeSummarizeNode(BaseNode):

    def define_inputs(self):
        return ['input']  # 'input' will be used for the user input

    def define_outputs(self):
        return ['prompt']  # Output the processed and summarized web search results

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'SearchScrapeSummarizeNode'},
            'description': {'type': 'text', 'default': 'Processes the input for web search, scraping, and summarization via API.'},
            'Prompt': {'type': 'textarea', 'default': ''},  # User-defined prompt
            'api_endpoint': {
                'type': 'dropdown',
                'label': 'API Endpoint',
                'options': self.get_api_endpoints(),
                'default': self.get_api_endpoints()[0] if self.get_api_endpoints() else ''
            },
            'num_search_results': {'type': 'number', 'default': 5},
            'num_results_to_skip': {'type': 'number', 'default': 0},
            'enable_web_search': {'type': 'boolean', 'default': True, 'description': 'Enable Web Search'},
            'enable_url_selection': {'type': 'boolean', 'default': False, 'description': 'Enable URL Selection'},
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def get_api_endpoints(self):
        # Retrieve API endpoint names from the configuration
        interfaces = self.config.get('interfaces', {})
        if interfaces is None:
            interfaces = {}
        api_list = list(interfaces.keys())
        print(f"[SearchScrapeSummarizeNode] Available API endpoints: {api_list}")
        return api_list

    def get_summarization_prompt(self, query, content):
        """Create a prompt for summarizing the scraped content."""
        return f"Please summarize the important details from the following information, keep it well formatted using proper markdown formatting, but include all relevant information, links, references, number and data relevant data: {query}\n\nScraped Content:\n{content}"

    def send_to_summarization_api(self, prompt):
        """Send the prompt to the selected API endpoint."""
        selected_api = self.properties.get('api_endpoint', {}).get('value') or self.properties.get('api_endpoint', {}).get('default', '')
        if not selected_api:
            print("[SearchScrapeSummarizeNode] No API endpoint selected.")
            return "No API endpoint selected."

        api_details = self.config['interfaces'].get(selected_api, {})
        if not api_details:
            print("[SearchScrapeSummarizeNode] API details not found for the selected endpoint.")
            return "API details not found for the selected endpoint."

        # Create request data dictionary
        request_data = {
            "prompt": prompt,
            "messages": [{"role": "user", "content": prompt}]
        }

        api_details = self.config['interfaces'].get(selected_api, {})
        model = api_details.get('selected_model')

        try:
            # Send the prompt to the API using the standard method
            print(f"[SearchScrapeSummarizeNode] Sending summarization request to {selected_api} with model {model}")
            api_response = self.send_api_request(prompt, selected_api, model=model)

            if api_response.success:
                summary = api_response.content
            else:
                print(f"[SearchScrapeSummarizeNode] API request failed: {api_response.error}")
                summary = f"Error during summarization: {api_response.error}"

            
        except Exception as e:
            print(f"[SearchScrapeSummarizeNode] Error sending prompt to API: {str(e)}")
            return f"Error sending prompt to API: {str(e)}"

    def perform_search(self, query, searxng_api_url, num_results, num_results_to_skip):
        """Perform a search using the SearxNG API."""
        # Ensure num_results and num_results_to_skip are integers
        try:
            num_results = int(num_results)
        except (ValueError, TypeError):
            print("[SearchScrapeSummarizeNode] Invalid num_results, using default of 3")
            num_results = 3
            
        try:
            num_results_to_skip = int(num_results_to_skip)
        except (ValueError, TypeError):
            print("[SearchScrapeSummarizeNode] Invalid num_results_to_skip, using default of 0")
            num_results_to_skip = 0
            
        params = {
            'q': query,  # Using raw user input for search
            'format': 'json',
            'pageno': 1,
            'language': 'en',
            'results': num_results + num_results_to_skip
        }
        
        print(f"[SearchScrapeSummarizeNode] Search params: {params}")

        try:
            print(f"[SearchScrapeSummarizeNode] Sending request to SearxNG API at {searxng_api_url}")
            response = requests.get(searxng_api_url, params=params)
            print(f"[SearchScrapeSummarizeNode] SearxNG API response status: {response.status_code}")
            response.raise_for_status()  # Raise an exception for HTTP errors
        except requests.exceptions.RequestException as e:
            print(f"[SearchScrapeSummarizeNode] SearxNG API Error: {e}")
            return []

        try:
            json_response = response.json()
            print(f"[SearchScrapeSummarizeNode] SearxNG API response: {json_response.keys()}")
            search_results = json_response.get('results', [])
            print(f"[SearchScrapeSummarizeNode] Found {len(search_results)} search results")
        except ValueError:
            print("[SearchScrapeSummarizeNode] Invalid JSON response from SearxNG API.")
            return []

        # Filter out PDF files
        filtered_results = [
            result for result in search_results 
            if not result.get('url', '').lower().endswith('.pdf') and 
            not result.get('title', '').lower().endswith('.pdf')
        ]
        
        print(f"[SearchScrapeSummarizeNode] After filtering PDFs: {len(filtered_results)} results")

        # Skip and limit results
        search_results = filtered_results[num_results_to_skip:num_results_to_skip + num_results]
        print(f"[SearchScrapeSummarizeNode] Final results after skip/limit: {len(search_results)}")
        
        # Log the URLs of the search results
        for i, result in enumerate(search_results):
            print(f"[SearchScrapeSummarizeNode] Result {i+1}: {result.get('url')} - {result.get('title')}")

        return search_results

    def scrape_content(self, search_results):
        """Scrape content from the search results."""
        scraped_content = []
        for i, result in enumerate(search_results):
            url = result.get('url')
            title = result.get('title', 'No title')
            print(f"[SearchScrapeSummarizeNode] [{i+1}/{len(search_results)}] Scraping content from: {url} - {title}")
            try:
                print(f"[SearchScrapeSummarizeNode] Sending GET request to {url}")
                # Use a shorter timeout to prevent long delays
                page = requests.get(url, timeout=5, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
                print(f"[SearchScrapeSummarizeNode] Response status: {page.status_code}")
                
                if page.status_code != 200:
                    print(f"[SearchScrapeSummarizeNode] Failed to get content from {url}: HTTP {page.status_code}")
                    scraped_content.append(f"Content from {url}: Unable to retrieve content (HTTP {page.status_code})")
                    continue
                    
                soup = BeautifulSoup(page.content, 'html.parser')
                
                # Try to get the main content
                main_content = None
                for tag in ['article', 'main', 'div.content', 'div.main', 'div.article']:
                    content = soup.select(tag)
                    if content:
                        main_content = content[0]
                        print(f"[SearchScrapeSummarizeNode] Found main content using selector: {tag}")
                        break
                
                # If no main content found, use the whole page
                if not main_content:
                    main_content = soup
                    print(f"[SearchScrapeSummarizeNode] Using whole page content")
                
                text = main_content.get_text(separator=' ', strip=True)
                
                # Truncate text if it's too long
                if len(text) > 5000:
                    print(f"[SearchScrapeSummarizeNode] Truncating content from {len(text)} to 5000 characters")
                    text = text[:5000] + "..."
                else:
                    print(f"[SearchScrapeSummarizeNode] Content length: {len(text)} characters")
                
                scraped_content.append(f"Content from {url}:\n{text}\n")
            except requests.exceptions.Timeout:
                print(f"[SearchScrapeSummarizeNode] Timeout while scraping {url}")
                scraped_content.append(f"Content from {url}: Request timed out after 5 seconds")
            except requests.exceptions.RequestException as e:
                print(f"[SearchScrapeSummarizeNode] Request error while processing {url}: {e}")
                scraped_content.append(f"Content from {url}: Request error - {str(e)}")
            except Exception as e:
                print(f"[SearchScrapeSummarizeNode] Error processing {url}: {e}")
                scraped_content.append(f"Content from {url}: Error - {str(e)}")

        combined_content = "\n".join(scraped_content)
        print(f"[SearchScrapeSummarizeNode] Total scraped content length: {len(combined_content)} characters")
        return combined_content

    def process(self, data):
        """Process the input data."""
        print("[SearchScrapeSummarizeNode] Starting process method.")
        
        # Get the input data
        input_data = data.get('input', '')
        if not input_data:
            print("[SearchScrapeSummarizeNode] Error: No input provided.")
            return {"prompt": "No search query provided."}
        
        # Get the API endpoint
        api_endpoint_name = self.properties.get('api_endpoint', {}).get('value') or self.properties.get('api_endpoint', {}).get('default', '')
        if api_endpoint_name:
            print(f"[SearchScrapeSummarizeNode] Using API endpoint: {api_endpoint_name}")
        else:
            print("[SearchScrapeSummarizeNode] Warning: No API endpoint specified")
            return {"prompt": "No API endpoint specified for search summarization."}
        
        # Log the search query
        print(f"[SearchScrapeSummarizeNode] Searching for: {input_data}")
        
        # Check if web search is enabled
        if not self.properties.get('enable_web_search', {}).get('default', True):
            print("[SearchScrapeSummarizeNode] Error: Web search is disabled.")
            return {"prompt": "Web search functionality is currently disabled."}
        
        # Get the number of search results to return
        try:
            num_search_results = int(self.properties.get('num_search_results', {}).get('default', 3))
        except (ValueError, TypeError):
            print("[SearchScrapeSummarizeNode] Invalid num_search_results, using default of 3")
            num_search_results = 3
            
        try:
            num_results_to_skip = int(self.properties.get('num_results_to_skip', {}).get('default', 0))
        except (ValueError, TypeError):
            print("[SearchScrapeSummarizeNode] Invalid num_results_to_skip, using default of 0")
            num_results_to_skip = 0
        
        # Find the configured SearxNG endpoint URL
        searxng_api_url = None
        for name, config in self.config.get('interfaces', {}).items():
            if config.get('type', '').lower() == 'searchengine':
                searxng_api_url = config.get('api_url')
                if searxng_api_url:
                    break

        if not searxng_api_url:
            print("[SearchScrapeSummarizeNode] Error: No SearchEngine (SearxNG) API endpoint configured or URL is missing.")
            return {"prompt": "Error: No SearchEngine (SearxNG) API endpoint configured or URL is missing."}
        
        # Perform the search
        print(f"[SearchScrapeSummarizeNode] Sending search request to SearxNG API at {searxng_api_url} with {num_search_results} results")
        search_results = self.perform_search(input_data, searxng_api_url, num_search_results, num_results_to_skip)
        
        if not search_results:
            print("[SearchScrapeSummarizeNode] Error: No search results found.")
            # Return a helpful message instead of an error
            return {"prompt": f"I searched the web for information about '{input_data}' but couldn't find any relevant results. The search service may be unavailable or there might be no matching content. Please try a different search query or try again later."}
        
        # Scrape the content from the search results
        scraped_content = self.scrape_content(search_results)
        
        if not scraped_content:
            print("[SearchScrapeSummarizeNode] Error: Failed to scrape content from search results.")
            # Return a message with the search results even if scraping failed
            urls = [f"{i+1}. {result.get('title', 'No title')}: {result.get('url')}" 
                   for i, result in enumerate(search_results)]
            url_list = "\n".join(urls)
            return {"prompt": f"I found some web pages about '{input_data}', but I couldn't extract their content. Here are the links I found:\n\n{url_list}"}
        
        # Summarize the content
        summarization_prompt = self.get_summarization_prompt(input_data, scraped_content)
        
        summary = self.send_to_summarization_api(summarization_prompt)
        
        if not summary or summary == "API response is None.":
            # If summarization fails, return the scraped content directly
            print("[SearchScrapeSummarizeNode] Summarization failed. Returning scraped content directly.")
            # Truncate the content if it's too long
            truncated_content = scraped_content
            if len(truncated_content) > 2000:
                truncated_content = truncated_content[:2000] + "..."
            return {"prompt": f"Here are some search results for '{input_data}':\n\n{truncated_content}"}
        
        return {"prompt": summary}

    def requires_api_call(self):
        return True  # Set to True since this node makes API calls
