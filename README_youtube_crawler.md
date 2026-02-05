# 🎬 YouTube Transcript Crawler

YouTube動画の字幕（トランスクリプト）をテキスト抽出してJSONに蓄積するツールです。

## セットアップ

```bash
pip install youtube-transcript-api yt-dlp
```

## 使い方

### 単一動画の取得

```bash
python youtube_crawler.py --url "https://www.youtube.com/watch?v=XXXXX"
```

### 複数動画の一括取得

```bash
python youtube_crawler.py --url "URL1" "URL2" "URL3"
```

### プレイリスト丸ごと取得

```bash
python youtube_crawler.py --playlist "https://www.youtube.com/playlist?list=XXXXX"
```

### チャンネルの最新動画を取得

```bash
python youtube_crawler.py --channel "https://www.youtube.com/@channelname" --max 30
```

### キーワード検索で取得

```bash
python youtube_crawler.py --search "建設DX AI活用" --max 10
```

### URLリストファイルから一括取得

```bash
# urls.txt（1行1URL、#でコメント）
python youtube_crawler.py --file urls.txt
```

### 追記モード（データ蓄積）

```bash
# 初回
python youtube_crawler.py --search "建設業 DX" --max 10 -o construction_dx.json

# 2回目以降 --append で重複排除しながら追記
python youtube_crawler.py --search "建設業 AI" --max 10 -o construction_dx.json --append
```

## オプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `--output`, `-o` | 出力JSONファイルパス | `youtube_data.json` |
| `--max` | 最大取得動画数 | 20 |
| `--no-segments` | タイムスタンプ付きセグメント省略 | OFF |
| `--compact` | JSON圧縮出力 | OFF |
| `--append` | 既存JSONに追記（重複排除） | OFF |

## 出力JSON構造

```json
{
  "crawl_info": {
    "tool": "YouTube Transcript Crawler",
    "version": "1.0.0",
    "crawled_at": "2026-02-05T12:00:00+00:00",
    "total_videos": 5,
    "successful": 4,
    "failed": 1
  },
  "videos": [
    {
      "video_id": "dQw4w9WgXcQ",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "crawled_at": "2026-02-05T12:00:00+00:00",
      "metadata": {
        "title": "動画タイトル",
        "channel": "チャンネル名",
        "channel_id": "UCxxxxxxx",
        "upload_date": "20240101",
        "duration_seconds": 600,
        "view_count": 12345,
        "like_count": 100,
        "description": "動画の説明文...",
        "tags": ["タグ1", "タグ2"],
        "categories": ["Education"],
        "thumbnail_url": "https://..."
      },
      "transcript": {
        "language": "ja",
        "is_generated": true,
        "segment_count": 150,
        "full_text": "字幕の全文テキストがここに...",
        "segments": [
          {
            "start": 0.0,
            "duration": 3.5,
            "text": "こんにちは"
          }
        ]
      }
    }
  ]
}
```

## 字幕取得の優先順位

1. 日本語の手動字幕
2. 日本語の自動生成字幕
3. 英語の手動字幕
4. 英語の自動生成字幕
5. その他見つかった字幕

## 活用例

取得したJSONは以下のような用途に使えます:

- **AIによる要約・分析**: full_textをLLMに渡して要約や分析
- **検索インデックス構築**: 動画内容のテキスト検索
- **ナレッジベース構築**: 業界動画の知識データベース化
- **セグメント活用**: タイムスタンプ付きで特定箇所を参照
- **チャンネル分析**: メタデータから再生数・トレンド分析
