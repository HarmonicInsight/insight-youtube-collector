# Insight YouTube Collector

YouTube transcript collector for **Harmonic Insight Text Data Warehouse**.

This tool extracts YouTube video transcripts (subtitles) and outputs them in formats compatible with the [Harmonic Mart Generator](https://github.com/HarmonicInsight/tool-mart-generator) for Knowledge Mart creation.

## Features

- Extract transcripts from YouTube videos, playlists, channels, or search results
- Japanese subtitle priority (manual → auto-generated → English → any)
- Multiple output formats:
  - **JSON**: Full structured data with metadata and segments
  - **Warehouse**: Plain text files for Harmonic Mart Generator
- Automatic metadata extraction (title, channel, duration, views, etc.)
- Deduplication support for incremental collection

## Installation

```bash
# Clone the repository
git clone https://github.com/HarmonicInsight/insight-youtube-collector.git
cd insight-youtube-collector

# Install the package
pip install -e .

# Or install dependencies directly
pip install youtube-transcript-api yt-dlp
```

## Quick Start

```bash
# Collect from a single video
iyc collect --url "https://youtube.com/watch?v=xxx"

# Collect from a playlist
iyc collect --playlist "https://youtube.com/playlist?list=xxx" --max 20

# Collect from a channel (latest videos)
iyc collect --channel "https://youtube.com/@channelname" --max 10

# Collect from search results
iyc collect --search "建設DX AI活用" --max 10

# Save to warehouse format (for Harmonic Mart Generator)
iyc collect --url "URL" --warehouse

# Save to both JSON and warehouse
iyc collect --url "URL" --both
```

## Output Formats

### JSON Output (default)

```bash
iyc collect --url "URL" -o output.json
```

Output structure:
```json
{
  "crawl_info": {
    "tool": "Insight YouTube Collector",
    "version": "1.0.0",
    "total_videos": 5,
    "successful": 4
  },
  "videos": [
    {
      "video_id": "xxx",
      "metadata": { "title": "...", "channel": "..." },
      "transcript": { "full_text": "...", "language": "ja" }
    }
  ]
}
```

### Warehouse Output (for HMG)

```bash
iyc collect --url "URL" --warehouse
```

Creates:
- `data/warehouse/lectures/{date}_lecture_{channel}_{title}.txt`
- `data/warehouse/warehouse_manifest.json`

These files can be directly processed by Harmonic Mart Generator:

```bash
# In tool-mart-generator
hmg generate -i data/warehouse/lectures/*.txt -o data/marts
```

## Command Reference

### collect

```bash
iyc collect [options]

Input (one required):
  --url URL [URL ...]     YouTube video URL(s)
  --playlist URL          YouTube playlist URL
  --channel URL           YouTube channel URL
  --search QUERY          YouTube search query
  --file PATH             Text file with URLs (one per line)

Output:
  -o, --output PATH       Output JSON file (default: youtube_data.json)
  --warehouse             Save to warehouse format
  --warehouse-dir DIR     Warehouse directory (default: data/warehouse/lectures)
  --both                  Save to both JSON and warehouse

Options:
  --max N                 Max videos to process (default: 20)
  --no-segments           Omit timestamp segments in JSON
  --compact               Compact JSON output
  --append                Append to existing JSON file
  -q, --quiet             Suppress progress output
```

### list

```bash
iyc list [--warehouse-dir DIR]
```

List files in the warehouse.

### manifest

```bash
iyc manifest [--warehouse-dir DIR] [--json]
```

Show warehouse manifest information.

## Integration with Harmonic Insight Ecosystem

### Harmonic Mart Generator

The warehouse output is designed for direct use with HMG:

1. Collect transcripts: `iyc collect --channel "@example" --warehouse`
2. Generate marts: `hmg generate -i data/warehouse/lectures/*.txt -o data/marts`
3. Use marts for RAG, search, or analysis

### lib-insight-common

This tool follows patterns from lib-insight-common for:
- Error handling
- Configuration management
- Data model design

## Use Cases

- **AI Summarization**: Extract text for LLM-based summarization
- **Knowledge Base**: Build searchable knowledge from video content
- **Research**: Collect domain-specific video transcripts
- **Training Data**: Prepare text data for ML models
- **Content Analysis**: Analyze channel content over time

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## License

MIT License - Harmonic Insight LLC
