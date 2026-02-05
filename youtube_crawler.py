#!/usr/bin/env python3
"""
YouTube Transcript Crawler
- YouTube動画の字幕（トランスクリプト）をテキスト抽出してJSONに保存するツール
- 単一動画URL、複数URL一括、チャンネル/プレイリストに対応
- 日本語字幕を優先取得（なければ自動生成字幕→英語の順でフォールバック）

Usage:
  python youtube_crawler.py --url "https://www.youtube.com/watch?v=XXXXX"
  python youtube_crawler.py --url "URL1" "URL2" "URL3"
  python youtube_crawler.py --playlist "https://www.youtube.com/playlist?list=XXXXX"
  python youtube_crawler.py --channel "https://www.youtube.com/@channelname" --max 20
  python youtube_crawler.py --file urls.txt
  python youtube_crawler.py --search "建設DX AI活用" --max 10
"""

import argparse
import json
import os
import re
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
    )
except ImportError:
    print("ERROR: youtube-transcript-api が未インストールです")
    print("  pip install youtube-transcript-api")
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp が未インストールです")
    print("  pip install yt-dlp")
    sys.exit(1)


# ─────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────

def extract_video_id(url: str) -> str | None:
    """URLからYouTube動画IDを抽出"""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',  # bare 11-char ID only
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def get_video_metadata(video_id: str) -> dict:
    """yt-dlpで動画メタデータを取得"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'no_check_certificates': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', ''),
                'channel': info.get('channel', '') or info.get('uploader', ''),
                'channel_id': info.get('channel_id', ''),
                'upload_date': info.get('upload_date', ''),
                'duration_seconds': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'description': info.get('description', ''),
                'tags': info.get('tags', []) or [],
                'categories': info.get('categories', []) or [],
                'thumbnail_url': info.get('thumbnail', ''),
            }
    except Exception as e:
        print(f"  ⚠ メタデータ取得エラー: {e}")
        return {}


def get_transcript(video_id: str, preferred_langs: list[str] = None) -> dict:
    """
    字幕テキストを取得。
    優先順位: 手動字幕(ja) → 自動生成字幕(ja) → 手動字幕(en) → 自動生成字幕(en) → 最初に見つかったもの
    """
    if preferred_langs is None:
        preferred_langs = ['ja', 'en']

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # 手動字幕を優先的に探す
        for lang in preferred_langs:
            try:
                transcript = transcript_list.find_transcript([lang])
                segments = transcript.fetch()
                return _format_transcript(segments, lang, is_generated=False)
            except NoTranscriptFound:
                pass

        # 自動生成字幕を探す
        for lang in preferred_langs:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                segments = transcript.fetch()
                return _format_transcript(segments, lang, is_generated=True)
            except NoTranscriptFound:
                pass

        # どの言語でもいいので取得
        for transcript in transcript_list:
            segments = transcript.fetch()
            return _format_transcript(
                segments,
                transcript.language_code,
                is_generated=transcript.is_generated,
            )

    except TranscriptsDisabled:
        return {'error': '字幕が無効化されています', 'segments': [], 'full_text': ''}
    except VideoUnavailable:
        return {'error': '動画が利用できません', 'segments': [], 'full_text': ''}
    except Exception as e:
        return {'error': str(e), 'segments': [], 'full_text': ''}

    return {'error': '字幕が見つかりません', 'segments': [], 'full_text': ''}


def _format_transcript(segments, language: str, is_generated: bool) -> dict:
    """トランスクリプトデータを整形"""
    formatted_segments = []
    full_text_parts = []

    for seg in segments:
        # youtube_transcript_api v1.x ではオブジェクトの場合あり
        if hasattr(seg, 'text'):
            text = seg.text
            start = getattr(seg, 'start', 0)
            duration = getattr(seg, 'duration', 0)
        elif isinstance(seg, dict):
            text = seg.get('text', '')
            start = seg.get('start', 0)
            duration = seg.get('duration', 0)
        else:
            # FetchedTranscriptSnippet の場合
            text = str(seg)
            start = 0
            duration = 0

        clean_text = text.replace('\n', ' ').strip()
        if clean_text:
            formatted_segments.append({
                'start': round(start, 2),
                'duration': round(duration, 2),
                'text': clean_text,
            })
            full_text_parts.append(clean_text)

    return {
        'language': language,
        'is_generated': is_generated,
        'segment_count': len(formatted_segments),
        'segments': formatted_segments,
        'full_text': ' '.join(full_text_parts),
    }


def format_duration(seconds: int) -> str:
    """秒数をHH:MM:SS形式に"""
    if not seconds:
        return "不明"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ─────────────────────────────────────────
# 動画リスト取得
# ─────────────────────────────────────────

def get_playlist_video_ids(playlist_url: str, max_videos: int = 50) -> list[str]:
    """プレイリストから動画IDリストを取得"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'playlistend': max_videos,
    }
    video_ids = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get('entries', [])
            for entry in entries:
                vid = entry.get('id')
                if vid:
                    video_ids.append(vid)
    except Exception as e:
        print(f"  ⚠ プレイリスト取得エラー: {e}")
    return video_ids[:max_videos]


