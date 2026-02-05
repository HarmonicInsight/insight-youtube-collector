"""Tests for video data models."""

import pytest
from datetime import datetime, timezone

from insight_youtube_collector.models.video import (
    VideoData,
    VideoMetadata,
    TranscriptData,
    TranscriptSegment,
)


class TestTranscriptSegment:
    def test_to_dict(self):
        segment = TranscriptSegment(start=10.5, duration=5.25, text="Hello world")
        result = segment.to_dict()

        assert result["start"] == 10.5
        assert result["duration"] == 5.25
        assert result["text"] == "Hello world"


class TestTranscriptData:
    def test_segment_count(self):
        segments = [
            TranscriptSegment(0, 1, "One"),
            TranscriptSegment(1, 1, "Two"),
            TranscriptSegment(2, 1, "Three"),
        ]
        transcript = TranscriptData(
            language="ja",
            is_generated=False,
            segments=segments,
            full_text="One Two Three",
        )

        assert transcript.segment_count == 3

    def test_to_dict_with_segments(self):
        segments = [TranscriptSegment(0, 1, "Test")]
        transcript = TranscriptData(
            language="ja",
            is_generated=True,
            segments=segments,
            full_text="Test",
        )

        result = transcript.to_dict(include_segments=True)

        assert result["language"] == "ja"
        assert result["is_generated"] is True
        assert "segments" in result

    def test_to_dict_without_segments(self):
        segments = [TranscriptSegment(0, 1, "Test")]
        transcript = TranscriptData(
            language="en",
            is_generated=False,
            segments=segments,
            full_text="Test",
        )

        result = transcript.to_dict(include_segments=False)

        assert "segments" not in result


class TestVideoMetadata:
    def test_upload_date_iso(self):
        metadata = VideoMetadata(
            title="Test Video",
            channel="Test Channel",
            channel_id="UC123",
            upload_date="20250115",
            duration_seconds=300,
            view_count=1000,
            like_count=100,
            description="Test description",
            tags=["test"],
            categories=["Education"],
            thumbnail_url="https://example.com/thumb.jpg",
        )

        assert metadata.upload_date_iso == "2025-01-15"

    def test_safe_filename_title(self):
        metadata = VideoMetadata(
            title='Test: Video "Title" / Special <chars>',
            channel="Test",
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

        safe = metadata.safe_filename_title
        assert "/" not in safe
        assert ":" not in safe
        assert '"' not in safe
        assert "<" not in safe
        assert ">" not in safe

    def test_safe_channel_name(self):
        metadata = VideoMetadata(
            title="Test",
            channel="@Test Channel: Special",
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

        safe = metadata.safe_channel_name
        assert "@" not in safe
        assert ":" not in safe


class TestVideoData:
    def test_warehouse_filename(self):
        metadata = VideoMetadata(
            title="Test Video Title",
            channel="Test Channel",
            channel_id="UC123",
            upload_date="20250115",
            duration_seconds=300,
            view_count=1000,
            like_count=100,
            description="",
            tags=[],
            categories=[],
            thumbnail_url="",
        )
        transcript = TranscriptData(
            language="ja",
            is_generated=False,
            segments=[],
            full_text="Test content",
        )
        video = VideoData.create("abc12345678", metadata, transcript)

        filename = video.to_warehouse_filename()

        assert filename.startswith("2025-01-15_lecture_")
        assert filename.endswith(".txt")
        assert "Test_Channel" in filename

    def test_warehouse_text(self):
        metadata = VideoMetadata(
            title="Test Video",
            channel="Test Channel",
            channel_id="UC123",
            upload_date="20250115",
            duration_seconds=300,
            view_count=1000,
            like_count=100,
            description="",
            tags=[],
            categories=[],
            thumbnail_url="",
        )
        transcript = TranscriptData(
            language="ja",
            is_generated=False,
            segments=[],
            full_text="This is the transcript text.",
        )
        video = VideoData.create("abc12345678", metadata, transcript)

        text = video.to_warehouse_text()

        assert "## Test Video" in text
        assert "チャンネル: Test Channel" in text
        assert "This is the transcript text." in text

    def test_manifest_entry(self):
        metadata = VideoMetadata(
            title="Test Video",
            channel="Test Channel",
            channel_id="UC123",
            upload_date="20250115",
            duration_seconds=300,
            view_count=1000,
            like_count=100,
            description="",
            tags=["tag1", "tag2"],
            categories=[],
            thumbnail_url="",
        )
        transcript = TranscriptData(
            language="ja",
            is_generated=True,
            segments=[],
            full_text="Test",
        )
        video = VideoData.create("abc12345678", metadata, transcript)

        entry = video.to_manifest_entry()

        assert entry["source_type"] == "lecture"
        assert entry["source_title"] == "Test Video"
        assert entry["channel"] == "Test Channel"
        assert entry["is_auto_generated"] is True
        assert entry["tags"] == ["tag1", "tag2"]
