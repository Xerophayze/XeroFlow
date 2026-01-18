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
            print(f"[SearchAndScrapeNode] Module '{module}' not found. Installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])

# Ensure required modules are installed
required_modules = ['requests', 'bs4']  # List all required modules here
install_missing_modules(required_modules)

import requests
from bs4 import BeautifulSoup

from .base_node import BaseNode
from src.workflows.node_registry import register_node

@register_node('SearchAndScrapeNode')
class SearchAndScrapeNode(BaseNode):

    def define_inputs(self):
        return ['input']  # 'input' will be used for the user input

    def define_outputs(self):
        return ['output']  # Output the processed web search results or scraped content

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'SearchAndScrapeNode'},
            'description': {'type': 'text', 'default': 'Processes the input for web search and scraping.'},
            'Prompt': {'type': 'textarea', 'default': ''},  # User-defined prompt
            'searxng_api_url': {'type': 'text', 'default': 'http://localhost:8888/search'},  # User-specified SearxNG API URL
            'num_search_results': {'type': 'number', 'default': 5},  # User-specified number of search results
            'num_results_to_skip': {'type': 'number', 'default': 0},  # User-specified number of search results to skip
            'enable_web_search': {'type': 'boolean', 'default': True, 'description': 'Enable Web Search'},  # Checkbox to enable/disable web search
            'enable_url_selection': {'type': 'boolean', 'default': False, 'description': 'Enable URL Selection'},  # Checkbox to enable URL selection
            'is_start_node': {'type': 'boolean', 'default': False},
            'is_end_node': {'type': 'boolean', 'default': False}
        })
        return props

    def process(self, inputs):
        print("[SearchAndScrapeNode] Starting process method.")

        # Retrieve properties
        prompt = self.properties.get('Prompt', {}).get('default', '')
        searxng_api_url = self.properties.get('searxng_api_url', {}).get('default', 'http://localhost:8888/search')
        num_results = self.properties.get('num_search_results', {}).get('default', 5)
        num_results_to_skip = self.properties.get('num_results_to_skip', {}).get('default', 0)
        enable_web_search = self.properties.get('enable_web_search', {}).get('default', True)
        enable_url_selection = self.properties.get('enable_url_selection', {}).get('default', False)

        # Use the input provided by the user
        user_input = inputs.get('input', '').strip()

        # Append the initial input to the end of the prompt
        combined_prompt = f"{prompt}\n{user_input}" if user_input else prompt

        # If web search is enabled
        if enable_web_search:
            if not combined_prompt.strip():
                print("[SearchAndScrapeNode] No input provided for the web search.")
                return {'output': 'Error: No input provided for the web search.'}

            # Perform a web search using SearxNG API
            params = {
                'q': combined_prompt,  # Use the combined prompt as the search query
                'format': 'json',   # Requesting JSON format
                'pageno': 1,
                'language': 'en',
                'n': num_results + num_results_to_skip  # Retrieve more results in case some need to be skipped
            }

            print(f"[SearchAndScrapeNode] Sending search request to SearxNG API at {searxng_api_url} with query: {combined_prompt}")
            response = requests.get(searxng_api_url, params=params)
            if response.status_code != 200:
                print(f"[SearchAndScrapeNode] SearxNG API Error: {response.status_code}")
                return {'output': f'Error: SearxNG API returned status {response.status_code}'}

            search_results = response.json().get('results', [])
            print(f"[SearchAndScrapeNode] SearxNG returned {len(search_results)} results.")

            # Ensure num_results and num_results_to_skip are integers
            try:
                num_results = int(num_results)
                num_results_to_skip = int(num_results_to_skip)
            except ValueError:
                print("[SearchAndScrapeNode] Error: num_results or num_results_to_skip is not a valid integer.")
                return {'output': 'Error: num_results or num_results_to_skip is not a valid integer.'}

            # Skip the specified number of results, then take the next num_results results
            search_results = search_results[num_results_to_skip:num_results_to_skip + num_results]
            print(f"[SearchAndScrapeNode] Skipping the first {num_results_to_skip} results and limiting to the next {num_results} results.")

            # If URL selection is enabled, show the list of URLs and let the user select
            if enable_url_selection:
                urls = [result.get('url') for result in search_results]
                print("[SearchAndScrapeNode] URL selection is enabled. Displaying selection window.")

                # Function to get user-selected URLs
                def get_user_selected_urls(urls):
                    selected_urls = []

                    def on_ok():
                        selected_indices = listbox.curselection()
                        for index in selected_indices:
                            selected_urls.append(urls[index])
                        root.destroy()

                    def on_cancel():
                        root.destroy()
                        raise Exception("User cancelled the URL selection.")

                    root = tk.Tk()
                    root.title("Select URLs to Scrape")

                    frame = tk.Frame(root)
                    frame.pack(fill=tk.BOTH, expand=True)

                    scrollbar = tk.Scrollbar(frame)
                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                    listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE)
                    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                    for url in urls:
                        listbox.insert(tk.END, url)

                    listbox.config(yscrollcommand=scrollbar.set)
                    scrollbar.config(command=listbox.yview)

                    button_frame = tk.Frame(root)
                    button_frame.pack(fill=tk.X)

                    ok_button = tk.Button(button_frame, text="OK", command=on_ok)
                    ok_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel)
                    cancel_button.pack(side=tk.RIGHT, fill=tk.X, expand=True)

                    root.mainloop()
                    return selected_urls

                try:
                    selected_urls = get_user_selected_urls(urls)
                except Exception as e:
                    print(f"[SearchAndScrapeNode] {str(e)}")
                    return {'output': f'Error: {str(e)}'}

                if not selected_urls:
                    print("[SearchAndScrapeNode] No URLs selected.")
                    return {'output': 'Error: No URLs selected.'}

                # Now scrape the selected URLs
                combined_text = ''
                for url in selected_urls:
                    print(f"[SearchAndScrapeNode] Scraping content from: {url}")
                    try:
                        page = requests.get(url, timeout=5)
                        soup = BeautifulSoup(page.content, 'html.parser')
                        text = soup.get_text(separator=' ', strip=True)
                        combined_text += text + "\n\n"
                    except Exception as e:
                        print(f"[SearchAndScrapeNode] Error scraping {url}: {e}")

                print("[SearchAndScrapeNode] Completed web scraping. Returning combined text.")
                return {'output': combined_text}  # Return the combined scraped text as the output

            else:
                # Scrape the content of each URL
                combined_text = ''
                for result in search_results:
                    url = result.get('url')
                    print(f"[SearchAndScrapeNode] Scraping content from: {url}")
                    try:
                        page = requests.get(url, timeout=5)
                        soup = BeautifulSoup(page.content, 'html.parser')
                        text = soup.get_text(separator=' ', strip=True)
                        combined_text += text + "\n\n"
                    except Exception as e:
                        print(f"[SearchAndScrapeNode] Error scraping {url}: {e}")

                print("[SearchAndScrapeNode] Completed web scraping. Returning combined text.")
                return {'output': combined_text}  # Return the combined scraped text as the output

        else:
            # Web search is disabled, check if input contains URLs or list of URLs separated by commas
            urls = [url.strip() for url in user_input.split(',') if url.strip()]
            valid_urls = []

            # Regular expression to check for valid URLs
            url_regex = re.compile(
                r'^(?:http|ftp)s?://'  # http:// or https:// or ftp://
                r'(?:\S+)?'  # Domain name and possibly other components
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)

            for url in urls:
                if re.match(url_regex, url):
                    valid_urls.append(url)
                else:
                    print(f"[SearchAndScrapeNode] Invalid URL detected and skipped: {url}")

            if not valid_urls:
                print("[SearchAndScrapeNode] No valid URLs provided for scraping.")
                return {'output': 'Error: No valid URLs provided for scraping.'}

            # Scrape the content of each valid URL
            combined_text = ''
            for url in valid_urls:
                print(f"[SearchAndScrapeNode] Scraping content from: {url}")
                try:
                    page = requests.get(url, timeout=5)
                    soup = BeautifulSoup(page.content, 'html.parser')
                    text = soup.get_text(separator=' ', strip=True)
                    combined_text += text + "\n\n"
                except Exception as e:
                    print(f"[SearchAndScrapeNode] Error scraping {url}: {e}")

            print("[SearchAndScrapeNode] Completed web scraping. Returning combined text.")
            return {'output': combined_text}  # Return the combined scraped text as the output

    def requires_api_call(self):
        return False  # No external API call required, only web search and scraping
