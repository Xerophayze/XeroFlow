import subprocess
import sys
import re

# Function to install missing modules
def install_missing_modules(modules):
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            print(f"[ParseAndScrapeNode] Module '{module}' not found. Installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])

# Ensure required modules are installed
required_modules = ['requests', 'bs4']
install_missing_modules(required_modules)

import requests
from bs4 import BeautifulSoup

from .base_node import BaseNode
from node_registry import register_node

@register_node('ParseAndScrapeNode')
class ParseAndScrapeNode(BaseNode):
    """
    Parse and Scrape Node:
    - Parses URLs from the input text
    - Scrapes content from each URL
    - Replaces URLs in the original text with scraped content
    - Outputs the final combined text
    """

    def define_inputs(self):
        return ['input']  # Single input for the user prompt

    def define_outputs(self):
        return ['output']  # Output the processed text with scraped content

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'ParseAndScrapeNode'},
            'description': {'type': 'text', 'default': 'Parses URLs from input, scrapes their content, and replaces URLs with scraped text.'},
            'Prompt': {'type': 'textarea', 'default': ''},  # Optional additional prompt
            'max_content_length': {'type': 'number', 'default': 15000, 'description': 'Maximum characters to extract from each URL'},
            'timeout': {'type': 'number', 'default': 10, 'description': 'Timeout in seconds for each URL request'},
            'include_url_header': {'type': 'boolean', 'default': True, 'description': 'Include URL as header before scraped content'},
            'separator': {'type': 'text', 'default': '\n\n---\n\n', 'description': 'Separator between scraped content sections'},
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def extract_urls(self, text):
        """
        Extract all URLs from the given text.
        Returns a list of tuples: (url, start_position, end_position)
        """
        # Regular expression to match URLs
        url_pattern = re.compile(
            r'(?:http|https|ftp)s?://'  # http:// or https:// or ftp://
            r'(?:[a-zA-Z0-9$\-_@.&+!*\'(),]|%[0-9a-fA-F][0-9a-fA-F])+'  # Domain
            r'(?::[0-9]+)?'  # Optional port
            r'(?:/[^\s]*)?',  # Optional path
            re.IGNORECASE
        )
        
        urls = []
        for match in url_pattern.finditer(text):
            url = match.group(0)
            start = match.start()
            end = match.end()
            urls.append((url, start, end))
        
        return urls

    def scrape_url(self, url, max_length, timeout):
        """
        Scrape content from a single URL.
        Returns the scraped text or an error message.
        """
        try:
            print(f"[ParseAndScrapeNode] Scraping content from: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Limit length
            if len(text) > max_length:
                text = text[:max_length] + "... [Content truncated]"
            
            return text
            
        except requests.exceptions.Timeout:
            error_msg = f"[Timeout error: URL took longer than {timeout} seconds to respond]"
            print(f"[ParseAndScrapeNode] {error_msg}")
            return error_msg
            
        except requests.exceptions.RequestException as e:
            error_msg = f"[Error scraping URL: {str(e)}]"
            print(f"[ParseAndScrapeNode] {error_msg}")
            return error_msg
            
        except Exception as e:
            error_msg = f"[Unexpected error: {str(e)}]"
            print(f"[ParseAndScrapeNode] {error_msg}")
            return error_msg

    def process(self, inputs):
        """
        Main processing method:
        1. Get input text
        2. Parse URLs from the text
        3. Scrape content from each URL
        4. Replace URLs with scraped content
        5. Return the final text
        """
        print("[ParseAndScrapeNode] Starting process method.")

        # Retrieve properties and ensure correct types
        prompt = self.properties.get('Prompt', {}).get('default', '')
        max_length = int(self.properties.get('max_content_length', {}).get('default', 15000))
        timeout = int(self.properties.get('timeout', {}).get('default', 10))
        include_header = self.properties.get('include_url_header', {}).get('default', True)
        separator = self.properties.get('separator', {}).get('default', '\n\n---\n\n')

        # Get the input text
        user_input = inputs.get('input', '').strip()
        
        # Combine with prompt if provided
        if prompt:
            combined_text = f"{prompt}\n{user_input}"
        else:
            combined_text = user_input

        if not combined_text:
            print("[ParseAndScrapeNode] No input provided.")
            return {'output': ''}

        print(f"[ParseAndScrapeNode] Input text length: {len(combined_text)} characters")

        # Extract URLs from the text
        urls = self.extract_urls(combined_text)
        
        if not urls:
            print("[ParseAndScrapeNode] No URLs found in the input text.")
            return {'output': combined_text}

        print(f"[ParseAndScrapeNode] Found {len(urls)} URL(s) to scrape.")

        # Build the output text by replacing URLs with scraped content
        # Process URLs in reverse order to maintain correct positions
        result_text = combined_text
        
        for url, start_pos, end_pos in reversed(urls):
            print(f"[ParseAndScrapeNode] Processing URL: {url}")
            
            # Scrape the content
            scraped_content = self.scrape_url(url, max_length, timeout)
            
            # Format the replacement text
            if include_header:
                replacement = f"{separator}[Content from: {url}]\n\n{scraped_content}{separator}"
            else:
                replacement = f"{separator}{scraped_content}{separator}"
            
            # Replace the URL in the text
            result_text = result_text[:start_pos] + replacement + result_text[end_pos:]

        print(f"[ParseAndScrapeNode] Processing complete. Output length: {len(result_text)} characters")
        
        return {'output': result_text}

    def requires_api_call(self):
        return False  # No API call required, only web scraping
