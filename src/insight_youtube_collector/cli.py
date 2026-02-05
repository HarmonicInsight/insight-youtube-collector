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

  # Collect from multiple videos
  iyc collect --url "URL1" "URL2" "URL3"

  # Collect from a playlist (max 20 videos)
  iyc collect --playlist "https://youtube.com/playlist?list=xxx" --max 20

  # Collect from a channel to warehouse format
  iyc collect --channel "@channelname" --warehouse --max 10

  # Collect from search results
  iyc collect --search "建設DX AI活用" --max 10

  # Collect to both JSON and warehouse formats
  iyc collect --url "URL" --both

  # List warehouse contents
  iyc list

  # Show manifest
  iyc manifest --json
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

    # Parse arguments
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Execute command
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
