"""
Core YouTube collector that orchestrates extraction and storage.
"""

import time
from typing import Optional, Callable, List
from .extractor import TranscriptExtractor, MetadataExtractor, VideoSourceExtractor
from .storage import JsonStorage, WarehouseStorage
from .models.video import VideoData, VideoMetadata, TranscriptData
from .config import Settings, DEFAULT_SETTINGS
from .analyzer import PIVOTAnalyzer, VideoAnalysisResult, save_analysis_results, print_analysis_summary


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

    def __init__(
        self,
        settings: Optional[Settings] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the YouTube collector.

        Args:
            settings: Configuration settings. Uses defaults if not provided.
            status_callback: Optional callback for status messages (e.g., rate limit waits).
        """
        self.settings = settings or DEFAULT_SETTINGS
        self.status_callback = status_callback

        # Initialize extractors
        self.source_extractor = VideoSourceExtractor(quiet=self.settings.quiet_mode)
        self.metadata_extractor = MetadataExtractor(quiet=self.settings.quiet_mode)
        self.transcript_extractor = TranscriptExtractor(
            preferred_langs=self.settings.preferred_langs,
            quiet=self.settings.quiet_mode,
            use_cookies=self.settings.use_cookies,
            cookie_browser=self.settings.cookie_browser,
            status_callback=status_callback,
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
        consecutive_failures = 0
        base_delay = 5.0  # Base delay between requests

        for i, vid in enumerate(video_ids, 1):
            if verbose:
                print(f"[{i}/{len(video_ids)}]")
            video_data = self.collect_video(vid, verbose)
            if video_data:
                results.append(video_data)
                # Check if transcript failed (might be rate limited)
                if video_data.transcript and video_data.transcript.error:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0
            else:
                consecutive_failures += 1
            if verbose:
                print()

            # Add delay between requests to avoid rate limiting (429)
            # Increase delay progressively if we see failures
            if i < len(video_ids):
                delay = base_delay + (consecutive_failures * 5.0)  # Add 5s per failure
                delay = min(delay, 60.0)  # Cap at 60 seconds
                if verbose and delay > base_delay:
                    print(f"  (Increasing delay to {delay:.0f}s due to failures)")
                time.sleep(delay)

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

    # ========================================
    # PIVOT Analysis Methods
    # ========================================

    def analyze(
        self,
        videos: List[VideoData],
        domain: Optional[str] = None,
        verbose: bool = True,
    ) -> List[VideoAnalysisResult]:
        """
        Analyze collected videos using PIVOT framework.

        PIVOT classifies transcript content into:
        - P (Pain): 課題・困りごと
        - I (Insecurity): 不安・心配
        - V (Vision): 要望・理想像
        - O (Objection): 摩擦・抵抗
        - T (Traction): 成功・強み

        Args:
            videos: List of VideoData to analyze.
            domain: Business domain for weight adjustment.
            verbose: Print progress and summary.

        Returns:
            List[VideoAnalysisResult]: PIVOT analysis results.
        """
        if verbose:
            print(f"\n🔍 Analyzing {len(videos)} videos with PIVOT framework...")

        analyzer = PIVOTAnalyzer(domain=domain)
        results = []

        for i, video in enumerate(videos, 1):
            if verbose:
                print(f"  [{i}/{len(videos)}] {video.metadata.title[:50]}...")

            result = analyzer.analyze_video(video)
            results.append(result)

            if verbose:
                p = result.pain_count
                i_count = result.insecurity_count
                v = result.vision_count
                o = result.objection_count
                t = result.traction_count
                print(f"           P:{p} I:{i_count} V:{v} O:{o} T:{t} (Score: {result.total_score})")

        if verbose:
            print_analysis_summary(results)

        return results

    def save_analysis(
        self,
        results: List[VideoAnalysisResult],
        output_path: str,
        format: str = "json",
    ) -> None:
        """
        Save PIVOT analysis results.

        Args:
            results: List of VideoAnalysisResult.
            output_path: Output file path.
            format: Output format ("json" or "jsonl" for mart items).
        """
        save_analysis_results(results, output_path, format)
        print(f"✅ Analysis saved to: {output_path}")

    def collect_and_analyze(
        self,
        videos: Optional[List[VideoData]] = None,
        urls: Optional[List[str]] = None,
        playlist_url: Optional[str] = None,
        channel_url: Optional[str] = None,
        search_query: Optional[str] = None,
        max_videos: Optional[int] = None,
        domain: Optional[str] = None,
        output_json: Optional[str] = None,
        output_analysis: Optional[str] = None,
        verbose: bool = True,
    ) -> tuple[List[VideoData], List[VideoAnalysisResult]]:
        """
        Collect videos and analyze them in one pipeline.

        Args:
            videos: Pre-collected videos (if any).
            urls: Video URLs to collect.
            playlist_url: Playlist URL.
            channel_url: Channel URL.
            search_query: Search query.
            max_videos: Maximum videos to process.
            domain: Business domain for PIVOT analysis.
            output_json: Path to save collected data.
            output_analysis: Path to save analysis results.
            verbose: Print progress.

        Returns:
            Tuple of (collected videos, analysis results).
        """
        # Collect videos if not provided
        if videos is None:
            videos = []
            if urls:
                videos.extend(self.collect_from_urls(urls, max_videos, verbose))
            if playlist_url:
                videos.extend(self.collect_from_playlist(playlist_url, max_videos, verbose))
            if channel_url:
                videos.extend(self.collect_from_channel(channel_url, max_videos, verbose))
            if search_query:
                videos.extend(self.collect_from_search(search_query, max_videos, verbose))

        if not videos:
            if verbose:
                print("No videos to analyze.")
            return [], []

        # Save collected data if requested
        if output_json:
            self.save_json(videos, output_json)

        # Analyze videos
        results = self.analyze(videos, domain=domain, verbose=verbose)

        # Save analysis if requested
        if output_analysis:
            self.save_analysis(results, output_analysis)

        return videos, results
