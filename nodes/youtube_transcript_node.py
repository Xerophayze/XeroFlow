from .basic_node import BaseNode
from src.workflows.node_registry import register_node
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import re
import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape
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
        url = url.strip()
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
            return url
        try:
            parsed_url = urlparse(url)
            if parsed_url.query:
                query = parse_qs(parsed_url.query)
                if query.get('v'):
                    return query['v'][0]
            if 'youtube.com' in parsed_url.netloc:
                if '/shorts/' in parsed_url.path:
                    return parsed_url.path.split('/shorts/')[1]
                if '/embed/' in parsed_url.path:
                    return parsed_url.path.split('/embed/')[1]
                if '/live/' in parsed_url.path:
                    return parsed_url.path.split('/live/')[1]
            if 'youtu.be' in parsed_url.netloc:
                return parsed_url.path.lstrip('/')
        except Exception as e:
            print(f"[YoutubeTranscriptNode] Error parsing URL: {str(e)}")

        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/live\/([a-zA-Z0-9_-]{11})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        fallback = re.search(r"([a-zA-Z0-9_-]{11})", url)
        return fallback.group(1) if fallback else None

    @dataclass
    class TranscriptResult:
        source: str
        language: str
        items: list

    def parse_caption_xml(self, xml_text):
        items = []
        root = ET.fromstring(xml_text)
        for node in root.findall(".//text"):
            start = float(node.attrib.get("start", 0))
            duration = float(node.attrib.get("dur", 0))
            text = unescape("".join(node.itertext()))
            items.append({"start": start, "duration": duration, "text": text})
        return items

    def timestamp_to_seconds(self, ts):
        match = re.match(r"(?:(\d+):)?(\d+):(\d+)(?:\.(\d+))?", ts)
        if not match:
            return 0.0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        millis = int((match.group(4) or "0")[:3].ljust(3, "0"))
        return hours * 3600 + minutes * 60 + seconds + millis / 1000

    def parse_vtt(self, vtt_text):
        items = []
        lines = [line.strip("\ufeff") for line in vtt_text.splitlines()]
        buffer = []
        start = None
        duration = None

        def flush():
            nonlocal buffer, start, duration
            if start is not None and buffer:
                items.append({
                    "start": start,
                    "duration": duration or 0,
                    "text": " ".join(buffer).strip(),
                })
            buffer = []
            start = None
            duration = None

        for line in lines:
            if not line:
                flush()
                continue
            if "-->" in line:
                parts = line.split("-->")
                start_ts = parts[0].strip()
                end_ts = parts[1].strip().split()[0]
                start = self.timestamp_to_seconds(start_ts)
                end = self.timestamp_to_seconds(end_ts)
                duration = max(0, end - start)
                continue
            if re.match(r"^\d+$", line):
                continue
            buffer.append(line)

        flush()
        return items

    def fetch_url(self, url, headers=None):
        response = requests.get(url, headers=headers or {})
        response.raise_for_status()
        return response.text

    def fetch_transcript_yta(self, video_id, languages):
        api = YouTubeTranscriptApi()
        try:
            transcript = api.fetch(video_id, languages=languages)
            items = transcript.to_raw_data()
            return self.TranscriptResult("youtube-transcript-api", transcript.language_code, items)
        except Exception:
            return None

    def fetch_metadata_yt_dlp(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"[YoutubeTranscriptNode] Error in yt-dlp metadata: {str(e)}")
            return None

    def pick_caption_track(self, info, languages):
        def pick_from(captions):
            for lang in languages:
                if lang in captions:
                    track = captions[lang][0]
                    return lang, track.get("url")
            if captions:
                lang, tracks = next(iter(captions.items()))
                return lang, tracks[0].get("url")
            return None

        subtitles = info.get("subtitles") or {}
        auto_captions = info.get("automatic_captions") or {}
        return pick_from(subtitles) or pick_from(auto_captions)

    def fetch_transcript_from_yt_dlp(self, info, languages):
        track = self.pick_caption_track(info, languages)
        if not track:
            return None
        lang, url = track
        if not url:
            return None
        text = self.fetch_url(url)
        if text.lstrip().startswith("WEBVTT"):
            items = self.parse_vtt(text)
        else:
            items = self.parse_caption_xml(text)
        return self.TranscriptResult("yt-dlp", lang, items)

    def extract_innertube_key(self, html):
        match = re.search(r"INNERTUBE_API_KEY\":\"([^\"]+)\"", html)
        return match.group(1) if match else None

    def fetch_innertube_player(self, video_id, api_key):
        url = f"https://www.youtube.com/youtubei/v1/player?key={api_key}"
        payload = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "17.31.35",
                    "androidSdkVersion": 30,
                }
            },
        }
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()

    def fetch_transcript_innertube(self, video_id, video_url, languages):
        html = self.fetch_url(video_url, headers={"User-Agent": "Mozilla/5.0"})
        api_key = self.extract_innertube_key(html)
        if not api_key:
            return None
        player = self.fetch_innertube_player(video_id, api_key)
        tracks = (
            player
            .get("captions", {})
            .get("playerCaptionsTracklistRenderer", {})
            .get("captionTracks", [])
        )
        if not tracks:
            return None
        track = None
        for lang in languages:
            track = next((t for t in tracks if t.get("languageCode") == lang), None)
            if track:
                break
        if not track:
            track = tracks[0]
        caption_url = track.get("baseUrl")
        if not caption_url:
            return None
        text = self.fetch_url(caption_url)
        if text.lstrip().startswith("WEBVTT"):
            items = self.parse_vtt(text)
        else:
            items = self.parse_caption_xml(text)
        return self.TranscriptResult("innertube", track.get("languageCode", "unknown"), items)

    def normalize_transcript(self, items):
        text = " ".join(item.get("text", "") for item in items if item.get("text"))
        return " ".join(text.split())

    def get_video_metadata(self, url):
        """Get video title and description using yt-dlp."""
        print(f"[YoutubeTranscriptNode] Fetching metadata for URL: {url}")
        info = self.fetch_metadata_yt_dlp(url)
        if not info:
            return {
                'title': 'Error: Could not fetch video title',
                'description': 'Error: Could not fetch video description'
            }
        title = info.get('title', '')
        description = info.get('description', '')
        print(f"[YoutubeTranscriptNode] Successfully got title: {title}")
        if description:
            print(f"[YoutubeTranscriptNode] Successfully got description (length: {len(description)})")
        return {
            'title': title or 'Error: Could not fetch video title',
            'description': description or 'Error: Could not fetch video description',
            'info': info
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
            preferred_lang = self.properties.get('language', {}).get('value') or self.properties.get('language', {}).get('default', 'en')
            languages = [lang.strip() for lang in preferred_lang.split(',') if lang.strip()]
            print(f"[YoutubeTranscriptNode] Using preferred language(s): {languages}")

            transcript = self.fetch_transcript_yta(video_id, languages)
            if not transcript and metadata.get('info'):
                transcript = self.fetch_transcript_from_yt_dlp(metadata['info'], languages)
            if not transcript:
                transcript = self.fetch_transcript_innertube(video_id, youtube_url, languages)

            if not transcript:
                return {
                    'transcript': 'Error: Could not retrieve transcript with available methods',
                    'title': metadata['title'],
                    'description': metadata['description']
                }

            transcript_text = self.normalize_transcript(transcript.items)
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
