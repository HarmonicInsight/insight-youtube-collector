"""
Configuration settings for Insight YouTube Collector.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Settings:
    """Configuration settings for the YouTube collector."""

    # Language preferences for transcript extraction
    preferred_langs: list[str] = field(default_factory=lambda: ['ja', 'en'])

    # Default output settings
    default_output_path: str = "youtube_data.json"
    default_warehouse_dir: str = "data/warehouse/lectures"

    # Processing limits
    default_max_videos: int = 20

    # Output format options
    include_segments: bool = True
    pretty_json: bool = True

    # Behavior
    quiet_mode: bool = False

    # Cookie settings for rate limit bypass
    use_cookies: bool = True
    cookie_browser: Optional[str] = None  # 'chrome', 'firefox', 'edge', etc.

    def to_dict(self) -> dict:
        return {
            "preferred_langs": self.preferred_langs,
            "default_output_path": self.default_output_path,
            "default_warehouse_dir": self.default_warehouse_dir,
            "default_max_videos": self.default_max_videos,
            "include_segments": self.include_segments,
            "pretty_json": self.pretty_json,
            "quiet_mode": self.quiet_mode,
            "use_cookies": self.use_cookies,
            "cookie_browser": self.cookie_browser,
        }


DEFAULT_SETTINGS = Settings()
