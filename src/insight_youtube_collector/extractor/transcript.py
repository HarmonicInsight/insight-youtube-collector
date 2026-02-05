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
        self._api = YouTubeTranscriptApi()

    def extract(self, video_id: str) -> TranscriptData:
        """
        Extract transcript from a YouTube video.

        Args:
            video_id: YouTube video ID (11 characters).

        Returns:
            TranscriptData with extracted transcript or error information.
        """
        # Try preferred languages first using the new API
        for lang in self.preferred_langs:
            try:
                transcript = self._api.fetch(video_id, languages=[lang])
                return self._format_transcript(transcript, lang, is_generated=False)
            except Exception:
                pass

        # Try with all preferred languages at once (API will pick best match)
        try:
            transcript = self._api.fetch(video_id, languages=self.preferred_langs)
            detected_lang = self.preferred_langs[0] if self.preferred_langs else 'unknown'
            return self._format_transcript(transcript, detected_lang, is_generated=False)
        except Exception:
            pass

        # Try to list available transcripts and get any available
        try:
            transcript_list = self._api.list(video_id)
            for transcript_info in transcript_list:
                try:
                    transcript = transcript_info.fetch()
                    lang_code = getattr(transcript_info, 'language_code', 'auto')
                    is_gen = getattr(transcript_info, 'is_generated', True)
                    return self._format_transcript(transcript, lang_code, is_generated=is_gen)
                except Exception:
                    continue
        except Exception:
            pass

        # Last resort: try with default 'en'
        try:
            transcript = self._api.fetch(video_id, languages=['en'])
            return self._format_transcript(transcript, 'en', is_generated=True)
        except Exception as e:
            error_msg = str(e)
            if 'disabled' in error_msg.lower():
                return TranscriptData(
                    language="",
                    is_generated=False,
                    segments=[],
                    full_text="",
                    error="字幕が無効化されています",
                )
            elif 'unavailable' in error_msg.lower():
                return TranscriptData(
                    language="",
                    is_generated=False,
                    segments=[],
                    full_text="",
                    error="動画が利用できません",
                )
            else:
                return TranscriptData(
                    language="",
                    is_generated=False,
                    segments=[],
                    full_text="",
                    error=f"字幕取得エラー: {error_msg}",
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
