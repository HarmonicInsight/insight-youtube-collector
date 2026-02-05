#!/usr/bin/env python3
"""
Command-line interface for Insight YouTube Collector.

Usage:
  iyc collect --url "https://youtube.com/watch?v=xxx"
  iyc collect --playlist "https://youtube.com/playlist?list=xxx" --max 20
  iyc collect --channel "@channelname" --warehouse
  iyc collect --search "建設DX AI活用" --max 10

Output modes:
  --output / -o : Save to JSON file (default: youtube_data.json)
  --warehouse   : Save to warehouse format for Harmonic Mart Generator
  --both        : Save to both JSON and warehouse formats
"""

import argparse
import sys
import os
from datetime import datetime

from . import __version__
from .collector import YouTubeCollector
from .config import Settings


def print_banner():
    """Print the CLI banner."""
    print("=" * 60)
    print(f"  Insight YouTube Collector v{__version__}")
    print("  Harmonic Insight Text Data Warehouse Tool")
    print("=" * 60)


def print_summary(info: dict, mode: str):
    """Print summary of collection/save operation."""
    if mode == "json":
        print(f"\n  Saved: {info.get('total_videos', 0)} videos")
        print(f"  Success: {info.get('successful', 0)} / Failed: {info.get('failed', 0)}")
    elif mode == "warehouse":
        print(f"\n  Warehouse: {info.get('warehouse_dir', '')}")
        print(f"  Saved: {info.get('saved', 0)} files")
        print(f"  Skipped: {info.get('skipped', 0)} (already exist)")
        if info.get('errors', 0) > 0:
            print(f"  Errors: {info.get('errors', 0)}")


def cmd_collect(args):
    """Handle the collect command."""
    print_banner()

    # Initialize collector
    settings = Settings(
        preferred_langs=['ja', 'en'],
        quiet_mode=args.quiet,
        use_cookies=not args.no_cookies,
        cookie_browser=args.browser,
    )
    collector = YouTubeCollector(settings)

    # Determine input source and collect
    videos = []

    if args.url:
        videos = collector.collect_from_urls(args.url, max_videos=args.max)
    elif args.playlist:
        videos = collector.collect_from_playlist(args.playlist, max_videos=args.max)
    elif args.channel:
        videos = collector.collect_from_channel(args.channel, max_videos=args.max)
    elif args.search:
        videos = collector.collect_from_search(args.search, max_videos=args.max)
    elif args.file:
        videos = collector.collect_from_file(args.file, max_videos=args.max)

    if not videos:
        print("\n  No videos collected.")
        return 1

    # Determine output mode
    save_json = args.output or (not args.warehouse) or args.both
    save_warehouse = args.warehouse or args.both

    # Save results
    if save_json:
        output_path = args.output or "youtube_data.json"
        info = collector.save_json(
            videos,
            output_path=output_path,
            append=args.append,
            pretty=not args.compact,
            include_segments=not args.no_segments,
        )
        file_size = os.path.getsize(output_path)
        print(f"\n  JSON saved: {output_path}")
        print(f"  File size: {file_size:,} bytes")
        print_summary(info, "json")

    if save_warehouse:
        warehouse_dir = args.warehouse_dir or "data/warehouse/lectures"
        info = collector.save_warehouse(videos, warehouse_dir=warehouse_dir)
        print(f"\n  Warehouse saved: {info['warehouse_dir']}")
        print(f"  Manifest: {info['manifest_path']}")
        print_summary(info, "warehouse")

    print("\n  Done!")
    return 0


def cmd_list(args):
    """Handle the list command to show warehouse contents."""
    from .storage import WarehouseStorage

    warehouse_dir = args.warehouse_dir or "data/warehouse/lectures"
    storage = WarehouseStorage(warehouse_dir=warehouse_dir)

    files = storage.list_files()
    manifest = storage.get_manifest()

    print(f"Warehouse: {warehouse_dir}")
    print(f"Files: {len(files)}")
    print("-" * 60)

    for f in files:
        meta = manifest.get("files", {}).get(f, {})
        title = meta.get("source_title", "(unknown)")[:50]
        observed = meta.get("observed_at", "")
        print(f"  {f[:60]}")
        if title:
            print(f"    -> {title}")

    return 0


