"""
PIVOT Analyzer - PIVOTフレームワークによるYouTube文字起こし分析

PIVOTフレームワーク:
- 対象軸（What）: Process / Tool / People の3層モデル
- 声の分類（Voice）: P(Pain) / I(Insecurity) / V(Vision) / O(Objection) / T(Traction)

使用例:
    from insight_youtube_collector.analyzer import PIVOTAnalyzer, analyze_videos

    analyzer = PIVOTAnalyzer(domain="biz_analysis")
    results = analyzer.analyze_videos(collected_videos)

    for result in results:
        print(f"{result.video_id}: {result.total_score} (P:{result.pain_count}, V:{result.vision_count})")
"""

import re
import uuid
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Import VideoData model
from ..models.video import VideoData


# ========================================
# PIVOT定義
# ========================================

class PIVOT:
    """PIVOT Voice定義"""
    PAIN = "P"
    INSECURITY = "I"
    VISION = "V"
    OBJECTION = "O"
    TRACTION = "T"

    ALL = [PAIN, INSECURITY, VISION, OBJECTION, TRACTION]

    LABELS = {
        "P": "Pain",
        "I": "Insecurity",
        "V": "Vision",
        "O": "Objection",
        "T": "Traction",
    }

    SCORES = {
        "P": -2,  # 現在の負のインパクト
        "I": -1,  # 将来の潜在リスク
        "V": 1,   # 改善へのモチベーション
        "O": -1,  # 実行障壁
        "T": 2,   # 成功の土台
    }

    DESCRIPTIONS = {
        "P": "課題・困りごと",
        "I": "不安・心配",
        "V": "要望・理想像",
        "O": "摩擦・抵抗",
        "T": "成功・強み",
    }


# ========================================
# キーワード・パターン辞書
# ========================================

PIVOT_KEYWORDS = {
    "P": {  # Pain
        "keywords": [
            "困っている", "問題", "課題", "うまくいかない", "できない",
            "難しい", "障害", "ボトルネック", "トラブル", "エラー",
            "遅れ", "遅延", "不足", "ミス", "失敗", "止まる",
            "時間がかかる", "手間", "非効率", "無駄", "面倒",
            "バグ", "不具合", "故障", "落ちる", "動かない",
        ],
        "patterns": [
            r"(.+?)(?:で|に)困っている",
            r"(.+?)(?:が|は)(?:問題|課題)(?:だ|です|になっている)",
            r"(.+?)(?:が|は)(?:うまくいかない|難しい|厳しい)",
            r"(.+?)(?:が|に)時間がかかる",
        ],
    },
    "I": {  # Insecurity
        "keywords": [
            "心配", "不安", "懸念", "気になる", "気がかり",
            "大丈夫か", "リスク", "危ない", "もしかしたら",
            "かもしれない", "恐れ", "属人化", "引継ぎ",
            "辞めたら", "いなくなったら", "将来", "今後",
        ],
        "patterns": [
            r"(.+?)(?:が|を)(?:心配|不安|懸念)",
            r"(.+?)(?:かもしれない|恐れがある)",
            r"(?:辞め|いなくなっ)たら(.+?)(?:が|は|も)(?:困る|終わる|できない)",
        ],
    },
    "V": {  # Vision
        "keywords": [
            "してほしい", "欲しい", "ほしい", "があれば", "できたら",
            "期待", "要望", "希望", "理想", "改善したい",
            "効率化", "自動化", "システム化", "デジタル化",
            "したい", "できるように", "なればいい", "なるといい",
            "導入したい", "使いたい", "実現したい",
        ],
        "patterns": [
            r"(.+?)(?:して|が)(?:ほしい|欲しい|ホシイ)",
            r"(.+?)(?:があれば|できれば)(?:いい|良い|嬉しい|助かる)",
            r"(.+?)(?:を|が)(?:効率化|自動化|改善)(?:したい|してほしい)",
        ],
    },
    "O": {  # Objection
        "keywords": [
            "反対", "抵抗", "無理", "やりたくない",
            "前もダメだった", "失敗した", "うまくいかなかった",
            "嫌", "面倒", "ストレス", "対立", "衝突",
            "やらされ", "強制", "納得できない",
        ],
        "patterns": [
            r"(?:前|以前|過去)(?:に|も)(.+?)(?:が|で)(?:失敗|ダメ|うまくいかなかった)",
            r"(.+?)(?:に|は)(?:反対|抵抗)(?:がある|している)",
            r"(.+?)(?:を|は)(?:やりたくない|したくない)",
        ],
    },
    "T": {  # Traction
        "keywords": [
            "うまくいっている", "成功", "順調", "問題ない",
            "満足", "良い", "便利", "助かっている", "効率的",
            "強み", "得意", "定着", "回っている", "機能している",
            "気に入っている", "使いやすい", "スムーズ",
            "うまく", "ちゃんと", "しっかり", "快適",
        ],
        "patterns": [
            r"(.+?)(?:は|が)(?:うまくいっている|順調|成功)",
            r"(.+?)(?:に|は)(?:満足|問題ない)",
            r"(.+?)(?:は|が)(?:便利|助かっている|効率的)",
        ],
    },
}