def get_channel_video_ids(channel_url: str, max_videos: int = 20) -> list[str]:
    """チャンネルから最新動画IDリストを取得"""
    # チャンネルURLを /videos に正規化
    if not channel_url.endswith('/videos'):
        channel_url = channel_url.rstrip('/') + '/videos'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'playlistend': max_videos,
    }
    video_ids = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            entries = info.get('entries', [])
            for entry in entries:
                vid = entry.get('id')
                if vid:
                    video_ids.append(vid)
    except Exception as e:
        print(f"  ⚠ チャンネル取得エラー: {e}")
    return video_ids[:max_videos]


def search_youtube(query: str, max_results: int = 10) -> list[str]:
    """YouTube検索で動画IDリストを取得"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'default_search': f'ytsearch{max_results}',
    }
    video_ids = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get('entries', [])
            for entry in entries:
                vid = entry.get('id')
                if vid:
                    video_ids.append(vid)
    except Exception as e:
        print(f"  ⚠ 検索エラー: {e}")
    return video_ids[:max_results]


# ─────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────

def process_video(video_id: str, include_segments: bool = True) -> dict:
    """1動画分の処理: メタデータ + トランスクリプト取得"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  📥 処理中: {url}")

    # メタデータ取得
    metadata = get_video_metadata(video_id)
    title = metadata.get('title', '(タイトル不明)')
    print(f"     タイトル: {title}")
    print(f"     再生時間: {format_duration(metadata.get('duration_seconds', 0))}")

    # トランスクリプト取得
    transcript_data = get_transcript(video_id)

    if transcript_data.get('error'):
        print(f"     ⚠ 字幕: {transcript_data['error']}")
    else:
        lang = transcript_data.get('language', '?')
        gen = '(自動生成)' if transcript_data.get('is_generated') else '(手動)'
        count = transcript_data.get('segment_count', 0)
        text_len = len(transcript_data.get('full_text', ''))
        print(f"     ✅ 字幕取得: {lang} {gen} / {count}セグメント / {text_len}文字")

    # 出力データ構築
    result = {
        'video_id': video_id,
        'url': url,
        'crawled_at': datetime.now(timezone.utc).isoformat(),
        'metadata': metadata,
        'transcript': {
            'language': transcript_data.get('language', ''),
            'is_generated': transcript_data.get('is_generated', False),
            'segment_count': transcript_data.get('segment_count', 0),
            'full_text': transcript_data.get('full_text', ''),
            'error': transcript_data.get('error', None),
        },
    }

    if include_segments and transcript_data.get('segments'):
        result['transcript']['segments'] = transcript_data['segments']

    return result


def save_results(results: list[dict], output_path: str, pretty: bool = True):
    """結果をJSONファイルに保存"""
    output = {
        'crawl_info': {
            'tool': 'YouTube Transcript Crawler',
            'version': '1.0.0',
            'crawled_at': datetime.now(timezone.utc).isoformat(),
            'total_videos': len(results),
            'successful': sum(1 for r in results if not r['transcript'].get('error')),
            'failed': sum(1 for r in results if r['transcript'].get('error')),
        },
        'videos': results,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2 if pretty else None)

    file_size = os.path.getsize(output_path)
    print(f"\n💾 保存完了: {output_path}")
    print(f"   ファイルサイズ: {file_size:,} bytes")
    print(f"   動画数: {output['crawl_info']['total_videos']}")
    print(f"   成功: {output['crawl_info']['successful']} / 失敗: {output['crawl_info']['failed']}")


