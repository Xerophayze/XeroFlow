from .basic_node import BaseNode
from src.workflows.node_registry import register_node
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs

@register_node('YoutubeTranscriptNode')
class YoutubeTranscriptNode(BaseNode):
    def define_inputs(self):
        return ['input']  # Match the basic node input name

    def define_outputs(self):
        return ['transcript', 'title', 'description']  # Added new outputs

    def define_properties(self):
        props = self.get_default_properties()
        props.update({
            'node_name': {
                'type': 'text',
                'label': 'Custom Node Name',
                'default': 'YouTube Transcript Node'
            },
            'description': {
                'type': 'text',
                'label': 'Description',
                'default': 'Extracts transcript and metadata from a YouTube video URL'
            },
            'language': {
                'type': 'text',
                'label': 'Preferred Language',
                'default': 'en'  # Default to English
            }
        })
        return props

    def extract_video_id(self, url):
        """Extract the video ID from various forms of YouTube URLs."""
        try:
            # Parse the URL
            parsed_url = urlparse(url)
            
            # Handle different URL formats
            if 'youtube.com' in parsed_url.netloc:
                if '/watch' in parsed_url.path:
                    # Regular watch URL
                    query = parse_qs(parsed_url.query)
                    return query.get('v', [None])[0]
                elif '/shorts/' in parsed_url.path:
                    # Shorts URL
                    return parsed_url.path.split('/shorts/')[1]
                elif '/embed/' in parsed_url.path:
                    # Embed URL
                    return parsed_url.path.split('/embed/')[1]
            elif 'youtu.be' in parsed_url.netloc:
                # Short URL
                return parsed_url.path[1:]
                
        except Exception as e:
            print(f"[YoutubeTranscriptNode] Error parsing URL: {str(e)}")
            
        # Fallback to regex if URL parsing fails
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/shorts\/([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_video_metadata(self, url):
        """Get video title and description using yt-dlp."""
        try:
            print(f"[YoutubeTranscriptNode] Fetching metadata for URL: {url}")
            
            # Configure yt-dlp options
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'force_generic_extractor': False
            }
            
            # Create yt-dlp object
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # Extract video information
                    info = ydl.extract_info(url, download=False)
                    
                    if info:
                        title = info.get('title', '')
                        description = info.get('description', '')
                        
                        print(f"[YoutubeTranscriptNode] Successfully got title: {title}")
                        if description:
                            print(f"[YoutubeTranscriptNode] Successfully got description (length: {len(description)})")
                        
                        return {
                            'title': title or 'Error: Could not fetch video title',
                            'description': description or 'Error: Could not fetch video description'
                        }
                    else:
                        print("[YoutubeTranscriptNode] No metadata found in yt-dlp response")
                        
                except Exception as e:
                    print(f"[YoutubeTranscriptNode] Error extracting info: {str(e)}")
                    
        except Exception as e:
            print(f"[YoutubeTranscriptNode] Error in yt-dlp setup: {str(e)}")
            
        return {
            'title': 'Error: Could not fetch video title',
            'description': 'Error: Could not fetch video description'
        }

    def process(self, inputs):
        """Process the YouTube URL and return the video transcript and metadata."""
        youtube_url = inputs.get('input', '').strip()
        print(f"[YoutubeTranscriptNode] Received URL: '{youtube_url}'")

        if not youtube_url:
            print("[YoutubeTranscriptNode] No URL provided in inputs")
            return {
                'transcript': 'Error: No YouTube URL provided',
                'title': '',
                'description': ''
            }

        try:
            # Get video metadata first
            metadata = self.get_video_metadata(youtube_url)
            print(f"[YoutubeTranscriptNode] Got video title: {metadata['title']}")

            # Extract video ID from URL
            video_id = self.extract_video_id(youtube_url)
            print(f"[YoutubeTranscriptNode] Extracted video ID: '{video_id}'")

            if not video_id:
                print("[YoutubeTranscriptNode] Failed to extract video ID")
                return {
                    'transcript': 'Error: Invalid YouTube URL format',
                    'title': metadata['title'],
                    'description': metadata['description']
                }

            # Get preferred language from properties
            preferred_lang = self.properties.get('language', {}).get('default', 'en')
            print(f"[YoutubeTranscriptNode] Using preferred language: {preferred_lang}")

            # Fetch transcript
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            print(f"[YoutubeTranscriptNode] Successfully got transcript list")
            
            try:
                # Try to get transcript in preferred language
                transcript = transcript_list.find_transcript([preferred_lang])
                print(f"[YoutubeTranscriptNode] Found transcript in preferred language")
            except:
                try:
                    # Fallback to auto-translated transcript
                    transcript = transcript_list.find_transcript(['en']).translate(preferred_lang)
                    print(f"[YoutubeTranscriptNode] Using auto-translated transcript")
                except Exception as e:
                    print(f"[YoutubeTranscriptNode] Error getting transcript: {str(e)}")
                    return {
                        'transcript': f'Error: Could not get transcript - {str(e)}',
                        'title': metadata['title'],
                        'description': metadata['description']
                    }

            # Extract transcript text
            transcript_parts = transcript.fetch()
            try:
                # Try accessing as dictionary (older API version)
                transcript_text = ' '.join(part['text'] for part in transcript_parts)
            except (TypeError, KeyError):
                # Try accessing as object attributes (newer API version)
                transcript_text = ' '.join(part.text for part in transcript_parts)
            print(f"[YoutubeTranscriptNode] Successfully extracted transcript of length: {len(transcript_text)}")

            return {
                'transcript': transcript_text,
                'title': metadata['title'],
                'description': metadata['description']
            }

        except Exception as e:
            print(f"[YoutubeTranscriptNode] Error in process: {str(e)}")
            return {
                'transcript': f'Error: {str(e)}',
                'title': metadata.get('title', 'Error: Could not fetch video title'),
                'description': metadata.get('description', 'Error: Could not fetch video description')
            }
