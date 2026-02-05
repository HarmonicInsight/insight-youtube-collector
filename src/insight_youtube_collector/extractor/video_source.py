"""
Video source extraction for URLs, playlists, channels, and search queries.
"""

import re
from typing import Optional

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


class VideoSourceExtractor:
    """Extract video IDs from various YouTube sources."""

    # URL patterns for video ID extraction
    VIDEO_ID_PATTERNS = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',  # bare 11-char ID
    ]

    def __init__(self, quiet: bool = True):
        """
        Initialize the video source extractor.

        Args:
            quiet: Suppress yt-dlp output.
        """
        if not YT_DLP_AVAILABLE:
            raise ImportError(
                "yt-dlp is not installed. "
                "Install it with: pip install yt-dlp"
            )
        self.quiet = quiet

    def extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract a single video ID from a URL.

        Args:
            url: YouTube video URL or bare video ID.

        Returns:
            Video ID (11 characters) or None.
        """
        for pattern in self.VIDEO_ID_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def extract_from_urls(self, urls: list[str]) -> list[str]:
        """
        Extract video IDs from multiple URLs.

        Args:
            urls: List of YouTube video URLs.

        Returns:
            List of valid video IDs.
        """
        video_ids = []
        for url in urls:
            vid = self.extract_video_id(url.strip())
            if vid:
                video_ids.append(vid)
        return video_ids

    def extract_from_playlist(self, playlist_url: str, max_videos: int = 50) -> list[str]:
        """
        Extract video IDs from a YouTube playlist.

        Args:
            playlist_url: YouTube playlist URL.
            max_videos: Maximum number of videos to extract.

        Returns:
            List of video IDs.
        """
        ydl_opts = {
            'quiet': self.quiet,
            'no_warnings': self.quiet,
            'extract_flat': True,
            'skip_download': True,
            'playlistend': max_videos,
        }

        video_ids = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                entries = info.get('entries', [])
                for entry in entries:
                    vid = entry.get('id')
                    if vid:
                        video_ids.append(vid)
        except Exception as e:
            print(f"  Playlist extraction error: {e}")

        return video_ids[:max_videos]

    def extract_from_channel(self, channel_url: str, max_videos: int = 20) -> list[str]:
        """
        Extract video IDs from a YouTube channel's latest videos.

        Args:
            channel_url: YouTube channel URL.
            max_videos: Maximum number of videos to extract.

        Returns:
            List of video IDs.
        """
        # Normalize channel URL to /videos
        if not channel_url.endswith('/videos'):
            channel_url = channel_url.rstrip('/') + '/videos'

        ydl_opts = {
            'quiet': self.quiet,
            'no_warnings': self.quiet,
            'extract_flat': True,
            'skip_download': True,
            'playlistend': max_videos,
        }

        video_ids = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                entries = info.get('entries', [])
                for entry in entries:
                    vid = entry.get('id')
                    if vid:
                        video_ids.append(vid)
        except Exception as e:
            print(f"  Channel extraction error: {e}")

        return video_ids[:max_videos]

    def extract_from_search(self, query: str, max_results: int = 10) -> list[str]:
        """
        Extract video IDs from YouTube search results.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of video IDs.
        """
        # Use explicit ytsearch prefix for YouTube search
        search_query = f"ytsearch{max_results}:{query}"

        ydl_opts = {
            'quiet': self.quiet,
            'no_warnings': self.quiet,
            'extract_flat': True,
            'skip_download': True,
        }

        video_ids = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                entries = info.get('entries', [])
                for entry in entries:
                    if entry:
                        vid = entry.get('id')
                        if vid:
                            video_ids.append(vid)
        except Exception as e:
            print(f"  Search extraction error: {e}")

        return video_ids[:max_results]

    def extract_from_file(self, file_path: str) -> list[str]:
        """
        Extract video IDs from a text file (one URL per line).

        Args:
            file_path: Path to text file with URLs.

        Returns:
            List of video IDs.
        """
        video_ids = []
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    vid = self.extract_video_id(line)
                    if vid:
                        video_ids.append(vid)
        return video_ids
