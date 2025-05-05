"""
Web Scraper Module for XeroFlow

This module provides functionality to scrape content from web URLs with configurable depth.
It supports both single URLs and lists of URLs, with retry mechanisms and proper error handling.
"""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from typing import Union, List, Dict, Set, Optional
import logging

class WebScraper:
    def __init__(self, retry_attempts: int = 2, timeout: int = 5, delay_between_requests: float = 0.5):
        """
        Initialize the WebScraper with configurable parameters.
        
        Args:
            retry_attempts (int): Number of times to retry failed requests
            timeout (int): Timeout in seconds for each request
            delay_between_requests (float): Delay in seconds between requests to avoid overwhelming servers
        """
        self.retry_attempts = retry_attempts
        self.timeout = timeout
        self.delay_between_requests = delay_between_requests
        self.visited_urls: Set[str] = set()
        self.logger = logging.getLogger(__name__)

    def format_url(self, url: str) -> str:
        """
        Format URL by adding https:// if no protocol is specified.
        
        Args:
            url (str): URL to format
            
        Returns:
            str: Formatted URL
        """
        if not re.match(r'^(?:http|https)://', url):
            return f'https://{url}'
        return url

    def is_valid_url(self, url: str) -> bool:
        """
        Check if the URL is valid and has an allowed scheme.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if URL is valid, False otherwise
        """
        try:
            parsed = urlparse(url)
            return parsed.scheme in ['http', 'https'] and bool(parsed.netloc)
        except Exception:
            return False

    def scrape_url(self, url: str, current_depth: int, max_depth: int) -> Dict[str, Union[str, List[str], bool]]:
        """
        Scrape content from a single URL with retry mechanism.
        
        Args:
            url (str): URL to scrape
            current_depth (int): Current scraping depth
            max_depth (int): Maximum depth to scrape
            
        Returns:
            dict: Dictionary containing scraped content and metadata
        """
        if url in self.visited_urls or current_depth > max_depth:
            return {'success': False, 'content': '', 'links': [], 'error': 'URL already visited or max depth reached'}

        self.visited_urls.add(url)
        
        for attempt in range(self.retry_attempts):
            try:
                self.logger.info(f"Scraping {url} (Depth {current_depth}, Attempt {attempt + 1})")
                
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract text content
                text = soup.get_text(separator=' ', strip=True)
                
                # Extract links if not at max depth
                links = []
                if current_depth < max_depth:
                    for link in soup.find_all('a', href=True):
                        full_link = urljoin(url, link['href'])
                        if self.is_valid_url(full_link):
                            links.append(full_link)
                
                time.sleep(self.delay_between_requests)  # Respect rate limiting
                
                return {
                    'success': True,
                    'content': text,
                    'links': links,
                    'error': None
                }
                
            except requests.RequestException as e:
                error = f"Error scraping {url} on attempt {attempt + 1}: {str(e)}"
                self.logger.error(error)
                if attempt < self.retry_attempts - 1:
                    time.sleep(2)  # Wait before retrying
        
        return {
            'success': False,
            'content': '',
            'links': [],
            'error': f'Failed to scrape {url} after {self.retry_attempts} attempts'
        }

    def scrape(self, urls: Union[str, List[str]], max_depth: int = 1) -> Dict[str, Union[dict, str]]:
        """
        Main scraping function that handles both single URLs and lists of URLs.
        
        Args:
            urls (Union[str, List[str]]): Single URL or list of URLs to scrape
            max_depth (int): Maximum depth to follow links
            
        Returns:
            dict: Dictionary containing scraped content and metadata for all URLs
        """
        # Convert input to list of URLs
        if isinstance(urls, str):
            url_list = [url.strip() for url in urls.split(',') if url.strip()]
        else:
            url_list = [str(url).strip() for url in urls if url]

        # Format and validate URLs
        formatted_urls = [self.format_url(url) for url in url_list if url]
        valid_urls = [url for url in formatted_urls if self.is_valid_url(url)]

        if not valid_urls:
            return {
                'success': False,
                'error': 'No valid URLs provided',
                'results': {}
            }

        # Reset visited URLs for new scraping session
        self.visited_urls.clear()
        
        # Store results for each URL
        results = {}
        
        def scrape_recursive(url: str, depth: int):
            if url not in results:  # Avoid re-scraping URLs
                result = self.scrape_url(url, depth, max_depth)
                results[url] = result
                
                # Recursively scrape linked pages if successful
                if result['success'] and depth < max_depth:
                    for link in result['links']:
                        scrape_recursive(link, depth + 1)

        # Start scraping from each initial URL
        for url in valid_urls:
            scrape_recursive(url, 1)

        return {
            'success': True,
            'error': None,
            'results': results
        }

    def get_text_content(self, scrape_results: Dict[str, Union[dict, str]], include_urls: bool = True) -> str:
        """
        Extract and format text content from scraping results.
        
        Args:
            scrape_results (dict): Results from scrape() method
            include_urls (bool): Whether to include URLs in the output
            
        Returns:
            str: Formatted text content
        """
        if not scrape_results.get('success'):
            return f"Error: {scrape_results.get('error', 'Unknown error occurred')}"

        content = []
        for url, result in scrape_results.get('results', {}).items():
            if result.get('success'):
                if include_urls:
                    content.append(f"URL: {url}")
                content.append(result.get('content', ''))
                content.append('')  # Empty line between entries

        return '\n'.join(content) if content else "No content was scraped."