def merge_json(existing_path: str, new_results: list[dict]) -> list[dict]:
    """既存のJSONファイルに追記（重複排除）"""
    existing_results = []
    if os.path.exists(existing_path):
        with open(existing_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            existing_results = data.get('videos', [])

    existing_ids = {r['video_id'] for r in existing_results}
    added = 0
    for r in new_results:
        if r['video_id'] not in existing_ids:
            existing_results.append(r)
            existing_ids.add(r['video_id'])
            added += 1

    print(f"   📎 マージ: 既存{len(existing_results) - added}件 + 新規{added}件 = 合計{len(existing_results)}件")
    return existing_results


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='YouTube動画の字幕をテキスト化してJSONに保存するツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 単一動画
  python youtube_crawler.py --url "https://www.youtube.com/watch?v=XXXXX"

  # 複数動画
  python youtube_crawler.py --url "URL1" "URL2" "URL3"

  # プレイリスト
  python youtube_crawler.py --playlist "https://www.youtube.com/playlist?list=XXXXX"

  # チャンネルの最新動画
  python youtube_crawler.py --channel "https://www.youtube.com/@channelname" --max 20

  # キーワード検索
  python youtube_crawler.py --search "建設DX AI活用" --max 10

  # URLリストファイルから
  python youtube_crawler.py --file urls.txt

  # 追記モード（既存JSONにマージ）
  python youtube_crawler.py --url "URL" --output data.json --append
        """,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url', nargs='+', help='YouTube動画URL（複数可）')
    source.add_argument('--playlist', help='YouTubeプレイリストURL')
    source.add_argument('--channel', help='YouTubeチャンネルURL')
    source.add_argument('--search', help='YouTube検索キーワード')
    source.add_argument('--file', help='URLリストファイルパス（1行1URL）')

    parser.add_argument('--output', '-o', default='youtube_data.json', help='出力JSONファイルパス (default: youtube_data.json)')
    parser.add_argument('--max', type=int, default=20, help='最大取得動画数 (default: 20)')
    parser.add_argument('--no-segments', action='store_true', help='タイムスタンプ付きセグメント詳細を省略（full_textのみ保存）')
    parser.add_argument('--compact', action='store_true', help='JSONを圧縮出力')
    parser.add_argument('--append', action='store_true', help='既存JSONファイルに追記（重複排除）')

    args = parser.parse_args()

    print("=" * 60)
    print("🎬 YouTube Transcript Crawler v1.0.0")
    print("=" * 60)

    # 動画IDリスト構築
    video_ids = []

    if args.url:
        for u in args.url:
            vid = extract_video_id(u.strip())
            if vid:
                video_ids.append(vid)
            else:
                print(f"  ⚠ 無効なURL: {u}")

    elif args.playlist:
        print(f"📋 プレイリスト読み込み: {args.playlist}")
        video_ids = get_playlist_video_ids(args.playlist, args.max)

    elif args.channel:
        print(f"📺 チャンネル読み込み: {args.channel}")
        video_ids = get_channel_video_ids(args.channel, args.max)

    elif args.search:
        print(f"🔍 検索: '{args.search}'")
        video_ids = search_youtube(args.search, args.max)

    elif args.file:
        with open(args.file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    vid = extract_video_id(line)
                    if vid:
                        video_ids.append(vid)

    if not video_ids:
        print("❌ 処理対象の動画が見つかりませんでした")
        sys.exit(1)

    # 重複排除
    seen = set()
    unique_ids = []
    for vid in video_ids:
        if vid not in seen:
            seen.add(vid)
            unique_ids.append(vid)
    video_ids = unique_ids[:args.max]

    print(f"\n🎯 処理対象: {len(video_ids)}動画\n")

    # 各動画を処理
    results = []
    for i, vid in enumerate(video_ids, 1):
        print(f"[{i}/{len(video_ids)}]")
        result = process_video(vid, include_segments=not args.no_segments)
        results.append(result)
        print()

    # 追記モード
    if args.append:
        results = merge_json(args.output, results)

    # 保存
    save_results(results, args.output, pretty=not args.compact)

    print("\n✅ 完了!")


if __name__ == '__main__':
    main()
