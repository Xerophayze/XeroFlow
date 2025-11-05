# Parse and Scrape Node

## Overview
The **ParseAndScrapeNode** is a specialized node in the XeroFlow system that automatically detects URLs in user input, scrapes content from those URLs, and intelligently replaces the URLs with the scraped content in the original text.

## Key Features

### 1. **Automatic URL Detection**
- Uses regex pattern matching to find all URLs in the input text
- Supports HTTP, HTTPS, and FTP protocols
- Detects URLs anywhere in the text (beginning, middle, or end)

### 2. **Web Scraping**
- Fetches content from each detected URL
- Removes unnecessary elements (scripts, styles, navigation, headers, footers)
- Extracts clean text content
- Handles timeouts and errors gracefully

### 3. **Intelligent Content Replacement**
- Replaces each URL with its scraped content
- Maintains the original text structure
- Adds optional headers showing the source URL
- Uses customizable separators between content sections

### 4. **Error Handling**
- Timeout protection for slow-loading pages
- Graceful handling of failed requests
- Clear error messages for debugging
- Continues processing even if some URLs fail

## Node Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| **node_name** | text | ParseAndScrapeNode | Display name for the node |
| **description** | text | Parses URLs... | Description of node functionality |
| **Prompt** | textarea | (empty) | Optional text to prepend to input |
| **max_content_length** | number | 5000 | Maximum characters to extract from each URL |
| **timeout** | number | 10 | Timeout in seconds for each URL request |
| **include_url_header** | boolean | true | Include URL as header before scraped content |
| **separator** | text | \n\n---\n\n | Separator between scraped content sections |
| **is_start_node** | boolean | false | Mark as workflow start node |
| **is_end_node** | boolean | false | Mark as workflow end node |

## Input/Output

### Input
- **input**: Text containing one or more URLs to be scraped

### Output
- **output**: Original text with URLs replaced by scraped content

## Usage Examples

### Example 1: Simple URL Replacement
**Input:**
```
Please summarize the information from https://example.com/article1 and https://example.com/article2
```

**Output:**
```
Please summarize the information from 

---
[Content from: https://example.com/article1]

[Scraped content from article1...]

---
 and 

---
[Content from: https://example.com/article2]

[Scraped content from article2...]

---
```

### Example 2: With Custom Prompt
**Properties:**
- Prompt: "Analyze the following sources:"

**Input:**
```
https://news.example.com/tech-trends
```

**Output:**
```
Analyze the following sources:

---
[Content from: https://news.example.com/tech-trends]

[Scraped content...]

---
```

## Workflow Integration

### Typical Workflow Pattern
```
[User Input Node] → [ParseAndScrapeNode] → [Assistant Node] → [Output Node]
```

This allows you to:
1. Accept user input with URLs
2. Automatically fetch and inject web content
3. Process the enriched content with AI
4. Return the final result

### Use Cases
- **Research Assistant**: Automatically fetch and summarize multiple web sources
- **Content Aggregation**: Combine information from various URLs
- **Context Enhancement**: Enrich prompts with real-time web data
- **Documentation Processing**: Extract content from documentation URLs

## Technical Details

### URL Extraction Regex
```python
r'(?:http|https|ftp)s?://'  # Protocol
r'(?:[a-zA-Z0-9$\-_@.&+!*\'(),]|%[0-9a-fA-F][0-9a-fA-F])+'  # Domain
r'(?::[0-9]+)?'  # Optional port
r'(?:/[^\s]*)?'  # Optional path
```

### Content Cleaning
The node removes:
- `<script>` tags and content
- `<style>` tags and content
- `<nav>` navigation elements
- `<footer>` elements
- `<header>` elements

### Error Messages
Failed scrapes are replaced with descriptive error messages:
- `[Timeout error: URL took longer than X seconds to respond]`
- `[Error scraping URL: <error details>]`
- `[Unexpected error: <error details>]`

## Performance Considerations

### Timeout Settings
- Default: 10 seconds per URL
- Adjust based on expected page load times
- Lower values = faster failure detection
- Higher values = better success rate for slow sites

### Content Length Limits
- Default: 5000 characters per URL
- Prevents memory issues with large pages
- Truncated content includes "... [Content truncated]" indicator
- Adjust based on your processing needs

### Multiple URLs
- URLs are processed sequentially
- Total processing time = (number of URLs) × (average timeout)
- Consider timeout settings for workflows with many URLs

## Best Practices

1. **Set Appropriate Timeouts**: Balance between reliability and speed
2. **Limit Content Length**: Prevent overwhelming downstream nodes
3. **Use Separators**: Make it easy to distinguish between sources
4. **Include URL Headers**: Maintain source attribution
5. **Handle Errors**: Check output for error messages before processing

## Troubleshooting

### No URLs Detected
- Verify URLs include protocol (http://, https://)
- Check for typos in URLs
- Ensure URLs are not wrapped in special characters

### Timeout Errors
- Increase timeout property value
- Check network connectivity
- Verify target site is accessible

### Empty Content
- Some sites block automated scraping
- Try increasing timeout
- Check if site requires authentication
- Verify site structure hasn't changed

## Dependencies
- **requests**: HTTP library for web requests
- **beautifulsoup4**: HTML parsing and content extraction
- **re**: Regular expressions (built-in)

Dependencies are automatically installed when the node is first loaded.

## API Call Status
This node does **not** require API calls. It performs direct web scraping without using external APIs.