# 温度感インジケータ
TEMPERATURE_INDICATORS = {
    "high": ["絶対", "本当に", "非常に", "とても", "すごく", "めちゃくちゃ", "いつも", "毎回", "必ず"],
    "medium": ["かなり", "結構", "わりと", "時々", "たまに", "よく"],
    "low": ["少し", "ちょっと", "多少", "若干", "たぶん", "おそらく"],
}


# ========================================
# 型定義
# ========================================

@dataclass
class PIVOTInsight:
    """PIVOT分類されたインサイト"""
    id: str
    pivot_voice: str  # P, I, V, O, T
    pivot_label: str
    pivot_score: int
    title: str
    body: str
    confidence: float
    temperature: str
    matched_keywords: List[str] = field(default_factory=list)
    video_id: Optional[str] = None
    timestamp: Optional[float] = None  # 動画内の時間（秒）


@dataclass
class PIVOTAnalysisResult:
    """PIVOT分析結果"""
    items: List[PIVOTInsight]
    by_pivot: Dict[str, List[PIVOTInsight]]
    total_score: int
    sentiment_index: float
    stats: Dict


@dataclass
class VideoAnalysisResult:
    """動画単位の分析結果"""
    video_id: str
    video_title: str
    channel: str
    analyzed_at: str
    pivot_result: PIVOTAnalysisResult

    @property
    def total_score(self) -> int:
        return self.pivot_result.total_score

    @property
    def sentiment_index(self) -> float:
        return self.pivot_result.sentiment_index

    @property
    def pain_count(self) -> int:
        return len(self.pivot_result.by_pivot.get("P", []))

    @property
    def insecurity_count(self) -> int:
        return len(self.pivot_result.by_pivot.get("I", []))

    @property
    def vision_count(self) -> int:
        return len(self.pivot_result.by_pivot.get("V", []))

    @property
    def objection_count(self) -> int:
        return len(self.pivot_result.by_pivot.get("O", []))

    @property
    def traction_count(self) -> int:
        return len(self.pivot_result.by_pivot.get("T", []))

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "video_title": self.video_title,
            "channel": self.channel,
            "analyzed_at": self.analyzed_at,
            "stats": {
                "total_insights": len(self.pivot_result.items),
                "total_score": self.total_score,
                "sentiment_index": round(self.sentiment_index, 2),
                "by_pivot": {
                    "P": self.pain_count,
                    "I": self.insecurity_count,
                    "V": self.vision_count,
                    "O": self.objection_count,
                    "T": self.traction_count,
                },
            },
            "items": [
                {
                    "id": item.id,
                    "pivot": item.pivot_voice,
                    "title": item.title,
                    "body": item.body,
                    "confidence": round(item.confidence, 2),
                    "temperature": item.temperature,
                    "keywords": item.matched_keywords,
                    "timestamp": item.timestamp,
                }
                for item in self.pivot_result.items
            ],
        }

    def to_mart_items(self, observed_at: Optional[str] = None) -> List[dict]:
        """PIVOT Martアイテムとして出力"""
        observed_at = observed_at or datetime.now().strftime("%Y-%m-%d")
        marts = []

        for item in self.pivot_result.items:
            marts.append({
                "id": f"pivot_{item.id}",
                "mart_type": "pivot_insight",
                "pivot_voice": item.pivot_voice,
                "pivot_label": item.pivot_label,
                "pivot_score": item.pivot_score,
                "title": item.title,
                "body": item.body,
                "confidence": item.confidence,
                "temperature": item.temperature,
                "keywords": {"surface": item.matched_keywords},
                "source_ref": {
                    "doc_id": self.video_id,
                    "doc_type": "youtube_transcript",
                    "channel": self.channel,
                    "title": self.video_title,
                    "timestamp": item.timestamp,
                },
                "source_time": {"observed_at": observed_at},
            })

        return marts


# ========================================
# PIVOT Analyzer
# ========================================