def cmd_manifest(args):
    """Handle the manifest command to show manifest details."""
    import json
    from .storage import WarehouseStorage

    warehouse_dir = args.warehouse_dir or "data/warehouse/lectures"
    storage = WarehouseStorage(warehouse_dir=warehouse_dir)
    manifest = storage.get_manifest()

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"Warehouse Manifest")
        print(f"  Version: {manifest.get('version', 'unknown')}")
        print(f"  Created: {manifest.get('created_at', 'unknown')}")
        print(f"  Updated: {manifest.get('updated_at', 'unknown')}")
        print(f"  Files: {len(manifest.get('files', {}))}")

    return 0


def cmd_batch(args):
    """Handle the batch command for bulk collection."""
    from .batch import BatchConfig, BatchCollector

    print_banner()
    print("\n  BATCH COLLECTION MODE")
    print("=" * 60)

    # Load configuration
    try:
        if args.keywords:
            # Simple keywords file mode
            config = BatchConfig.from_keywords_file(
                args.keywords,
                max_per_keyword=args.max,
            )
            print(f"  Loaded {len(config.sources)} keywords from: {args.keywords}")
        elif args.urls:
            # URLs file mode (auto-detect playlists/channels/videos)
            config = BatchConfig.from_urls_file(args.urls)
            print(f"  Loaded {len(config.sources)} sources from: {args.urls}")
        elif args.config:
            # Full config file mode (YAML/JSON)
            config = BatchConfig.from_file(args.config)
            print(f"  Loaded {len(config.sources)} sources from: {args.config}")
        else:
            print("  Error: No input specified")
            return 1

        # Override output settings if specified
        if args.warehouse_dir:
            config.warehouse_dir = args.warehouse_dir
        if args.output:
            config.save_json = True
            config.json_path = args.output
        if args.no_warehouse:
            config.save_warehouse = False

        # Default to warehouse output
        if not config.save_json:
            config.save_warehouse = True

    except Exception as e:
        print(f"  Error loading config: {e}")
        return 1

    # Run batch collection
    collector = BatchCollector(config, verbose=not args.quiet)
    result = collector.collect_all()

    # Print summary
    print("\n" + "=" * 60)
    print("  BATCH SUMMARY")
    print("=" * 60)
    print(f"  Sources processed: {result['total_sources']}")
    print(f"  Total collected: {result['total_collected']}")
    print(f"  Unique videos: {result['unique_videos']}")
    print(f"  Duplicates removed: {result['duplicates_removed']}")

    if result.get('save_results', {}).get('warehouse'):
        wh = result['save_results']['warehouse']
        print(f"\n  Warehouse: {wh['warehouse_dir']}")
        print(f"    Saved: {wh['saved']} / Skipped: {wh['skipped']}")

    if result.get('save_results', {}).get('json'):
        print(f"\n  JSON: {config.json_path}")

    print("\n  Done!")
    return 0


