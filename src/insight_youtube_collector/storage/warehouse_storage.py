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

    def save(self, videos: list[VideoData]) -> dict:
        """
        Save video data to warehouse format.

        Creates:
        1. One .txt file per video in warehouse_dir
        2. Updates warehouse_manifest.json with metadata

        Args:
            videos: List of VideoData to save.

        Returns:
            Summary dict with save statistics.
        """
        # Ensure directories exist
        self.warehouse_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing manifest
        manifest = self._load_manifest()

        saved_files = []
        skipped = 0
        errors = 0

        for video in videos:
            try:
                if video.transcript.error:
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

            except Exception as e:
                print(f"  Error saving {video.video_id}: {e}")
                errors += 1

        # Save updated manifest
        self._save_manifest(manifest)

        return {
            "warehouse_dir": str(self.warehouse_dir),
            "manifest_path": str(self.manifest_path),
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

    def list_files(self) -> list[str]:
        """List all transcript files in warehouse."""
        if not self.warehouse_dir.exists():
            return []
        return sorted([f.name for f in self.warehouse_dir.glob("*.txt")])

    def get_manifest(self) -> dict:
        """Get the current manifest."""
        return self._load_manifest()
