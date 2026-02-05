"""
Core YouTube collector that orchestrates extraction and storage.
"""

import time
from typing import Optional, Callable
from .extractor import TranscriptExtractor, MetadataExtractor, VideoSourceExtractor
from .storage import JsonStorage, WarehouseStorage
from .models.video import VideoData, VideoMetadata, TranscriptData
from .config import Settings, DEFAULT_SETTINGS


def format_duration(seconds: int) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    if not seconds:
        return "Unknown"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class YouTubeCollector:
    """
    Main collector class that orchestrates YouTube data extraction.

    Supports multiple input sources (URLs, playlists, channels, search)
    and multiple output formats (JSON, warehouse).
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the YouTube collector.

        Args:
            settings: Configuration settings. Uses defaults if not provided.
        """
        self.settings = settings or DEFAULT_SETTINGS

        # Initialize extractors
        self.source_extractor = VideoSourceExtractor(quiet=self.settings.quiet_mode)
        self.metadata_extractor = MetadataExtractor(quiet=self.settings.quiet_mode)
        self.transcript_extractor = TranscriptExtractor(
            preferred_langs=self.settings.preferred_langs,
            quiet=self.settings.quiet_mode,
        )

    def collect_video(self, video_id: str, verbose: bool = True) -> Optional[VideoData]:
        """
        Collect data from a single video.

        Args:
            video_id: YouTube video ID (11 characters).
            verbose: Print progress messages.

        Returns:
            VideoData or None if collection fails.
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        if verbose:
            print(f"  Processing: {url}")

        # Extract metadata
        metadata = self.metadata_extractor.extract(video_id)
        if not metadata:
            # Create minimal metadata on failure
            metadata = VideoMetadata(
                title="(Title Unknown)",
                channel="",
                channel_id="",
                upload_date="",
                duration_seconds=0,
                view_count=0,
                like_count=0,
                description="",
                tags=[],
                categories=[],
                thumbnail_url="",
            )

        if verbose:
            print(f"     Title: {metadata.title}")
            print(f"     Duration: {format_duration(metadata.duration_seconds)}")

        # Extract transcript
        transcript = self.transcript_extractor.extract(video_id)

        if verbose:
            if transcript.error:
                print(f"     Transcript: {transcript.error}")
            else:
                gen = "(auto-generated)" if transcript.is_generated else "(manual)"
                text_len = len(transcript.full_text)
                print(f"     Transcript: {transcript.language} {gen} / {transcript.segment_count} segments / {text_len} chars")

        return VideoData.create(video_id, metadata, transcript)

    def collect_from_urls(
        self,
        urls: list[str],
        max_videos: Optional[int] = None,
        verbose: bool = True,
    ) -> list[VideoData]:
        """
        Collect data from multiple video URLs.

        Args:
            urls: List of YouTube video URLs.
            max_videos: Maximum number of videos to process.
            verbose: Print progress messages.

        Returns:
            List of collected VideoData.
        """
        video_ids = self.source_extractor.extract_from_urls(urls)
        return self._collect_videos(video_ids, max_videos, verbose)

    def collect_from_playlist(
        self,
        playlist_url: str,
        max_videos: Optional[int] = None,
        verbose: bool = True,
    ) -> list[VideoData]:
        """
        Collect data from a YouTube playlist.

        Args:
            playlist_url: YouTube playlist URL.
            max_videos: Maximum number of videos to process.
            verbose: Print progress messages.

        Returns:
            List of collected VideoData.
        """
        if verbose:
            print(f"Loading playlist: {playlist_url}")
        max_v = max_videos or self.settings.default_max_videos
        video_ids = self.source_extractor.extract_from_playlist(playlist_url, max_v)
        return self._collect_videos(video_ids, max_videos, verbose)

    def collect_from_channel(
        self,
        channel_url: str,
        max_videos: Optional[int] = None,
        verbose: bool = True,
    ) -> list[VideoData]:
        """
        Collect data from a YouTube channel's latest videos.

        Args:
            channel_url: YouTube channel URL.
            max_videos: Maximum number of videos to process.
            verbose: Print progress messages.

        Returns:
            List of collected VideoData.
        """
        if verbose:
            print(f"Loading channel: {channel_url}")
        max_v = max_videos or self.settings.default_max_videos
        video_ids = self.source_extractor.extract_from_channel(channel_url, max_v)
        return self._collect_videos(video_ids, max_videos, verbose)

    def collect_from_search(
        self,
        query: str,
        max_videos: Optional[int] = None,
        verbose: bool = True,
    ) -> list[VideoData]:
        """
        Collect data from YouTube search results.

        Args:
            query: Search query string.
            max_videos: Maximum number of videos to process.
            verbose: Print progress messages.

        Returns:
            List of collected VideoData.
        """
        if verbose:
            print(f"Searching: '{query}'")
        max_v = max_videos or self.settings.default_max_videos
        video_ids = self.source_extractor.extract_from_search(query, max_v)
        return self._collect_videos(video_ids, max_videos, verbose)

    def collect_from_file(
        self,
        file_path: str,
        max_videos: Optional[int] = None,
        verbose: bool = True,
    ) -> list[VideoData]:
        """
        Collect data from a file containing video URLs.

        Args:
            file_path: Path to text file with URLs (one per line).
            max_videos: Maximum number of videos to process.
            verbose: Print progress messages.

        Returns:
            List of collected VideoData.
        """
        if verbose:
            print(f"Loading URLs from: {file_path}")
        video_ids = self.source_extractor.extract_from_file(file_path)
        return self._collect_videos(video_ids, max_videos, verbose)

    def _collect_videos(
        self,
        video_ids: list[str],
        max_videos: Optional[int],
        verbose: bool,
    ) -> list[VideoData]:
        """Internal method to collect from a list of video IDs."""
        # Deduplicate and limit
        seen = set()
        unique_ids = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                unique_ids.append(vid)

        max_v = max_videos or self.settings.default_max_videos
        video_ids = unique_ids[:max_v]

        if not video_ids:
            if verbose:
                print("No videos found to process.")
            return []

        if verbose:
            print(f"\nProcessing {len(video_ids)} videos\n")

        results = []
        for i, vid in enumerate(video_ids, 1):
            if verbose:
                print(f"[{i}/{len(video_ids)}]")
            video_data = self.collect_video(vid, verbose)
            if video_data:
                results.append(video_data)
            if verbose:
                print()

            # Add delay between requests to avoid rate limiting (429)
            if i < len(video_ids):
                time.sleep(2.0)

        return results

    def save_json(
        self,
        videos: list[VideoData],
        output_path: Optional[str] = None,
        append: bool = False,
        pretty: bool = True,
        include_segments: bool = True,
    ) -> dict:
        """
        Save collected videos to JSON format.

        Args:
            videos: List of VideoData to save.
            output_path: Output file path.
            append: Merge with existing file.
            pretty: Use indented JSON.
            include_segments: Include transcript segments.

        Returns:
            Crawl info summary dict.
        """
        storage = JsonStorage(
            output_path=output_path or self.settings.default_output_path,
            pretty=pretty,
            include_segments=include_segments,
        )
        return storage.save(videos, append=append)

    def save_warehouse(
        self,
        videos: list[VideoData],
        warehouse_dir: Optional[str] = None,
    ) -> dict:
        """
        Save collected videos to warehouse format.

        Compatible with Harmonic Mart Generator for Knowledge Mart creation.

        Args:
            videos: List of VideoData to save.
            warehouse_dir: Directory to store transcript files.

        Returns:
            Summary dict with save statistics.
        """
        storage = WarehouseStorage(
            warehouse_dir=warehouse_dir or self.settings.default_warehouse_dir,
        )
        return storage.save(videos)
