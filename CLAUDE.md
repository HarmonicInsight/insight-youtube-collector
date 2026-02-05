# Insight YouTube Collector - Development Guide

## Overview

This tool collects YouTube video transcripts for the Harmonic Insight text data warehouse. It outputs data compatible with the **Harmonic Mart Generator** for Knowledge Mart creation.

## Architecture

```
insight-youtube-collector/
├── src/insight_youtube_collector/
│   ├── __init__.py          # Package entry, exports main classes
│   ├── cli.py               # Command-line interface (iyc command)
│   ├── collector.py         # Main collector orchestrator
│   ├── extractor/           # Data extraction modules
│   │   ├── transcript.py    # YouTube transcript extraction
│   │   ├── metadata.py      # Video metadata extraction (yt-dlp)
│   │   └── video_source.py  # URL/playlist/channel parsing
│   ├── storage/             # Output storage adapters
│   │   ├── json_storage.py  # JSON file output
│   │   └── warehouse_storage.py  # Harmonic Mart Generator format
│   ├── models/              # Data models
│   │   └── video.py         # VideoData, TranscriptData, etc.
│   └── config/              # Configuration
│       └── settings.py      # Settings dataclass
├── schemas/                 # JSON schemas
├── tests/                   # Test files
├── data/                    # Data directory (gitignored)
│   ├── warehouse/lectures/  # Warehouse output
│   └── output/              # JSON output
└── pyproject.toml           # Package configuration
```

## Integration with Harmonic Insight Ecosystem

### tool-mart-generator (Harmonic Mart Generator)

This collector outputs to the **warehouse format** compatible with HMG:

**File naming**: `{YYYY-MM-DD}_lecture_{channel}_{title}.txt`
**Location**: `data/warehouse/lectures/`
**Manifest**: `data/warehouse/warehouse_manifest.json`

The warehouse files can then be processed by HMG to create Knowledge Marts:
- `term`: 用語定義
- `regulation`: 法令・基準
- `process`: 作業手順

### lib-insight-common

Future integration points:
- Error handling patterns
- i18n support
- Utility functions

## Commands

```bash
# Install
pip install -e .

# Collect transcripts
iyc collect --url "https://youtube.com/watch?v=xxx"
iyc collect --playlist "https://youtube.com/playlist?list=xxx" --max 20
iyc collect --channel "@channelname" --warehouse --max 10
iyc collect --search "建設DX AI活用" --max 10

# Save to warehouse format (for HMG)
iyc collect --url "URL" --warehouse
iyc collect --url "URL" --both  # JSON + warehouse

# List warehouse contents
iyc list
iyc manifest --json
```

## Output Formats

### JSON Format (default)

```json
{
  "crawl_info": {
    "tool": "Insight YouTube Collector",
    "version": "1.0.0",
    "crawled_at": "2026-02-05T12:00:00+00:00",
    "total_videos": 5,
    "successful": 4,
    "failed": 1
  },
  "videos": [
    {
      "video_id": "xxx",
      "url": "https://www.youtube.com/watch?v=xxx",
      "metadata": {...},
      "transcript": {
        "language": "ja",
        "is_generated": true,
        "full_text": "...",
        "segments": [...]
      }
    }
  ]
}
```

### Warehouse Format (for HMG)

**Text file**: `2025-01-15_lecture_ChannelName_VideoTitle.txt`

```markdown
## Video Title

チャンネル: Channel Name
公開日: 2025-01-15
URL: https://www.youtube.com/watch?v=xxx

---

[transcript text content...]
```

**Manifest entry** in `warehouse_manifest.json`:

```json
{
  "files": {
    "2025-01-15_lecture_ChannelName_VideoTitle.txt": {
      "observed_at": "2026-02-05",
      "source_type": "lecture",
      "source_title": "Video Title",
      "channel": "Channel Name",
      "upload_date": "2025-01-15",
      "language": "ja",
      "is_auto_generated": true
    }
  }
}
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking (if using mypy)
mypy src/
```

## Dependencies

- `youtube-transcript-api`: Transcript extraction
- `yt-dlp`: Metadata extraction, playlist/channel parsing

## Migration from youtube_crawler.py

The original `youtube_crawler.py` single-file script has been refactored into this package structure. Key differences:

1. **Modular architecture**: Separate extractors, storage, models
2. **Multiple output formats**: JSON + warehouse
3. **HMG integration**: Direct warehouse format support
4. **CLI subcommands**: `collect`, `list`, `manifest`
5. **Package installation**: `pip install -e .` provides `iyc` command
