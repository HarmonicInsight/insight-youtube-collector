"""
Insight YouTube Collector
=========================

YouTube transcript collector for Harmonic Insight text data warehouse.

This tool extracts YouTube video transcripts and outputs them in a format
compatible with the Harmonic Mart Generator warehouse structure.

Features:
- Collect transcripts from videos, playlists, channels, or search
- PIVOT analysis for insight extraction (Pain/Insecurity/Vision/Objection/Traction)
- Export to JSON, warehouse format, or PIVOT marts

Example:
    $ iyc collect --url "https://youtube.com/watch?v=xxx" --output-dir data/warehouse/lectures
    $ iyc collect --channel "@channelname" --max 20 --warehouse-mode
    $ iyc analyze --json youtube_data.json -o analysis.json --domain biz_analysis
"""

__version__ = "1.1.0"
__author__ = "Harmonic Insight"

from .collector import YouTubeCollector
from .models.video import VideoData, TranscriptData, VideoMetadata
from .analyzer import (
    PIVOTAnalyzer,
    PIVOTAnalysisResult,
    VideoAnalysisResult,
    analyze_video,
    analyze_videos,
)

__all__ = [
    # Collector
    "YouTubeCollector",
    # Models
    "VideoData",
    "TranscriptData",
    "VideoMetadata",
    # Analyzer
    "PIVOTAnalyzer",
    "PIVOTAnalysisResult",
    "VideoAnalysisResult",
    "analyze_video",
    "analyze_videos",
    # Meta
    "__version__",
]
