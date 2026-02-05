"""Tests for video source extractor."""

import pytest

from insight_youtube_collector.extractor.video_source import VideoSourceExtractor


class TestVideoSourceExtractor:
    """Tests for VideoSourceExtractor.extract_video_id method."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance (skip if yt-dlp not available)."""
        try:
            return VideoSourceExtractor(quiet=True)
        except ImportError:
            pytest.skip("yt-dlp not installed")

    def test_extract_standard_url(self, extractor):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extractor.extract_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_short_url(self, extractor):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extractor.extract_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_embed_url(self, extractor):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extractor.extract_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_bare_id(self, extractor):
        video_id = "dQw4w9WgXcQ"
        assert extractor.extract_video_id(video_id) == "dQw4w9WgXcQ"

    def test_extract_with_extra_params(self, extractor):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120"
        assert extractor.extract_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_invalid_url(self, extractor):
        url = "https://example.com/video"
        assert extractor.extract_video_id(url) is None

    def test_extract_from_urls(self, extractor):
        urls = [
            "https://www.youtube.com/watch?v=abc12345678",
            "https://youtu.be/def12345678",
            "invalid_url",
            "ghi12345678",
        ]
        result = extractor.extract_from_urls(urls)

        assert len(result) == 3
        assert "abc12345678" in result
        assert "def12345678" in result
        assert "ghi12345678" in result
