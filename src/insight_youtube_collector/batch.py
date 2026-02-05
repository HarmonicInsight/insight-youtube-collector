"""
Batch collection for processing multiple YouTube sources at once.

Supports:
- Multiple playlists
- Multiple channels
- Multiple search keywords
- URL lists

Config file format (YAML):
```yaml
sources:
  playlists:
    - url: "https://youtube.com/playlist?list=xxx"
      max: 20
    - url: "https://youtube.com/playlist?list=yyy"
      max: 10

  channels:
    - url: "https://youtube.com/@channelname"
      max: 20

  keywords:
    - query: "建設DX AI活用"
      max: 10
    - query: "施工管理 デジタル化"
      max: 10

  urls:
    - "https://youtube.com/watch?v=xxx"
    - "https://youtube.com/watch?v=yyy"

output:
  warehouse: true
  warehouse_dir: "data/warehouse/lectures"
  json: true
  json_path: "data/output/batch_result.json"
```
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .collector import YouTubeCollector
from .models.video import VideoData
from .config import Settings


@dataclass
class SourceConfig:
    """Configuration for a single source."""
    source_type: str  # playlist, channel, keyword, url
    value: str  # URL or search query
    max_videos: int = 20
    label: Optional[str] = None  # optional label for logging


@dataclass
class BatchConfig:
    """Configuration for batch collection."""
    sources: list[SourceConfig] = field(default_factory=list)

    # Output settings
    save_warehouse: bool = True
    warehouse_dir: str = "data/warehouse/lectures"
    save_json: bool = False
    json_path: str = "data/output/batch_result.json"

    # Processing settings
    include_segments: bool = False  # usually not needed for warehouse

    @classmethod
    def from_dict(cls, data: dict) -> "BatchConfig":
        """Create BatchConfig from dictionary (parsed YAML/JSON)."""
        sources = []

        source_data = data.get("sources", {})

        # Parse playlists
        for item in source_data.get("playlists", []):
            if isinstance(item, str):
                sources.append(SourceConfig("playlist", item))
            else:
                sources.append(SourceConfig(
                    "playlist",
                    item.get("url", item.get("value", "")),
                    item.get("max", 20),
                    item.get("label"),
                ))

        # Parse channels
        for item in source_data.get("channels", []):
            if isinstance(item, str):
                sources.append(SourceConfig("channel", item))
            else:
                sources.append(SourceConfig(
                    "channel",
                    item.get("url", item.get("value", "")),
                    item.get("max", 20),
                    item.get("label"),
                ))

        # Parse keywords/search queries
        for item in source_data.get("keywords", source_data.get("search", [])):
            if isinstance(item, str):
                sources.append(SourceConfig("keyword", item, 10))
            else:
                sources.append(SourceConfig(
                    "keyword",
                    item.get("query", item.get("value", "")),
                    item.get("max", 10),
                    item.get("label"),
                ))

        # Parse direct URLs
        for item in source_data.get("urls", []):
            if isinstance(item, str):
                sources.append(SourceConfig("url", item, 1))
            else:
                sources.append(SourceConfig(
                    "url",
                    item.get("url", item.get("value", "")),
                    1,
                    item.get("label"),
                ))

        # Parse output settings
        output = data.get("output", {})

        return cls(
            sources=sources,
            save_warehouse=output.get("warehouse", True),
            warehouse_dir=output.get("warehouse_dir", "data/warehouse/lectures"),
            save_json=output.get("json", False),
            json_path=output.get("json_path", "data/output/batch_result.json"),
            include_segments=output.get("include_segments", False),
        )

    @classmethod
    def from_file(cls, path: str) -> "BatchConfig":
        """Load BatchConfig from a YAML or JSON file."""
        path = Path(path)

        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix in ('.yaml', '.yml'):
                if not YAML_AVAILABLE:
                    raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        return cls.from_dict(data)

    @classmethod
    def from_keywords_file(cls, path: str, max_per_keyword: int = 10) -> "BatchConfig":
        """
        Create BatchConfig from a simple text file with one keyword per line.

        Example file:
        ```
        建設DX AI活用
        施工管理 デジタル化
        # コメント行は無視
        BIM 活用事例
        ```
        """
        sources = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    sources.append(SourceConfig("keyword", line, max_per_keyword))

        return cls(sources=sources)

    @classmethod
    def from_urls_file(cls, path: str) -> "BatchConfig":
        """
        Create BatchConfig from a text file with URLs.
        Supports playlist URLs, channel URLs, and video URLs.
        """
        sources = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Detect source type from URL
                if 'playlist?list=' in line:
                    sources.append(SourceConfig("playlist", line, 50))
                elif '/@' in line or '/channel/' in line or '/c/' in line:
                    sources.append(SourceConfig("channel", line, 20))
                else:
                    sources.append(SourceConfig("url", line, 1))

        return cls(sources=sources)


class BatchCollector:
    """
    Batch collector for processing multiple YouTube sources.
    """

    def __init__(self, config: BatchConfig, verbose: bool = True):
        """
        Initialize batch collector.

        Args:
            config: Batch configuration.
            verbose: Print progress messages.
        """
        self.config = config
        self.verbose = verbose
        self.collector = YouTubeCollector(Settings(quiet_mode=not verbose))

    def collect_all(self) -> dict:
        """
        Collect from all configured sources.

        Returns:
            Summary dict with collection statistics.
        """
        all_videos: list[VideoData] = []
        source_stats = []

        total_sources = len(self.config.sources)

        for i, source in enumerate(self.config.sources, 1):
            if self.verbose:
                label = source.label or source.value[:50]
                print(f"\n{'='*60}")
                print(f"[{i}/{total_sources}] {source.source_type.upper()}: {label}")
                print(f"{'='*60}")

            try:
                videos = self._collect_source(source)
                all_videos.extend(videos)

                source_stats.append({
                    "type": source.source_type,
                    "value": source.value,
                    "collected": len(videos),
                    "successful": sum(1 for v in videos if not v.transcript.error),
                    "status": "success",
                })

            except Exception as e:
                if self.verbose:
                    print(f"  Error: {e}")
                source_stats.append({
                    "type": source.source_type,
                    "value": source.value,
                    "collected": 0,
                    "status": "error",
                    "error": str(e),
                })

        # Deduplicate by video_id
        seen_ids = set()
        unique_videos = []
        for video in all_videos:
            if video.video_id not in seen_ids:
                seen_ids.add(video.video_id)
                unique_videos.append(video)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Collection complete: {len(unique_videos)} unique videos")
            print(f"{'='*60}")

        # Save results
        save_results = {}

        if self.config.save_warehouse and unique_videos:
            if self.verbose:
                print(f"\nSaving to warehouse: {self.config.warehouse_dir}")
            warehouse_result = self.collector.save_warehouse(
                unique_videos,
                warehouse_dir=self.config.warehouse_dir,
            )
            save_results["warehouse"] = warehouse_result
            if self.verbose:
                print(f"  Saved: {warehouse_result['saved']} files")

        if self.config.save_json and unique_videos:
            if self.verbose:
                print(f"\nSaving to JSON: {self.config.json_path}")
            json_result = self.collector.save_json(
                unique_videos,
                output_path=self.config.json_path,
                include_segments=self.config.include_segments,
            )
            save_results["json"] = json_result

        return {
            "total_sources": total_sources,
            "total_collected": len(all_videos),
            "unique_videos": len(unique_videos),
            "duplicates_removed": len(all_videos) - len(unique_videos),
            "source_stats": source_stats,
            "save_results": save_results,
        }

    def _collect_source(self, source: SourceConfig) -> list[VideoData]:
        """Collect videos from a single source."""
        if source.source_type == "playlist":
            return self.collector.collect_from_playlist(
                source.value,
                max_videos=source.max_videos,
                verbose=self.verbose,
            )
        elif source.source_type == "channel":
            return self.collector.collect_from_channel(
                source.value,
                max_videos=source.max_videos,
                verbose=self.verbose,
            )
        elif source.source_type == "keyword":
            return self.collector.collect_from_search(
                source.value,
                max_videos=source.max_videos,
                verbose=self.verbose,
            )
        elif source.source_type == "url":
            return self.collector.collect_from_urls(
                [source.value],
                max_videos=1,
                verbose=self.verbose,
            )
        else:
            raise ValueError(f"Unknown source type: {source.source_type}")