class PIVOTAnalyzer:
    """YouTube文字起こしのPIVOT分析エンジン"""

    def __init__(
        self,
        domain: Optional[str] = None,
        min_confidence: float = 0.3,
        split_by_sentence: bool = True,
    ):
        """
        Args:
            domain: 業務ドメイン（将来の重み付け用）
            min_confidence: 最小信頼度閾値
            split_by_sentence: 句点で文を分割するか
        """
        self.domain = domain
        self.min_confidence = min_confidence
        self.split_by_sentence = split_by_sentence

        # パターンをコンパイル
        self.pivot_patterns = {}
        for pivot, config in PIVOT_KEYWORDS.items():
            self.pivot_patterns[pivot] = [
                re.compile(p) for p in config.get("patterns", [])
            ]

    def analyze_video(self, video: VideoData) -> VideoAnalysisResult:
        """
        単一動画を分析

        Args:
            video: VideoDataオブジェクト

        Returns:
            VideoAnalysisResult: 分析結果
        """
        # 文字起こしテキストを取得
        transcript_text = video.transcript.full_text if video.transcript else ""

        if not transcript_text:
            # 文字起こしがない場合は空の結果を返す
            return VideoAnalysisResult(
                video_id=video.video_id,
                video_title=video.metadata.title,
                channel=video.metadata.channel,
                analyzed_at=datetime.now().isoformat(),
                pivot_result=PIVOTAnalysisResult(
                    items=[],
                    by_pivot={p: [] for p in PIVOT.ALL},
                    total_score=0,
                    sentiment_index=0.0,
                    stats={"total": 0, "by_pivot": {p: 0 for p in PIVOT.ALL}},
                ),
            )

        # 文を分割
        sentences = self._split_sentences(transcript_text)

        # セグメントからタイムスタンプを取得するマッピング
        timestamp_map = self._build_timestamp_map(video)

        # 各文をPIVOT分類
        items: List[PIVOTInsight] = []
        by_pivot: Dict[str, List[PIVOTInsight]] = {p: [] for p in PIVOT.ALL}

        for sentence in sentences:
            insight = self._classify_sentence(sentence, video.video_id, timestamp_map)
            if insight and insight.confidence >= self.min_confidence:
                items.append(insight)
                by_pivot[insight.pivot_voice].append(insight)

        # スコア算出
        total_score = sum(item.pivot_score for item in items)
        sentiment_index = total_score / len(items) if items else 0.0

        stats = {
            "total": len(items),
            "by_pivot": {p: len(lst) for p, lst in by_pivot.items()},
            "domain": self.domain,
        }

        return VideoAnalysisResult(
            video_id=video.video_id,
            video_title=video.metadata.title,
            channel=video.metadata.channel,
            analyzed_at=datetime.now().isoformat(),
            pivot_result=PIVOTAnalysisResult(
                items=items,
                by_pivot=by_pivot,
                total_score=total_score,
                sentiment_index=sentiment_index,
                stats=stats,
            ),
        )

    def analyze_videos(self, videos: List[VideoData]) -> List[VideoAnalysisResult]:
        """
        複数動画を分析

        Args:
            videos: VideoDataのリスト

        Returns:
            List[VideoAnalysisResult]: 分析結果リスト
        """
        return [self.analyze_video(video) for video in videos]

    def _split_sentences(self, text: str) -> List[str]:
        """文を分割"""
        if not self.split_by_sentence:
            return [text]

        # 句点、感嘆符、疑問符、改行で分割
        sentences = re.split(r'[。．！？\n]+', text)
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 10]

    def _build_timestamp_map(self, video: VideoData) -> Dict[str, float]:
        """テキストからタイムスタンプへのマッピングを構築"""
        timestamp_map = {}
        if video.transcript and video.transcript.segments:
            for seg in video.transcript.segments:
                # セグメントテキストの先頭部分をキーにする
                key = seg.text[:30] if len(seg.text) > 30 else seg.text
                timestamp_map[key] = seg.start
        return timestamp_map

    def _find_timestamp(self, text: str, timestamp_map: Dict[str, float]) -> Optional[float]:
        """テキストに対応するタイムスタンプを探す"""
        for key, timestamp in timestamp_map.items():
            if key in text or text[:30] in key:
                return timestamp
        return None

    def _classify_sentence(
        self,
        text: str,
        video_id: str,
        timestamp_map: Dict[str, float],
    ) -> Optional[PIVOTInsight]:
        """単一の文をPIVOT分類"""
        if not text.strip():
            return None

        # 各PIVOTカテゴリに対してスコアリング
        scores: Dict[str, Tuple[float, List[str]]] = {}

        for pivot in PIVOT.ALL:
            config = PIVOT_KEYWORDS[pivot]
            keywords = config["keywords"]
            patterns = self.pivot_patterns[pivot]

            # キーワードマッチング
            matched_kw = [kw for kw in keywords if kw in text]
            kw_score = min(len(matched_kw) * 0.25, 0.6)

            # パターンマッチング
            pat_score = 0.0
            for pattern in patterns:
                if pattern.search(text):
                    pat_score = 0.4
                    break

            # 合計スコア
            total_score = min(kw_score + pat_score, 0.95)

            if total_score > 0:
                scores[pivot] = (total_score, matched_kw)

        if not scores:
            return None

        # 最高スコアのPIVOTを選択
        best_pivot = max(scores.keys(), key=lambda p: scores[p][0])
        confidence, matched_keywords = scores[best_pivot]

        # 温度感判定
        temperature = self._detect_temperature(text)

        # タイムスタンプを探す
        timestamp = self._find_timestamp(text, timestamp_map)

        return PIVOTInsight(
            id=str(uuid.uuid4()),
            pivot_voice=best_pivot,
            pivot_label=PIVOT.LABELS[best_pivot],
            pivot_score=PIVOT.SCORES[best_pivot],
            title=self._truncate(text, 50),
            body=text,
            confidence=confidence,
            temperature=temperature,
            matched_keywords=matched_keywords,
            video_id=video_id,
            timestamp=timestamp,
        )

    def _detect_temperature(self, text: str) -> str:
        """温度感を判定"""
        for level, indicators in TEMPERATURE_INDICATORS.items():
            if any(ind in text for ind in indicators):
                return level
        return "medium"

    def _truncate(self, text: str, max_len: int) -> str:
        """テキストを切り詰め"""
        text = text.replace("\n", " ").strip()
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


