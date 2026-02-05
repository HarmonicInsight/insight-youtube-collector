"""
Transcript extraction from YouTube videos.

Uses yt-dlp as primary method (more reliable) with youtube-transcript-api as fallback.

Extracts subtitles/captions with language priority:
1. Manual Japanese subtitles
2. Auto-generated Japanese subtitles
3. Manual English subtitles
4. Auto-generated English subtitles
5. Any available subtitle
"""

import json
import os
import re
import tempfile
import time
from typing import Optional
from ..models.video import TranscriptData, TranscriptSegment

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False


class TranscriptExtractor:
    """Extract transcripts from YouTube videos."""

    def __init__(
        self,
        preferred_langs: Optional[list[str]] = None,
        quiet: bool = True,
        use_cookies: bool = True,
        cookie_browser: Optional[str] = None,
    ):
        """
        Initialize the transcript extractor.

        Args:
            preferred_langs: List of language codes in priority order.
                           Defaults to ['ja', 'en'].
            quiet: Suppress yt-dlp output.
            use_cookies: Use browser cookies to avoid rate limiting.
            cookie_browser: Browser to extract cookies from ('chrome', 'firefox', 'edge', etc.)
                          If None, tries to auto-detect.
        """
        if not YT_DLP_AVAILABLE:
            raise ImportError(
                "yt-dlp is not installed. "
                "Install it with: pip install yt-dlp"
            )
        self.preferred_langs = preferred_langs or ['ja', 'en']
        self.quiet = quiet
        self.use_cookies = use_cookies
        self.cookie_browser = cookie_browser

    def extract(self, video_id: str) -> TranscriptData:
        """
        Extract transcript from a YouTube video.

        Args:
            video_id: YouTube video ID (11 characters).

        Returns:
            TranscriptData with extracted transcript or error information.
        """
        # Try yt-dlp first (more reliable)
        result = self._extract_with_ytdlp(video_id)
        if result and not result.error:
            return result

        # Fallback to youtube-transcript-api
        if TRANSCRIPT_API_AVAILABLE:
            result = self._extract_with_api(video_id)
            if result and not result.error:
                return result

        # Return error
        return TranscriptData(
            language="",
            is_generated=False,
            segments=[],
            full_text="",
            error="字幕を取得できませんでした",
        )

    def _extract_with_ytdlp(self, video_id: str, retry_count: int = 0) -> Optional[TranscriptData]:
        """Extract transcript using yt-dlp with retry on rate limit."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        max_retries = 5

        # Create temp directory for subtitle files
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                'quiet': self.quiet,
                'no_warnings': self.quiet,
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': self.preferred_langs,
                'subtitlesformat': 'json3',
                'outtmpl': os.path.join(tmpdir, '%(id)s'),
                'nocheckcertificate': True,
                'socket_timeout': 30,
            }

            # Add cookie support to bypass rate limiting
            use_cookies_this_time = self.use_cookies
            if use_cookies_this_time:
                browser = self.cookie_browser or 'chrome'
                ydl_opts['cookiesfrombrowser'] = (browser,)

            try:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                except Exception as e:
                    error_msg = str(e).lower()
                    # If cookie error, retry without cookies
                    if 'cookie' in error_msg and use_cookies_this_time:
                        if not self.quiet:
                            print(f"     Cookie取得失敗、Cookieなしで再試行...")
                        if 'cookiesfrombrowser' in ydl_opts:
                            del ydl_opts['cookiesfrombrowser']
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=True)
                    else:
                        raise

                # Find downloaded subtitle file
                for lang in self.preferred_langs:
                    sub_file = os.path.join(tmpdir, f"{video_id}.{lang}.json3")
                    if os.path.exists(sub_file):
                        return self._parse_json3_subtitles(sub_file, lang, is_generated=False)

                # Check for auto-generated subtitles
                for lang in self.preferred_langs:
                    sub_file = os.path.join(tmpdir, f"{video_id}.{lang}.json3")
                    if os.path.exists(sub_file):
                        return self._parse_json3_subtitles(sub_file, lang, is_generated=True)

                # Check for any subtitle file
                for f in os.listdir(tmpdir):
                    if f.endswith('.json3'):
                        match = re.search(r'\.([a-z]{2}(-[A-Z]{2})?)\.json3$', f)
                        lang = match.group(1) if match else 'unknown'
                        return self._parse_json3_subtitles(
                            os.path.join(tmpdir, f), lang, is_generated=True
                        )

            except Exception as e:
                error_msg = str(e)
                # Retry on rate limit (429) with exponential backoff
                if '429' in error_msg and retry_count < max_retries:
                    wait_time = (2 ** retry_count) * 15  # 15, 30, 60, 120, 240 seconds
                    if not self.quiet:
                        print(f"     Rate limited (429), waiting {wait_time}s before retry {retry_count + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    return self._extract_with_ytdlp(video_id, retry_count + 1)
                if 'subtitles' in error_msg.lower():
                    return None
                return None

        return None

    def _parse_json3_subtitles(
        self, filepath: str, language: str, is_generated: bool
    ) -> TranscriptData:
        """Parse json3 format subtitle file."""
        segments = []
        full_text_parts = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            events = data.get('events', [])
            for event in events:
                # Skip events without segments
                segs = event.get('segs', [])
                if not segs:
                    continue

                start_ms = event.get('tStartMs', 0)
                duration_ms = event.get('dDurationMs', 0)

                # Combine all segments in this event
                text_parts = []
                for seg in segs:
                    text = seg.get('utf8', '')
                    if text and text.strip():
                        text_parts.append(text)

                combined_text = ''.join(text_parts).replace('\n', ' ').strip()
                if combined_text:
                    segments.append(TranscriptSegment(
                        start=start_ms / 1000.0,
                        duration=duration_ms / 1000.0,
                        text=combined_text,
                    ))
                    full_text_parts.append(combined_text)

        except Exception as e:
            return TranscriptData(
                language="",
                is_generated=False,
                segments=[],
                full_text="",
                error=f"字幕ファイル解析エラー: {e}",
            )

        return TranscriptData(
            language=language,
            is_generated=is_generated,
            segments=segments,
            full_text=' '.join(full_text_parts),
            error="字幕ファイルにテキストが含まれていません" if not full_text_parts else None,
        )

    def _extract_with_api(self, video_id: str) -> Optional[TranscriptData]:
        """Extract transcript using youtube-transcript-api (fallback)."""
        if not TRANSCRIPT_API_AVAILABLE:
            return None

        try:
            api = YouTubeTranscriptApi()

            # Try preferred languages
            for lang in self.preferred_langs:
                try:
                    transcript = api.fetch(video_id, languages=[lang])
                    return self._format_transcript(transcript, lang, is_generated=False)
                except Exception:
                    pass

            # Try with all preferred languages
            try:
                transcript = api.fetch(video_id, languages=self.preferred_langs)
                lang = self.preferred_langs[0] if self.preferred_langs else 'unknown'
                return self._format_transcript(transcript, lang, is_generated=False)
            except Exception:
                pass

            # Try to list and get any available
            try:
                transcript_list = api.list(video_id)
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

        except Exception:
            pass

        return None

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
            error="字幕ファイルにテキストが含まれていません" if not full_text_parts else None,
        )
