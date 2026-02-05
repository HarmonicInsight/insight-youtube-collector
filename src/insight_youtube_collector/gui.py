"""
Streamlit GUI for Insight YouTube Collector.

Run with:
    streamlit run src/insight_youtube_collector/gui.py
    # or
    iyc-gui
"""

import streamlit as st
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path for development
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from insight_youtube_collector import __version__
from insight_youtube_collector.collector import YouTubeCollector
from insight_youtube_collector.batch import BatchConfig, BatchCollector
from insight_youtube_collector.storage import WarehouseStorage
from insight_youtube_collector.config import Settings


def init_session_state():
    """Initialize session state variables."""
    if 'collection_results' not in st.session_state:
        st.session_state.collection_results = []
    if 'collection_log' not in st.session_state:
        st.session_state.collection_log = []
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    if 'selected_videos' not in st.session_state:
        st.session_state.selected_videos = set()


def log_message(message: str):
    """Add message to collection log."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.collection_log.append(f"[{timestamp}] {message}")


def clear_log():
    """Clear collection log."""
    st.session_state.collection_log = []


def format_duration(seconds: int) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    if not seconds:
        return "0:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def search_videos(query: str, max_results: int):
    """Search for videos and store results in session state."""
    import time
    import io
    import contextlib
    log_message(f"検索中: {query}")

    from insight_youtube_collector.extractor import VideoSourceExtractor
    import yt_dlp

    def fetch_video_info(vid: str, retry_count: int = 0) -> dict | None:
        """Fetch video info with retry on rate limit."""
        max_retries = 3
        url = f"https://www.youtube.com/watch?v={vid}"

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
            'no_color': True,
        }

        # Try with cookies first (only on first attempt)
        if retry_count == 0:
            ydl_opts['cookiesfrombrowser'] = ('chrome',)

        # Suppress stderr output from yt-dlp
        stderr_capture = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr_capture):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        return info
        except Exception as e:
            error_msg = str(e).lower()
            # If cookie error, retry without cookies
            if 'cookie' in error_msg and 'cookiesfrombrowser' in ydl_opts:
                del ydl_opts['cookiesfrombrowser']
                try:
                    with contextlib.redirect_stderr(stderr_capture):
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            if info:
                                return info
                except Exception:
                    pass
            # If rate limited, retry with backoff
            if '429' in str(e) and retry_count < max_retries:
                wait_time = (retry_count + 1) * 10  # 10, 20, 30 seconds
                log_message(f"  Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                return fetch_video_info(vid, retry_count + 1)

        return None

    try:
        with st.spinner("🔍 検索中..."):
            source_extractor = VideoSourceExtractor(quiet=True)

            # Get video IDs from search
            video_ids = source_extractor.extract_from_search(query, max_results)

            if not video_ids:
                st.warning("検索結果が見つかりませんでした")
                log_message("検索結果なし")
                return

            # Get metadata and subtitle info for each video
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, vid in enumerate(video_ids):
                status_text.text(f"字幕情報を確認中... {i+1}/{len(video_ids)}")
                progress_bar.progress((i + 1) / len(video_ids))

                try:
                    info = fetch_video_info(vid)
                    if not info:
                        log_message(f"  スキップ: {vid} - 情報取得失敗")
                        continue

                    # Check if subtitles are available
                    subtitles = info.get('subtitles', {})
                    auto_captions = info.get('automatic_captions', {})
                    has_ja = 'ja' in subtitles or 'ja' in auto_captions
                    has_en = 'en' in subtitles or 'en' in auto_captions
                    has_any = bool(subtitles) or bool(auto_captions)

                    results.append({
                        'video_id': vid,
                        'title': info.get('title', '(タイトル不明)'),
                        'channel': info.get('channel', info.get('uploader', '')),
                        'duration': info.get('duration', 0),
                        'url': f"https://www.youtube.com/watch?v={vid}",
                        'has_subtitles': has_any,
                        'has_ja': has_ja,
                        'has_en': has_en,
                        'subtitle_langs': list(subtitles.keys()) + list(auto_captions.keys()),
                    })

                    # Add small delay between requests to avoid rate limiting
                    if i < len(video_ids) - 1:
                        time.sleep(1.5)

                except Exception as e:
                    log_message(f"  スキップ: {vid} - {e}")
                    continue

            progress_bar.empty()
            status_text.empty()

            # Filter to only videos with subtitles
            videos_with_subs = [r for r in results if r['has_subtitles']]

            st.session_state.search_results = videos_with_subs
            st.session_state.selected_videos = set()  # Clear previous selections

            total_found = len(results)
            with_subs = len(videos_with_subs)
            log_message(f"検索完了: {total_found} 件中 {with_subs} 件が字幕あり")

            if videos_with_subs:
                st.success(f"✅ {with_subs} 件の動画が見つかりました（字幕あり）")
                if total_found > with_subs:
                    st.info(f"ℹ️ 字幕なしの {total_found - with_subs} 件は除外されました")
            else:
                st.warning("字幕のある動画が見つかりませんでした")

            st.rerun()

    except Exception as e:
        st.error(f"検索エラー: {e}")
        log_message(f"検索エラー: {e}")


def collect_selected_videos(video_ids: list, warehouse_dir: str, json_path: str):
    """Collect transcripts for selected videos."""
    clear_log()
    log_message(f"選択した {len(video_ids)} 件の収集開始")

    settings = Settings(quiet_mode=True)
    collector = YouTubeCollector(settings)

    progress = st.progress(0)
    status = st.empty()

    try:
        videos = []
        total = len(video_ids)

        for i, vid in enumerate(video_ids):
            status.info(f"🔄 [{i+1}/{total}] トランスクリプト取得中...")
            log_message(f"取得中: {vid}")
            progress.progress((i + 1) / (total + 1))

            video_data = collector.collect_video(vid, verbose=False)
            if video_data:
                videos.append(video_data)
                if video_data.transcript and not video_data.transcript.error:
                    text_len = len(video_data.transcript.full_text)
                    seg_count = video_data.transcript.segment_count
                    log_message(f"  ✓ {video_data.metadata.title} ({text_len}文字, {seg_count}セグメント)")
                else:
                    error_msg = video_data.transcript.error if video_data.transcript else "不明"
                    log_message(f"  ✗ {video_data.metadata.title} - {error_msg}")

        log_message(f"取得完了: {len(videos)} 動画")

        if videos:
            # Save to warehouse
            if warehouse_dir:
                status.info("💾 Warehouseに保存中...")
                log_message("Warehouseに保存中...")
                result = collector.save_warehouse(videos, warehouse_dir=warehouse_dir)
                log_message(f"Warehouse保存: {result['saved']} ファイル")

            # Save to JSON
            if json_path:
                log_message("JSONに保存中...")
                collector.save_json(videos, output_path=json_path)
                log_message(f"JSON保存: {json_path}")

            progress.progress(100)
            status.success(f"✅ 完了: {len(videos)} 動画を収集しました")
            log_message("収集完了!")

            # Clear search results
            st.session_state.search_results = []
            st.session_state.selected_videos = set()

            # Show results
            st.subheader("収集結果")
            success_count = sum(1 for v in videos if v.transcript and not v.transcript.error)
            st.metric("トランスクリプト取得成功", f"{success_count} / {len(videos)}")

            for v in videos[:10]:
                has_transcript = v.transcript and not v.transcript.error
                icon = "✓" if has_transcript else "✗"
                st.write(f"{icon} **{v.metadata.title}**")
            if len(videos) > 10:
                st.write(f"... 他 {len(videos) - 10} 件")
        else:
            status.warning("動画が見つかりませんでした")
            log_message("動画が見つかりませんでした")

    except Exception as e:
        status.error(f"エラー: {e}")
        log_message(f"エラー: {e}")


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Insight YouTube Collector",
        page_icon="🎬",
        layout="wide",
    )

    init_session_state()

    # Header
    st.title("🎬 Insight YouTube Collector")
    st.caption(f"v{__version__} - Harmonic Insight Text Data Warehouse Tool")

    # Sidebar - Settings
    with st.sidebar:
        st.header("⚙️ 設定")

        warehouse_dir = st.text_input(
            "Warehouse ディレクトリ",
            value="data/warehouse/lectures",
            help="収集したテキストを保存するディレクトリ"
        )

        max_videos = st.slider(
            "最大動画数（ソースごと）",
            min_value=1,
            max_value=100,
            value=10,
            help="各ソースから取得する最大動画数"
        )

        st.divider()

        # Output format
        st.subheader("出力形式")
        save_warehouse = st.checkbox("Warehouse形式（HMG用）", value=True)
        save_json = st.checkbox("JSON形式", value=False)

        if save_json:
            json_path = st.text_input("JSON出力パス", value="data/output/result.json")

        st.divider()

        # Warehouse status
        st.subheader("📁 Warehouse 状態")
        try:
            storage = WarehouseStorage(warehouse_dir=warehouse_dir)
            files = storage.list_files()
            st.metric("保存済みファイル数", len(files))
        except Exception:
            st.info("Warehouseが存在しません")

    # Main content - Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 検索＆選択",
        "🔗 単一収集",
        "📋 バッチ収集",
        "📁 Warehouse",
        "📜 ログ"
    ])

    # Tab 1: Search & Select
    with tab1:
        st.header("🔍 検索して選択")
        st.caption("検索結果から動画を選んでトランスクリプトを取得します")

        # Search section
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input(
                "検索キーワード",
                placeholder="建設DX AI活用 など",
                key="search_query"
            )
        with col2:
            search_max = st.number_input("検索件数", min_value=5, max_value=50, value=20, key="search_max")

        if st.button("🔍 検索", key="search_btn", type="primary"):
            if search_query:
                search_videos(search_query, search_max)
            else:
                st.warning("検索キーワードを入力してください")

        # Display search results
        if st.session_state.search_results:
            st.divider()
            st.subheader(f"検索結果: {len(st.session_state.search_results)} 件")

            # Select all / Deselect all buttons
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("✅ すべて選択"):
                    st.session_state.selected_videos = set(
                        v['video_id'] for v in st.session_state.search_results
                    )
                    st.rerun()
            with col2:
                if st.button("❌ すべて解除"):
                    st.session_state.selected_videos = set()
                    st.rerun()
            with col3:
                selected_count = len(st.session_state.selected_videos)
                st.write(f"選択中: **{selected_count}** 件")

            # Video list with checkboxes
            for v in st.session_state.search_results:
                vid = v['video_id']
                is_selected = vid in st.session_state.selected_videos

                col1, col2 = st.columns([0.05, 0.95])
                with col1:
                    if st.checkbox("選択", value=is_selected, key=f"chk_{vid}", label_visibility="collapsed"):
                        st.session_state.selected_videos.add(vid)
                    else:
                        st.session_state.selected_videos.discard(vid)
                with col2:
                    duration = format_duration(v.get('duration', 0))
                    # Show subtitle language badges
                    lang_badges = []
                    if v.get('has_ja'):
                        lang_badges.append("🇯🇵")
                    if v.get('has_en'):
                        lang_badges.append("🇺🇸")
                    lang_str = " ".join(lang_badges) if lang_badges else "📝"
                    st.markdown(f"**{v['title']}** {lang_str}  \n{v['channel']} • {duration}")

            st.divider()

            # Collect selected videos
            selected_count = len(st.session_state.selected_videos)
            if selected_count > 0:
                if st.button(f"🚀 選択した {selected_count} 件を収集", type="primary", use_container_width=True):
                    collect_selected_videos(
                        list(st.session_state.selected_videos),
                        warehouse_dir if save_warehouse else None,
                        json_path if save_json else None,
                    )
            else:
                st.info("収集する動画を選択してください")

    # Tab 2: Single Collection
    with tab2:
        st.header("単一ソースからの収集")

        col1, col2 = st.columns([2, 1])

        with col1:
            source_type = st.selectbox(
                "ソースタイプ",
                ["動画URL", "プレイリスト", "チャンネル", "検索キーワード"],
                key="single_source_type"
            )

            if source_type == "動画URL":
                source_value = st.text_area(
                    "YouTube URL（複数の場合は1行1URL）",
                    height=100,
                    placeholder="https://www.youtube.com/watch?v=...",
                    key="single_urls"
                )
            elif source_type == "プレイリスト":
                source_value = st.text_input(
                    "プレイリスト URL",
                    placeholder="https://www.youtube.com/playlist?list=...",
                    key="single_playlist"
                )
            elif source_type == "チャンネル":
                source_value = st.text_input(
                    "チャンネル URL",
                    placeholder="https://www.youtube.com/@channelname",
                    key="single_channel"
                )
            else:
                source_value = st.text_input(
                    "検索キーワード",
                    placeholder="建設DX AI活用",
                    key="single_search"
                )

        with col2:
            st.write("")  # Spacer
            st.write("")
            if st.button("🚀 収集開始", key="single_collect", type="primary", use_container_width=True):
                if source_value:
                    collect_single(
                        source_type,
                        source_value,
                        max_videos,
                        warehouse_dir if save_warehouse else None,
                        json_path if save_json else None,
                    )
                else:
                    st.warning("ソースを入力してください")

    # Tab 3: Batch Collection
    with tab3:
        st.header("バッチ収集")

        batch_mode = st.radio(
            "入力モード",
            ["キーワードリスト", "URLリスト", "設定ファイル"],
            horizontal=True
        )

        if batch_mode == "キーワードリスト":
            keywords_text = st.text_area(
                "検索キーワード（1行1キーワード）",
                height=200,
                placeholder="建設DX AI活用\n施工管理 デジタル化\nBIM 活用事例",
                key="batch_keywords"
            )

            if st.button("🚀 バッチ収集開始", key="batch_keywords_btn", type="primary"):
                if keywords_text.strip():
                    keywords = [k.strip() for k in keywords_text.strip().split('\n') if k.strip()]
                    collect_batch_keywords(
                        keywords,
                        max_videos,
                        warehouse_dir if save_warehouse else None,
                    )
                else:
                    st.warning("キーワードを入力してください")

        elif batch_mode == "URLリスト":
            urls_text = st.text_area(
                "URL（1行1URL、プレイリスト/チャンネル/動画を混在可）",
                height=200,
                placeholder="https://www.youtube.com/playlist?list=...\nhttps://www.youtube.com/@channelname\nhttps://www.youtube.com/watch?v=...",
                key="batch_urls"
            )

            if st.button("🚀 バッチ収集開始", key="batch_urls_btn", type="primary"):
                if urls_text.strip():
                    urls = [u.strip() for u in urls_text.strip().split('\n') if u.strip()]
                    collect_batch_urls(
                        urls,
                        max_videos,
                        warehouse_dir if save_warehouse else None,
                    )
                else:
                    st.warning("URLを入力してください")

        else:  # 設定ファイル
            config_file = st.file_uploader(
                "YAML/JSON 設定ファイル",
                type=['yaml', 'yml', 'json'],
                key="batch_config_file"
            )

            if config_file and st.button("🚀 バッチ収集開始", key="batch_config_btn", type="primary"):
                collect_batch_config(config_file, warehouse_dir)

    # Tab 4: Warehouse Browser
    with tab4:
        st.header("Warehouse ブラウザ")

        try:
            storage = WarehouseStorage(warehouse_dir=warehouse_dir)
            files = storage.list_files()
            manifest = storage.get_manifest()

            if files:
                st.success(f"📁 {len(files)} ファイルが保存されています")

                # File list with search
                search = st.text_input("🔍 ファイル名で検索", key="warehouse_search")

                filtered_files = files
                if search:
                    filtered_files = [f for f in files if search.lower() in f.lower()]

                for f in filtered_files[:50]:  # Limit display
                    meta = manifest.get("files", {}).get(f, {})
                    title = meta.get("source_title", "")
                    channel = meta.get("channel", "")

                    with st.expander(f"📄 {f[:60]}..."):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**タイトル:** {title}")
                            st.write(f"**チャンネル:** {channel}")
                        with col2:
                            st.write(f"**収集日:** {meta.get('observed_at', 'N/A')}")
                            st.write(f"**公開日:** {meta.get('upload_date', 'N/A')}")

                        # Read and display file content preview
                        file_path = Path(warehouse_dir) / f
                        if file_path.exists():
                            content = file_path.read_text(encoding='utf-8')
                            file_size = file_path.stat().st_size
                            st.caption(f"📊 ファイルサイズ: {file_size:,} bytes / {len(content):,} 文字")
                            if len(content) > 2000:
                                st.text_area("内容プレビュー (最初の2000文字)", content[:2000] + "\n\n... (以下省略)", height=200, disabled=True)
                            else:
                                st.text_area("内容プレビュー", content, height=200, disabled=True)

                if len(filtered_files) > 50:
                    st.info(f"... 他 {len(filtered_files) - 50} ファイル")

            else:
                st.info("Warehouseは空です。収集を開始してください。")

        except Exception as e:
            st.error(f"Warehouse読み込みエラー: {e}")

    # Tab 5: Log
    with tab5:
        st.header("収集ログ")

        col1, col2 = st.columns([4, 1])
        with col2:
            if st.button("🗑️ ログクリア"):
                clear_log()
                st.rerun()

        if st.session_state.collection_log:
            log_text = "\n".join(st.session_state.collection_log)
            st.code(log_text, language=None)
        else:
            st.info("ログはまだありません")


def collect_single(source_type, source_value, max_videos, warehouse_dir, json_path):
    """Collect from a single source."""
    clear_log()
    log_message(f"収集開始: {source_type}")

    settings = Settings(quiet_mode=True)
    collector = YouTubeCollector(settings)

    progress = st.progress(0)
    status = st.empty()

    try:
        status.info("🔄 動画情報を取得中...")
        log_message("動画情報を取得中...")

        videos = []
        if source_type == "動画URL":
            urls = [u.strip() for u in source_value.strip().split('\n') if u.strip()]
            videos = collector.collect_from_urls(urls, max_videos=max_videos, verbose=False)
        elif source_type == "プレイリスト":
            videos = collector.collect_from_playlist(source_value, max_videos=max_videos, verbose=False)
        elif source_type == "チャンネル":
            videos = collector.collect_from_channel(source_value, max_videos=max_videos, verbose=False)
        else:
            videos = collector.collect_from_search(source_value, max_videos=max_videos, verbose=False)

        progress.progress(50)
        log_message(f"取得完了: {len(videos)} 動画")

        if videos:
            # Save to warehouse
            if warehouse_dir:
                status.info("💾 Warehouseに保存中...")
                log_message("Warehouseに保存中...")
                result = collector.save_warehouse(videos, warehouse_dir=warehouse_dir)
                log_message(f"Warehouse保存: {result['saved']} ファイル")

            # Save to JSON
            if json_path:
                log_message("JSONに保存中...")
                collector.save_json(videos, output_path=json_path)
                log_message(f"JSON保存: {json_path}")

            progress.progress(100)
            status.success(f"✅ 完了: {len(videos)} 動画を収集しました")
            log_message("収集完了!")

            # Show results
            st.subheader("収集結果")
            for v in videos[:10]:
                st.write(f"- **{v.metadata.title}** ({v.metadata.channel})")
            if len(videos) > 10:
                st.write(f"... 他 {len(videos) - 10} 件")

        else:
            status.warning("動画が見つかりませんでした")
            log_message("動画が見つかりませんでした")

    except Exception as e:
        status.error(f"エラー: {e}")
        log_message(f"エラー: {e}")


def collect_batch_keywords(keywords, max_videos, warehouse_dir):
    """Batch collect from keywords."""
    clear_log()
    log_message(f"バッチ収集開始: {len(keywords)} キーワード")

    from insight_youtube_collector.batch import BatchConfig, SourceConfig, BatchCollector

    # Build config
    sources = [SourceConfig("keyword", kw, max_videos) for kw in keywords]
    config = BatchConfig(
        sources=sources,
        save_warehouse=bool(warehouse_dir),
        warehouse_dir=warehouse_dir or "data/warehouse/lectures",
        save_json=False,
    )

    progress = st.progress(0)
    status = st.empty()

    try:
        total = len(keywords)
        for i, kw in enumerate(keywords):
            status.info(f"🔄 [{i+1}/{total}] 検索中: {kw}")
            log_message(f"検索中: {kw}")
            progress.progress((i + 1) / (total + 1))

        status.info("🔄 収集実行中...")
        collector = BatchCollector(config, verbose=False)
        result = collector.collect_all()

        progress.progress(100)
        log_message(f"収集完了: {result['unique_videos']} 動画")

        status.success(f"✅ 完了: {result['unique_videos']} 動画を収集")

        # Show summary
        st.metric("収集動画数", result['unique_videos'])
        if result.get('save_results', {}).get('warehouse'):
            wh = result['save_results']['warehouse']
            st.metric("保存ファイル数", wh['saved'])

    except Exception as e:
        status.error(f"エラー: {e}")
        log_message(f"エラー: {e}")


def collect_batch_urls(urls, max_videos, warehouse_dir):
    """Batch collect from URLs."""
    clear_log()
    log_message(f"バッチ収集開始: {len(urls)} URL")

    from insight_youtube_collector.batch import BatchConfig, SourceConfig, BatchCollector

    # Auto-detect source types
    sources = []
    for url in urls:
        if 'playlist?list=' in url:
            sources.append(SourceConfig("playlist", url, max_videos))
        elif '/@' in url or '/channel/' in url or '/c/' in url:
            sources.append(SourceConfig("channel", url, max_videos))
        else:
            sources.append(SourceConfig("url", url, 1))

    config = BatchConfig(
        sources=sources,
        save_warehouse=bool(warehouse_dir),
        warehouse_dir=warehouse_dir or "data/warehouse/lectures",
        save_json=False,
    )

    progress = st.progress(0)
    status = st.empty()

    try:
        status.info("🔄 収集実行中...")
        collector = BatchCollector(config, verbose=False)
        result = collector.collect_all()

        progress.progress(100)
        log_message(f"収集完了: {result['unique_videos']} 動画")

        status.success(f"✅ 完了: {result['unique_videos']} 動画を収集")

        st.metric("収集動画数", result['unique_videos'])

    except Exception as e:
        status.error(f"エラー: {e}")
        log_message(f"エラー: {e}")


def collect_batch_config(config_file, warehouse_dir):
    """Batch collect from config file."""
    import tempfile
    import yaml
    import json

    clear_log()
    log_message("設定ファイルからバッチ収集開始")

    progress = st.progress(0)
    status = st.empty()

    try:
        # Save uploaded file temporarily
        content = config_file.read().decode('utf-8')

        if config_file.name.endswith('.json'):
            data = json.loads(content)
        else:
            import yaml
            data = yaml.safe_load(content)

        config = BatchConfig.from_dict(data)
        log_message(f"設定読み込み: {len(config.sources)} ソース")

        status.info("🔄 収集実行中...")
        collector = BatchCollector(config, verbose=False)
        result = collector.collect_all()

        progress.progress(100)
        log_message(f"収集完了: {result['unique_videos']} 動画")

        status.success(f"✅ 完了: {result['unique_videos']} 動画を収集")

        st.metric("収集動画数", result['unique_videos'])

    except Exception as e:
        status.error(f"エラー: {e}")
        log_message(f"エラー: {e}")


if __name__ == "__main__":
    main()