# ========================================
# 便利関数
# ========================================

def analyze_video(
    video: VideoData,
    domain: Optional[str] = None,
) -> VideoAnalysisResult:
    """
    シンプルなインターフェース - 単一動画分析

    Args:
        video: VideoDataオブジェクト
        domain: 業務ドメイン

    Returns:
        VideoAnalysisResult: 分析結果
    """
    analyzer = PIVOTAnalyzer(domain=domain)
    return analyzer.analyze_video(video)


def analyze_videos(
    videos: List[VideoData],
    domain: Optional[str] = None,
) -> List[VideoAnalysisResult]:
    """
    シンプルなインターフェース - 複数動画分析

    Args:
        videos: VideoDataのリスト
        domain: 業務ドメイン

    Returns:
        List[VideoAnalysisResult]: 分析結果リスト
    """
    analyzer = PIVOTAnalyzer(domain=domain)
    return analyzer.analyze_videos(videos)


def save_analysis_results(
    results: List[VideoAnalysisResult],
    output_path: str,
    format: str = "json",
) -> None:
    """
    分析結果を保存

    Args:
        results: VideoAnalysisResultのリスト
        output_path: 出力パス
        format: 出力フォーマット ("json" or "jsonl")
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if format == "jsonl":
        with open(path, "w", encoding="utf-8") as f:
            for result in results:
                for mart in result.to_mart_items():
                    f.write(json.dumps(mart, ensure_ascii=False) + "\n")
    else:
        data = {
            "analyzed_at": datetime.now().isoformat(),
            "total_videos": len(results),
            "results": [r.to_dict() for r in results],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def print_analysis_summary(results: List[VideoAnalysisResult]) -> None:
    """分析サマリーを表示"""
    print("\n" + "=" * 60)
    print("PIVOT分析サマリー")
    print("=" * 60)

    total_insights = sum(len(r.pivot_result.items) for r in results)
    total_score = sum(r.total_score for r in results)

    print(f"\n📊 分析動画数: {len(results)}")
    print(f"📝 総インサイト数: {total_insights}")
    print(f"📈 総合スコア: {total_score}")

    # PIVOT別集計
    pivot_totals = {p: 0 for p in PIVOT.ALL}
    for result in results:
        for pivot in PIVOT.ALL:
            pivot_totals[pivot] += len(result.pivot_result.by_pivot.get(pivot, []))

    print("\n📋 PIVOT分布:")
    print("-" * 40)
    pivot_labels = {
        "P": "Pain (課題)",
        "I": "Insecurity (不安)",
        "V": "Vision (要望)",
        "O": "Objection (抵抗)",
        "T": "Traction (成功)",
    }
    for pivot, label in pivot_labels.items():
        count = pivot_totals[pivot]
        bar = "█" * min(count, 20)
        print(f"  {pivot} {label:20} {count:3}件 {bar}")

    # 上位動画
    if results:
        print("\n🎯 課題が多い動画 (Top 5):")
        print("-" * 40)
        sorted_by_pain = sorted(results, key=lambda r: r.pain_count, reverse=True)[:5]
        for r in sorted_by_pain:
            print(f"  [{r.pain_count}P] {r.video_title[:40]}")

    print("\n" + "=" * 60)
