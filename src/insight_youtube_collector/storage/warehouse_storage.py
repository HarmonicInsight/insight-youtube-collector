"""
Warehouse storage for Harmonic Mart Generator integration.

Outputs transcript text files in the warehouse format:
- Filename: {YYYY-MM-DD}_lecture_{channel}_{title}.txt
- Location: data/warehouse/lectures/
- Manifest: warehouse_manifest.json

This format is directly compatible with the Harmonic Mart Generator
for processing into term/regulation/process Knowledge Marts.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models.video import VideoData


class WarehouseStorage:
    """
    Store collected video data in Harmonic Mart Generator warehouse format.

    This storage adapter creates:
    1. Individual .txt files for each video transcript
    2. A warehouse_manifest.json with metadata for all collected videos
    """

    def __init__(
        self,
        warehouse_dir: str = "data/warehouse/lectures",
        manifest_path: Optional[str] = None,
    ):
        """
        Initialize warehouse storage.

        Args:
            warehouse_dir: Directory to store transcript files.
            manifest_path: Path to warehouse_manifest.json.
                          Defaults to {warehouse_dir}/../warehouse_manifest.json
        """
        self.warehouse_dir = Path(warehouse_dir)
        self.manifest_path = Path(manifest_path) if manifest_path else (
            self.warehouse_dir.parent / "warehouse_manifest.json"
        )

    def save(self, videos: list[VideoData], generate_index: bool = True) -> dict:
        """
        Save video data to warehouse format.

        Creates:
        1. One .txt file per video in warehouse_dir
        2. Updates warehouse_manifest.json with metadata
        3. Updates INDEX.md with video list summary

        Args:
            videos: List of VideoData to save.
            generate_index: Whether to generate/update INDEX.md.

        Returns:
            Summary dict with save statistics.
        """
        # Ensure directories exist
        self.warehouse_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing manifest
        manifest = self._load_manifest()

        saved_files = []
        saved_videos = []
        skipped = 0
        errors = 0

        for video in videos:
            try:
                # Skip videos without transcript content
                if video.transcript.error or not video.transcript.full_text.strip():
                    errors += 1
                    continue

                filename = video.to_warehouse_filename()
                filepath = self.warehouse_dir / filename

                # Check if file already exists
                if filepath.exists():
                    skipped += 1
                    continue

                # Write transcript text file
                content = video.to_warehouse_text()
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Add to manifest
                manifest["files"][filename] = video.to_manifest_entry()
                saved_files.append(filename)
                saved_videos.append(video)

            except Exception as e:
                print(f"  Error saving {video.video_id}: {e}")
                errors += 1

        # Save updated manifest
        self._save_manifest(manifest)

        # Generate index file
        if generate_index:
            self._update_index(manifest)

        return {
            "warehouse_dir": str(self.warehouse_dir),
            "manifest_path": str(self.manifest_path),
            "index_path": str(self.warehouse_dir / "INDEX.md"),
            "saved": len(saved_files),
            "skipped": skipped,
            "errors": errors,
            "files": saved_files,
        }

    def _load_manifest(self) -> dict:
        """Load existing manifest or create new one."""
        if self.manifest_path.exists():
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        return {
            "version": "1.0.0",
            "description": "YouTube transcript warehouse manifest for Harmonic Mart Generator",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "files": {},
        }

    def _save_manifest(self, manifest: dict) -> None:
        """Save manifest to file."""
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _update_index(self, manifest: dict) -> None:
        """Generate INDEX.md with video list summary."""
        index_path = self.warehouse_dir / "INDEX.md"

        files_data = manifest.get("files", {})
        if not files_data:
            return

        # Group by channel
        by_channel: dict[str, list] = {}
        for filename, meta in files_data.items():
            channel = meta.get("channel", "Unknown")
            if channel not in by_channel:
                by_channel[channel] = []
            by_channel[channel].append({
                "filename": filename,
                "title": meta.get("source_title", ""),
                "upload_date": meta.get("upload_date", ""),
                "url": meta.get("source_url", ""),
                "observed_at": meta.get("observed_at", ""),
                "duration": meta.get("duration_seconds", 0),
                "views": meta.get("view_count", 0),
            })

        # Sort channels and videos
        sorted_channels = sorted(by_channel.keys())
        for channel in sorted_channels:
            by_channel[channel].sort(key=lambda x: x.get("upload_date", ""), reverse=True)

        # Generate markdown
        lines = [
            "# YouTube Transcript Warehouse Index",
            "",
            f"**更新日時**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"**総ファイル数**: {len(files_data)}",
            f"**チャンネル数**: {len(by_channel)}",
            "",
            "---",
            "",
        ]

        # Summary table
        lines.extend([
            "## 概要",
            "",
            "| チャンネル | 動画数 |",
            "|------------|--------|",
        ])
        for channel in sorted_channels:
            count = len(by_channel[channel])
            lines.append(f"| {channel} | {count} |")

        lines.extend(["", "---", ""])

        # Detailed list by channel
        lines.append("## 動画リスト")
        lines.append("")

        for channel in sorted_channels:
            videos = by_channel[channel]
            lines.append(f"### {channel}")
            lines.append("")
            lines.append("| 公開日 | タイトル | 再生時間 | URL |")
            lines.append("|--------|----------|----------|-----|")

            for v in videos:
                title = v["title"][:50] + "..." if len(v["title"]) > 50 else v["title"]
                duration = self._format_duration(v.get("duration", 0))
                url = v.get("url", "")
                upload = v.get("upload_date", "")
                lines.append(f"| {upload} | {title} | {duration} | [Link]({url}) |")

            lines.append("")

        # Write index file
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def _format_duration(self, seconds: int) -> str:
        """Format seconds as MM:SS or HH:MM:SS."""
        if not seconds:
            return "-"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def generate_index(self) -> str:
        """Generate or update INDEX.md from current manifest."""
        manifest = self._load_manifest()
        self._update_index(manifest)
        return str(self.warehouse_dir / "INDEX.md")

    def list_files(self) -> list[str]:
        """List all transcript files in warehouse."""
        if not self.warehouse_dir.exists():
            return []
        return sorted([f.name for f in self.warehouse_dir.glob("*.txt")])

    def get_manifest(self) -> dict:
        """Get the current manifest."""
        return self._load_manifest()
