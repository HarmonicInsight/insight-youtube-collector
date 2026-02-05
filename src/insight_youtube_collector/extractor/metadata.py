"""
Metadata extraction from YouTube videos using yt-dlp.
"""

from typing import Optional
from ..models.video import VideoMetadata

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


class MetadataExtractor:
    """Extract metadata from YouTube videos."""

    def __init__(self, quiet: bool = True):
        """
        Initialize the metadata extractor.

        Args:
            quiet: Suppress yt-dlp output.
        """
        if not YT_DLP_AVAILABLE:
            raise ImportError(
                "yt-dlp is not installed. "
                "Install it with: pip install yt-dlp"
            )
        self.quiet = quiet

    def extract(self, video_id: str) -> Optional[VideoMetadata]:
        """
        Extract metadata from a YouTube video.

        Args:
            video_id: YouTube video ID (11 characters).

        Returns:
            VideoMetadata or None if extraction fails.
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {
            'quiet': self.quiet,
            'no_warnings': self.quiet,
            'skip_download': True,
            'no_check_certificates': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return VideoMetadata(
                    title=info.get('title', ''),
                    channel=info.get('channel', '') or info.get('uploader', ''),
                    channel_id=info.get('channel_id', ''),
                    upload_date=info.get('upload_date', ''),
                    duration_seconds=info.get('duration', 0) or 0,
                    view_count=info.get('view_count', 0) or 0,
                    like_count=info.get('like_count', 0) or 0,
                    description=info.get('description', '') or '',
                    tags=info.get('tags', []) or [],
                    categories=info.get('categories', []) or [],
                    thumbnail_url=info.get('thumbnail', '') or '',
                )
        except Exception as e:
            print(f"  Metadata extraction error: {e}")
            return None
