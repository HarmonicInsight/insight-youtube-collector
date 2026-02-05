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


def log_message(message: str):
    """Add message to collection log."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.collection_log.append(f"[{timestamp}] {message}")


def clear_log():
    """Clear collection log."""
    st.session_state.collection_log = []


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
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔗 単一収集",
        "📋 バッチ収集",
        "📁 Warehouse",
        "📜 ログ"
    ])

    # Tab 1: Single Collection
    with tab1:
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

    # Tab 2: Batch Collection
    with tab2:
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

    # Tab 3: Warehouse Browser
    with tab3:
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
                            st.text_area("内容プレビュー", content[:2000], height=200, disabled=True)

                if len(filtered_files) > 50:
                    st.info(f"... 他 {len(filtered_files) - 50} ファイル")

            else:
                st.info("Warehouseは空です。収集を開始してください。")

        except Exception as e:
            st.error(f"Warehouse読み込みエラー: {e}")

    # Tab 4: Log
    with tab4:
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
