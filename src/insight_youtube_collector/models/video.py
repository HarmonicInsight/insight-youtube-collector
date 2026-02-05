"""
Video data models for YouTube transcript collection.

These models are designed to be compatible with the Harmonic Mart Generator
warehouse schema and MartItem v0.2 specification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import re


@dataclass
class TranscriptSegment:
    """A single segment of a transcript with timing information."""
    start: float
    duration: float
    text: str

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 2),
            "duration": round(self.duration, 2),
            "text": self.text,
        }


@dataclass
class TranscriptData:
    """Transcript data extracted from a YouTube video."""
    language: str
    is_generated: bool
    segments: list[TranscriptSegment]
    full_text: str
    error: Optional[str] = None

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def to_dict(self, include_segments: bool = True) -> dict:
        result = {
            "language": self.language,
            "is_generated": self.is_generated,
            "segment_count": self.segment_count,
            "full_text": self.full_text,
        }
        if self.error:
            result["error"] = self.error
        if include_segments:
            result["segments"] = [s.to_dict() for s in self.segments]
        return result


@dataclass
class VideoMetadata:
    """Metadata for a YouTube video."""
    title: str
    channel: str
    channel_id: str
    upload_date: str  # YYYYMMDD format
    duration_seconds: int
    view_count: int
    like_count: int
    description: str
    tags: list[str]
    categories: list[str]
    thumbnail_url: str

    @property
    def upload_date_iso(self) -> str:
        """Convert YYYYMMDD to ISO date format."""
        if len(self.upload_date) == 8:
            return f"{self.upload_date[:4]}-{self.upload_date[4:6]}-{self.upload_date[6:8]}"
        return self.upload_date

    @property
    def safe_filename_title(self) -> str:
        """Generate a filesystem-safe version of the title."""
        # Remove or replace unsafe characters
        safe = re.sub(r'[\\/:*?"<>|]', '', self.title)
        safe = re.sub(r'\s+', '_', safe)
        # Limit length
        return safe[:80] if len(safe) > 80 else safe

    @property
    def safe_channel_name(self) -> str:
        """Generate a filesystem-safe version of the channel name."""
        safe = re.sub(r'[\\/:*?"<>|@]', '', self.channel)
        safe = re.sub(r'\s+', '_', safe)
        return safe[:40] if len(safe) > 40 else safe

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "channel": self.channel,
            "channel_id": self.channel_id,
            "upload_date": self.upload_date,
            "duration_seconds": self.duration_seconds,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "description": self.description,
            "tags": self.tags,
            "categories": self.categories,
            "thumbnail_url": self.thumbnail_url,
        }


@dataclass
class VideoData:
    """Complete data for a YouTube video including metadata and transcript."""
    video_id: str
    url: str
    crawled_at: datetime
    metadata: VideoMetadata
    transcript: TranscriptData

    @classmethod
    def create(cls, video_id: str, metadata: VideoMetadata, transcript: TranscriptData) -> "VideoData":
        return cls(
            video_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            crawled_at=datetime.now(timezone.utc),
            metadata=metadata,
            transcript=transcript,
        )

    def to_dict(self, include_segments: bool = True) -> dict:
        return {
            "video_id": self.video_id,
            "url": self.url,
            "crawled_at": self.crawled_at.isoformat(),
            "metadata": self.metadata.to_dict(),
            "transcript": self.transcript.to_dict(include_segments),
        }

    def to_warehouse_filename(self) -> str:
        """
        Generate a warehouse-compatible filename.
        Format: {YYYY-MM-DD}_lecture_{channel}_{title}.txt
        """
        date = self.metadata.upload_date_iso
        channel = self.metadata.safe_channel_name
        title = self.metadata.safe_filename_title
        return f"{date}_lecture_{channel}_{title}.txt"

    def to_warehouse_text(self) -> str:
        """
        Generate warehouse-compatible text content.
        Includes metadata headers for Harmonic Mart Generator processing.
        """
        lines = [
            f"## {self.metadata.title}",
            "",
            f"チャンネル: {self.metadata.channel}",
            f"公開日: {self.metadata.upload_date_iso}",
            f"URL: {self.url}",
            "",
            "---",
            "",
        ]

        # Add transcript text
        if self.transcript.full_text:
            lines.append(self.transcript.full_text)
        elif self.transcript.error:
            lines.append(f"[字幕取得エラー: {self.transcript.error}]")

        return "\n".join(lines)

    def to_manifest_entry(self) -> dict:
        """
        Generate a warehouse_manifest.json entry for this video.
        Compatible with Harmonic Mart Generator manifest schema.
        """
        return {
            "observed_at": self.crawled_at.strftime("%Y-%m-%d"),
            "source_type": "lecture",
            "source_title": self.metadata.title,
            "source_url": self.url,
            "channel": self.metadata.channel,
            "channel_id": self.metadata.channel_id,
            "upload_date": self.metadata.upload_date_iso,
            "duration_seconds": self.metadata.duration_seconds,
            "language": self.transcript.language,
            "is_auto_generated": self.transcript.is_generated,
            "view_count": self.metadata.view_count,
            "tags": self.metadata.tags,
        }
