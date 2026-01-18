import re
import requests
from bs4 import BeautifulSoup
from .base_node import BaseNode
from src.workflows.node_registry import register_node
import time
from urllib.parse import urljoin, urlparse
import tkinter as tk
from tkinter import simpledialog, messagebox

@register_node('WebScrapingNode')
class WebScrapingNode(BaseNode):

    def define_inputs(self):
        return ['input']  # User input for URLs as string or list

    def define_outputs(self):
        return ['scraped_text']  # Output the scraped content as a single string

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {'type': 'text', 'default': 'WebScrapingNode'},
            'description': {'type': 'text', 'default': 'Scrapes data from provided URLs.'}
            # Removed 'depth' from properties since we're using a pop-up
        })
        return props

    def get_depth_from_user(self):
        # Initialize tkinter root
        root = tk.Tk()
        root.withdraw()  # Hide the root window

        # Prompt the user for depth input
        depth = 1  # Default value
        try:
            user_input = simpledialog.askstring(
                title="Set Scraping Depth",
                prompt="Enter the depth for link following (1 for initial page only):",
                initialvalue="1",
                parent=root
            )

            if user_input is None:
                # User cancelled the dialog
                print("[WebScrapingNode] User cancelled the depth input. Using default depth of 1.")
                return depth

            depth = int(user_input)
            if depth < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                title="Invalid Input",
                message="Invalid depth value entered. Using default depth of 1."
            )
            depth = 1
        finally:
            root.destroy()  # Destroy the tkinter root

        print(f"[WebScrapingNode] Scraping depth set to: {depth}")
        return depth

    def process(self, inputs):
        print("[WebScrapingNode] Starting scraping process.")

        # Display the pop-up to get the depth value from the user
        depth = self.get_depth_from_user()

        # Retrieve input and check if it contains URLs
        raw_input = inputs.get('input', '')
        if not raw_input:
            print("[WebScrapingNode] No input received for final processing.")
            return {'scraped_text': "No input URLs provided."}

        # Convert input into a list of URLs if it's a string
        if isinstance(raw_input, str):
            urls = [url.strip() for url in raw_input.split(',') if url.strip()]
        elif isinstance(raw_input, list):
            urls = [str(url).strip() for url in raw_input if url]
        else:
            print("[WebScrapingNode] Invalid input format. Expected string or list.")
            return {'scraped_text': "Invalid input format. Expected string or list of URLs."}

        # Validate URLs and add 'https://' if missing
        formatted_urls = []
        for url in urls:
            try:
                # Clean the URL first
                url = url.strip()
                url = url.strip('"\'')  # Remove quotes
                url = url.rstrip(',]}\'')  # Remove JSON list/dict endings
                url = url.split('#')[0]  # Remove fragment identifier
                
                # Remove any URL-encoded characters at the end
                if '%' in url:
                    url = url.split('%')[0]
                
                if not re.match(r'^(?:http|https)://', url):
                    url = f'https://{url}'
                
                # Parse and validate URL
                parsed = urlparse(url)
                if not parsed.netloc:
                    print(f"[WebScrapingNode] Invalid URL format: {url}")
                    continue
                    
                formatted_urls.append(url.strip())
            except Exception as e:
                print(f"[WebScrapingNode] Error processing URL {url}: {str(e)}")
                continue

        scraped_text = ""
        retry_attempts = 2  # Set the number of retry attempts
        visited_urls = set()

        def scrape(url, current_depth):
            nonlocal scraped_text
            if url in visited_urls:
                print(f"[WebScrapingNode] Already visited {url}. Skipping to avoid duplication.")
                return
            if current_depth > depth:
                print(f"[WebScrapingNode] Reached maximum depth for {url}.")
                return

            visited_urls.add(url)
            success = False
            for attempt in range(retry_attempts):
                try:
                    print(f"[WebScrapingNode] Scraping {url} (Depth {current_depth}, Attempt {attempt + 1})")
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                        
                    text = soup.get_text(separator=' ', strip=True)
                    scraped_text += f"\nURL: {url}\nContent:\n{text}\n{'='*80}\n"
                    success = True

                    if current_depth < depth:
                        # Find all links on the page
                        for link_tag in soup.find_all('a', href=True):
                            try:
                                link = link_tag['href']
                                # Resolve relative URLs
                                full_link = urljoin(url, link)
                                # Only follow HTTP and HTTPS links
                                parsed = urlparse(full_link)
                                if parsed.scheme in ['http', 'https'] and parsed.netloc:
                                    scrape(full_link, current_depth + 1)
                            except Exception as e:
                                print(f"[WebScrapingNode] Error processing link {link}: {str(e)}")
                                continue
                    break  # Exit retry loop on success
                except requests.exceptions.HTTPError as e:
                    print(f"[WebScrapingNode] HTTP Error for {url} on attempt {attempt + 1}: {e}")
                except requests.exceptions.ConnectionError as e:
                    print(f"[WebScrapingNode] Connection Error for {url} on attempt {attempt + 1}: {e}")
                except requests.exceptions.Timeout as e:
                    print(f"[WebScrapingNode] Timeout Error for {url} on attempt {attempt + 1}: {e}")
                except Exception as e:
                    print(f"[WebScrapingNode] Error scraping {url} on attempt {attempt + 1}: {e}")
                
                if attempt < retry_attempts - 1:  # Don't sleep on the last attempt
                    time.sleep(2)  # Wait before retrying

            if not success:
                print(f"[WebScrapingNode] Failed to scrape {url} after {retry_attempts} attempts.")
                scraped_text += f"\nURL: {url}\nContent: Failed to retrieve content.\n{'='*80}\n"

        for url in formatted_urls:
            scrape(url, 1)

        if not scraped_text.strip():
            scraped_text = "No content could be scraped from the provided URLs due to connection timeouts or other errors."

        print("[WebScrapingNode] Completed scraping. Returning scraped text.")
        print(f"[WebScrapingNode] Type of scraped_text: {type(scraped_text)}")  # Debugging line
        return {'scraped_text': scraped_text}
