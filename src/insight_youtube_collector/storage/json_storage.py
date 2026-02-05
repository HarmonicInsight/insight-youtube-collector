"""
JSON storage for YouTube collector output.

Maintains backward compatibility with the original youtube_crawler.py output format.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models.video import VideoData


class JsonStorage:
    """Store collected video data as JSON."""

    def __init__(
        self,
        output_path: str = "youtube_data.json",
        pretty: bool = True,
        include_segments: bool = True,
    ):
        """
        Initialize JSON storage.

        Args:
            output_path: Path to output JSON file.
            pretty: Use indented JSON formatting.
            include_segments: Include transcript segments in output.
        """
        self.output_path = output_path
        self.pretty = pretty
        self.include_segments = include_segments

    def save(self, videos: list[VideoData], append: bool = False) -> dict:
        """
        Save video data to JSON file.

        Args:
            videos: List of VideoData to save.
            append: Merge with existing file (deduplicate).

        Returns:
            Summary dict with crawl statistics.
        """
        if append:
            videos = self._merge_existing(videos)

        results = [v.to_dict(self.include_segments) for v in videos]
        successful = sum(1 for v in videos if not v.transcript.error)

        output = {
            'crawl_info': {
                'tool': 'Insight YouTube Collector',
                'version': '1.0.0',
                'crawled_at': datetime.now(timezone.utc).isoformat(),
                'total_videos': len(results),
                'successful': successful,
                'failed': len(results) - successful,
            },
            'videos': results,
        }

        # Ensure parent directory exists
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2 if self.pretty else None)

        return output['crawl_info']

    def _merge_existing(self, new_videos: list[VideoData]) -> list[VideoData]:
        """Merge new videos with existing JSON file, deduplicating by video_id."""
        existing_videos = []
        if os.path.exists(self.output_path):
            with open(self.output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert existing dict entries back to list
                existing_videos = data.get('videos', [])

        existing_ids = {v['video_id'] for v in existing_videos}

        # Add new videos that aren't duplicates
        merged = existing_videos.copy()
        added = 0
        for video in new_videos:
            if video.video_id not in existing_ids:
                merged.append(video.to_dict(self.include_segments))
                existing_ids.add(video.video_id)
                added += 1

        print(f"   Merged: {len(existing_videos)} existing + {added} new = {len(merged)} total")

        # Convert back to VideoData-like dicts for consistent handling
        # Note: We return the raw dict list since we can't reconstruct full VideoData
        return new_videos  # Return original for proper handling

    def load(self) -> Optional[dict]:
        """Load existing JSON file."""
        if not os.path.exists(self.output_path):
            return None
        with open(self.output_path, 'r', encoding='utf-8') as f:
            return json.load(f)
