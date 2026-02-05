"""
Insight YouTube Collector
=========================

YouTube transcript collector for Harmonic Insight text data warehouse.

This tool extracts YouTube video transcripts and outputs them in a format
compatible with the Harmonic Mart Generator warehouse structure.

Example:
    $ iyc collect --url "https://youtube.com/watch?v=xxx" --output-dir data/warehouse/lectures
    $ iyc collect --channel "@channelname" --max 20 --warehouse-mode
"""

__version__ = "1.0.0"
__author__ = "Harmonic Insight"

from .collector import YouTubeCollector
from .models.video import VideoData, TranscriptData, VideoMetadata

__all__ = [
    "YouTubeCollector",
    "VideoData",
    "TranscriptData",
    "VideoMetadata",
    "__version__",
]
