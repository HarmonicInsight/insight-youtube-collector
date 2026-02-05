"""
Transcript extraction from YouTube videos.

Extracts subtitles/captions with language priority:
1. Manual Japanese subtitles
2. Auto-generated Japanese subtitles
3. Manual English subtitles
4. Auto-generated English subtitles
5. Any available subtitle
"""

from typing import Optional
from ..models.video import TranscriptData, TranscriptSegment

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False


class TranscriptExtractor:
    """Extract transcripts from YouTube videos."""

    def __init__(self, preferred_langs: Optional[list[str]] = None):
        """
        Initialize the transcript extractor.

        Args:
            preferred_langs: List of language codes in priority order.
                           Defaults to ['ja', 'en'].
        """
        if not TRANSCRIPT_API_AVAILABLE:
            raise ImportError(
                "youtube-transcript-api is not installed. "
                "Install it with: pip install youtube-transcript-api"
            )
        self.preferred_langs = preferred_langs or ['ja', 'en']

    def extract(self, video_id: str) -> TranscriptData:
        """
        Extract transcript from a YouTube video.

        Args:
            video_id: YouTube video ID (11 characters).

        Returns:
            TranscriptData with extracted transcript or error information.
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Try manual transcripts first
            for lang in self.preferred_langs:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    segments = transcript.fetch()
                    return self._format_transcript(segments, lang, is_generated=False)
                except NoTranscriptFound:
                    pass

            # Try auto-generated transcripts
            for lang in self.preferred_langs:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    segments = transcript.fetch()
                    return self._format_transcript(segments, lang, is_generated=True)
                except NoTranscriptFound:
                    pass

            # Fallback: any available transcript
            for transcript in transcript_list:
                segments = transcript.fetch()
                return self._format_transcript(
                    segments,
                    transcript.language_code,
                    is_generated=transcript.is_generated,
                )

        except TranscriptsDisabled:
            return TranscriptData(
                language="",
                is_generated=False,
                segments=[],
                full_text="",
                error="字幕が無効化されています",
            )
        except VideoUnavailable:
            return TranscriptData(
                language="",
                is_generated=False,
                segments=[],
                full_text="",
                error="動画が利用できません",
            )
        except Exception as e:
            return TranscriptData(
                language="",
                is_generated=False,
                segments=[],
                full_text="",
                error=str(e),
            )

        return TranscriptData(
            language="",
            is_generated=False,
            segments=[],
            full_text="",
            error="字幕が見つかりません",
        )

    def _format_transcript(
        self,
        raw_segments: list,
        language: str,
        is_generated: bool,
    ) -> TranscriptData:
        """Format raw transcript segments into structured data."""
        segments = []
        full_text_parts = []

        for seg in raw_segments:
            # Handle different segment formats
            if hasattr(seg, 'text'):
                text = seg.text
                start = getattr(seg, 'start', 0)
                duration = getattr(seg, 'duration', 0)
            elif isinstance(seg, dict):
                text = seg.get('text', '')
                start = seg.get('start', 0)
                duration = seg.get('duration', 0)
            else:
                text = str(seg)
                start = 0
                duration = 0

            clean_text = text.replace('\n', ' ').strip()
            if clean_text:
                segments.append(TranscriptSegment(
                    start=start,
                    duration=duration,
                    text=clean_text,
                ))
                full_text_parts.append(clean_text)

        return TranscriptData(
            language=language,
            is_generated=is_generated,
            segments=segments,
            full_text=' '.join(full_text_parts),
        )