def cmd_index(args):
    """Generate INDEX.md from warehouse manifest."""
    from .storage import WarehouseStorage

    warehouse_dir = args.warehouse_dir or "data/warehouse/lectures"
    storage = WarehouseStorage(warehouse_dir=warehouse_dir)

    try:
        index_path = storage.generate_index()
        print(f"INDEX.md generated: {index_path}")

        # Show summary
        manifest = storage.get_manifest()
        files = manifest.get("files", {})
        channels = set(f.get("channel", "") for f in files.values())

        print(f"  Total videos: {len(files)}")
        print(f"  Channels: {len(channels)}")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_gui(args):
    """Launch the Streamlit GUI."""
    import subprocess
    from pathlib import Path

    print_banner()
    print("\n  Launching GUI...")

    gui_path = Path(__file__).parent / "gui.py"

    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(gui_path),
             "--server.port", str(args.port)],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"  Error launching GUI: {e}")
        return 1
    except FileNotFoundError:
        print("  Error: Streamlit is not installed.")
        print("  Install it with: pip install insight-youtube-collector[gui]")
        return 1

    return 0


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog='iyc',
        description='Insight YouTube Collector - YouTube transcript collector for text data warehouse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect from a single video
  iyc collect --url "https://youtube.com/watch?v=xxx"

  # Collect from a playlist (max 20 videos)
  iyc collect --playlist "https://youtube.com/playlist?list=xxx" --max 20

  # Collect from a channel to warehouse format
  iyc collect --channel "@channelname" --warehouse --max 10

  # BATCH: Collect from multiple keywords at once
  iyc batch --keywords keywords.txt --max 10

  # BATCH: Collect from URL list (playlists, channels, videos)
  iyc batch --urls sources.txt

  # BATCH: Use full config file
  iyc batch --config batch_config.yaml

  # List warehouse contents
  iyc list

  # Show manifest
  iyc manifest --json

  # Generate INDEX.md summary
  iyc index

  # Launch GUI
  iyc gui
        """,
    )

    parser.add_argument('--version', '-v', action='version', version=f'%(prog)s {__version__}')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # collect command
    collect_parser = subparsers.add_parser('collect', help='Collect YouTube transcripts')

    # Input sources (mutually exclusive)
    source = collect_parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url', nargs='+', help='YouTube video URL(s)')
    source.add_argument('--playlist', help='YouTube playlist URL')
    source.add_argument('--channel', help='YouTube channel URL')
    source.add_argument('--search', help='YouTube search query')
    source.add_argument('--file', help='Text file with URLs (one per line)')

    # Output options
    collect_parser.add_argument('--output', '-o', help='Output JSON file path')
    collect_parser.add_argument('--warehouse', action='store_true',
                               help='Save to warehouse format (for Harmonic Mart Generator)')
    collect_parser.add_argument('--warehouse-dir', help='Warehouse directory (default: data/warehouse/lectures)')
    collect_parser.add_argument('--both', action='store_true',
                               help='Save to both JSON and warehouse formats')

    # Processing options
    collect_parser.add_argument('--max', type=int, default=20, help='Max videos to process (default: 20)')
    collect_parser.add_argument('--no-segments', action='store_true',
                               help='Omit timestamp segments (JSON only)')
    collect_parser.add_argument('--compact', action='store_true', help='Compact JSON output')
    collect_parser.add_argument('--append', action='store_true',
                               help='Append to existing JSON file (deduplicate)')
    collect_parser.add_argument('--quiet', '-q', action='store_true', help='Suppress progress output')
    collect_parser.add_argument('--browser', choices=['chrome', 'firefox', 'edge', 'safari', 'brave'],
                               default='chrome', help='Browser for cookie extraction (default: chrome)')
    collect_parser.add_argument('--no-cookies', action='store_true',
                               help='Do not use browser cookies (may cause rate limiting)')

    collect_parser.set_defaults(func=cmd_collect)

    # list command
    list_parser = subparsers.add_parser('list', help='List warehouse contents')
    list_parser.add_argument('--warehouse-dir', help='Warehouse directory')
    list_parser.set_defaults(func=cmd_list)

    # manifest command
    manifest_parser = subparsers.add_parser('manifest', help='Show warehouse manifest')
    manifest_parser.add_argument('--warehouse-dir', help='Warehouse directory')
    manifest_parser.add_argument('--json', action='store_true', help='Output as JSON')
    manifest_parser.set_defaults(func=cmd_manifest)

    # batch command
    batch_parser = subparsers.add_parser('batch', help='Batch collect from multiple sources')

    # Input (one required)
    batch_input = batch_parser.add_mutually_exclusive_group(required=True)
    batch_input.add_argument('--keywords', '-k',
                            help='Text file with search keywords (one per line)')
    batch_input.add_argument('--urls', '-u',
                            help='Text file with URLs (playlists/channels/videos)')
    batch_input.add_argument('--config', '-c',
                            help='YAML/JSON config file with full batch settings')

    # Output options
    batch_parser.add_argument('--output', '-o', help='Output JSON file path')
    batch_parser.add_argument('--warehouse-dir', help='Warehouse directory')
    batch_parser.add_argument('--no-warehouse', action='store_true',
                             help='Do not save to warehouse format')

    # Processing options
    batch_parser.add_argument('--max', type=int, default=10,
                             help='Max videos per source (default: 10)')
    batch_parser.add_argument('--quiet', '-q', action='store_true',
                             help='Suppress progress output')

    batch_parser.set_defaults(func=cmd_batch)

    # gui command
    gui_parser = subparsers.add_parser('gui', help='Launch web GUI (requires streamlit)')
    gui_parser.add_argument('--port', type=int, default=8501, help='Port number (default: 8501)')
    gui_parser.set_defaults(func=cmd_gui)

    # index command
    index_parser = subparsers.add_parser('index', help='Generate INDEX.md summary from warehouse')
    index_parser.add_argument('--warehouse-dir', help='Warehouse directory')
    index_parser.set_defaults(func=cmd_index)

    # Parse arguments
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Execute command
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
