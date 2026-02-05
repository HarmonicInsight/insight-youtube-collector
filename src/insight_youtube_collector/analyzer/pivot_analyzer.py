"""
PIVOT Analyzer - PIVOTフレームワークによるYouTube文字起こし分析（完全版）

PIVOTフレームワーク:
- 対象軸（What）: Process / Tool / People の3層モデル
- 声の分類（Voice）: P(Pain) / I(Insecurity) / V(Vision) / O(Objection) / T(Traction)

品詞分解エンジン:
- 動詞カテゴリ: 障害系/困難系/喪失系/願望系/拒否系/成功系
- 副詞スコアリング: 「非常に」×1.5 〜 「ほとんど」×0.4
- 語尾確信度: 断定1.0 〜 伝聞0.4
- 強度スコア: base × degree × certainty

使用例:
    from insight_youtube_collector.analyzer import PIVOTAnalyzer, analyze_videos

    analyzer = PIVOTAnalyzer(domain="biz_analysis", use_morphology=True)
    results = analyzer.analyze_videos(collected_videos)

    for result in results:
        print(f"{result.video_id}: Score={result.total_score}")
        for item in result.pivot_result.items:
            print(f"  {item.pivot_voice}: {item.title} (intensity={item.intensity_score:.2f})")
"""

import re
import uuid
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path
from enum import Enum

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
# 品詞分解エンジン - 動詞カテゴリ
# ========================================

class VerbCategory(Enum):
    """動詞カテゴリ"""
    OBSTACLE = "障害系"      # 止まる、落ちる、消える、壊れる → Pain
    DIFFICULTY = "困難系"    # 困る、詰まる、悩む、迷う → Pain
    LOSS = "喪失系"          # 失う、辞める、なくなる、減る → Insecurity
    DESIRE = "願望系"        # 欲しい、したい、なりたい → Vision
    REJECTION = "拒否系"     # 嫌がる、反対する、拒む → Objection
    SUCCESS = "成功系"       # できる、回る、うまくいく → Traction
    NEUTRAL = "通常"


VERB_CATEGORY_DICT = {
    VerbCategory.OBSTACLE: [
        "止まる", "落ちる", "消える", "壊れる", "間違える",
        "動かない", "起動しない", "フリーズする", "クラッシュする",
        "遅れる", "滞る", "停滞する", "中断する", "途切れる",
        "漏れる", "抜ける", "忘れる", "見落とす", "ミスる",
    ],
    VerbCategory.DIFFICULTY: [
        "困る", "詰まる", "悩む", "迷う", "分からない",
        "苦労する", "手間取る", "てこずる", "行き詰まる",
        "追いつかない", "間に合わない", "足りない", "不足する",
        "つまずく", "ハマる", "沼る",
    ],
    VerbCategory.LOSS: [
        "失う", "辞める", "なくなる", "減る", "いなくなる",
        "退職する", "離職する", "去る", "抜ける",
        "忘れられる", "引き継げない", "伝わらない",
        "陳腐化する", "時代遅れになる", "廃止される",
    ],
    VerbCategory.DESIRE: [
        "欲しい", "ほしい", "したい", "やりたい", "なりたい",
        "できるようにしたい", "実現したい", "導入したい",
        "改善したい", "効率化したい", "自動化したい",
        "変えたい", "見たい", "知りたい", "使いたい",
    ],
    VerbCategory.REJECTION: [
        "嫌がる", "反対する", "拒む", "拒否する", "無視する",
        "やりたくない", "したくない", "使いたくない",
        "認めない", "納得しない", "受け入れない",
        "嫌だ", "面倒くさい", "だるい",
    ],
    VerbCategory.SUCCESS: [
        "できる", "回る", "うまくいく", "定着する", "使いこなす",
        "機能する", "動く", "成功する", "達成する",
        "改善された", "効率化された", "便利になった",
        "助かる", "楽になる", "スムーズになる",
    ],
}

VERB_TO_CATEGORY = {}
for category, verbs in VERB_CATEGORY_DICT.items():
    for verb in verbs:
        VERB_TO_CATEGORY[verb] = category

VERB_CATEGORY_TO_PIVOT = {
    VerbCategory.OBSTACLE: "P",
    VerbCategory.DIFFICULTY: "P",
    VerbCategory.LOSS: "I",
    VerbCategory.DESIRE: "V",
    VerbCategory.REJECTION: "O",
    VerbCategory.SUCCESS: "T",
}


# ========================================
# 品詞分解エンジン - 形容詞センチメント
# ========================================

class Sentiment(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ANXIETY = "anxiety"
    NEUTRAL = "neutral"


ADJECTIVE_SENTIMENT_DICT = {
    Sentiment.NEGATIVE: [
        "遅い", "難しい", "面倒な", "煩雑な", "不便な", "分かりにくい",
        "複雑な", "大変な", "厳しい", "辛い", "きつい", "重い",
        "悪い", "ダメな", "まずい", "ひどい", "最悪な",
        "使いにくい", "見づらい", "分かりづらい",
        "古い", "時代遅れな", "非効率な", "無駄な",
    ],
    Sentiment.POSITIVE: [
        "早い", "速い", "簡単な", "便利な", "使いやすい", "分かりやすい",
        "シンプルな", "楽な", "快適な", "スムーズな", "効率的な",
        "良い", "いい", "素晴らしい", "最高な", "優秀な",
        "見やすい", "操作しやすい", "直感的な",
        "新しい", "モダンな", "最新な",
    ],
    Sentiment.ANXIETY: [
        "不安な", "心配な", "危うい", "怪しい", "危険な",
        "不確かな", "曖昧な", "脆い", "脆弱な",
        "属人的な", "ブラックボックスな",
    ],
}

ADJECTIVE_TO_SENTIMENT = {}
for sentiment, adjectives in ADJECTIVE_SENTIMENT_DICT.items():
    for adj in adjectives:
        ADJECTIVE_TO_SENTIMENT[adj] = sentiment


# ========================================
# 品詞分解エンジン - 副詞強度係数
# ========================================

DEGREE_ADVERBS = {
    1.5: ["非常に", "極めて", "全く", "絶対に", "到底", "めちゃくちゃ", "めっちゃ", "すごく", "ものすごく", "完全に", "100%", "間違いなく"],
    1.3: ["かなり", "とても", "相当", "大幅に", "大いに", "だいぶ", "ずいぶん", "なかなか"],
    1.0: [],
    0.7: ["少し", "多少", "やや", "ちょっと", "若干", "わずかに", "幾分", "いくらか"],
    0.4: ["ほとんど", "あまり", "たいして", "それほど"],
}

ADVERB_TO_DEGREE = {}
for factor, adverbs in DEGREE_ADVERBS.items():
    for adv in adverbs:
        ADVERB_TO_DEGREE[adv] = factor


# ========================================
# 品詞分解エンジン - 語尾パターン確信度
# ========================================

TAIL_PATTERNS = [
    # (pattern, certainty, pivot_tendency)
    # 断定 (確信度 1.0)
    (r"(?:です|ます|だ|である)$", 1.0, "P"),
    (r"(?:ですね|ますね|だね|だよね)$", 1.0, "P"),
    # 経験 (確信度 0.9)
    (r"(?:ました|した|てしまった|ちゃった)$", 0.9, "P"),
    (r"(?:ている|てる|ていた|てた)$", 0.9, "P"),
    # 推測 (確信度 0.6)
    (r"(?:かもしれない|かもしれません)$", 0.6, "I"),
    (r"(?:だろう|でしょう)$", 0.6, "I"),
    (r"(?:と思う|と思います)$", 0.6, "I"),
    (r"(?:気がする|気がします)$", 0.6, "I"),
    # 伝聞 (確信度 0.4)
    (r"(?:らしい|らしいです)$", 0.4, "I"),
    (r"(?:そうだ|そうです)$", 0.4, "I"),
    # 願望 (確信度 0.8)
    (r"(?:てほしい|てほしいです|ていただきたい)$", 0.8, "V"),
    (r"(?:たい|たいです|たいと思う)$", 0.8, "V"),
    (r"(?:ばいいのに|といいのに)$", 0.8, "V"),
    # 否定的願望 (確信度 0.8)
    (r"(?:たくない|たくないです)$", 0.8, "O"),
    (r"(?:てほしくない|ないでほしい)$", 0.8, "O"),
]


# ========================================
# キーワード・パターン辞書
# ========================================

PIVOT_KEYWORDS = {
    "P": {
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
            r"(.+?)(?:で|が)(?:ミス|エラー|トラブル)が(?:起きる|発生)",
        ],
    },
    "I": {
        "keywords": [
            "心配", "不安", "懸念", "気になる", "気がかり",
            "大丈夫か", "リスク", "危ない", "もしかしたら",
            "かもしれない", "恐れ", "属人化", "引継ぎ",
            "辞めたら", "いなくなったら", "将来", "今後",
            "先行き", "見通し", "ブラックボックス",
        ],
        "patterns": [
            r"(.+?)(?:が|を)(?:心配|不安|懸念)",
            r"(.+?)(?:かもしれない|恐れがある)",
            r"(?:辞め|いなくなっ)たら(.+?)(?:が|は|も)(?:困る|終わる|できない)",
            r"(.+?)(?:が|は)属人化(?:している|されている)",
        ],
    },
    "V": {
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
            r"(.+?)(?:を|が)(?:導入|実現)(?:したい|してほしい)",
        ],
    },
    "O": {
        "keywords": [
            "反対", "抵抗", "無理", "やりたくない",
            "前もダメだった", "失敗した", "うまくいかなかった",
            "嫌", "面倒", "ストレス", "対立", "衝突",
            "やらされ", "強制", "納得できない",
            "理解されない", "協力してくれない", "押し付け",
        ],
        "patterns": [
            r"(?:前|以前|過去)(?:に|も)(.+?)(?:が|で)(?:失敗|ダメ|うまくいかなかった)",
            r"(.+?)(?:に|は)(?:反対|抵抗)(?:がある|している)",
            r"(.+?)(?:を|は)(?:やりたくない|したくない)",
            r"(.+?)(?:が|は)(?:納得できない|理解できない)",
        ],
    },
    "T": {
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
            r"(.+?)(?:は|が)(?:強み|得意|定着している)",
            r"(.+?)(?:は|が)(?:うまく|ちゃんと)(?:回っている|機能している)",
        ],
    },
}


# ========================================
# 対象軸（Layer）パターン
# ========================================

LAYER_PATTERNS = {
    "process": {
        "keywords": [
            "管理", "処理", "作業", "業務", "対応", "報告",
            "確認", "承認", "申請", "発注", "受注", "請求",
            "入力", "出力", "集計", "分析", "検査", "点検",
            "棚卸", "在庫", "出荷", "配送", "仕入", "調達",
            "採用", "評価", "教育", "研修", "勤怠", "給与",
        ],
        "extraction_patterns": [
            r"(.{2,15}管理)",
            r"(.{2,15}処理)",
            r"(.{2,10}業務)",
            r"(.{2,10}作業)",
        ],
    },
    "tool": {
        "keywords": [
            "Excel", "エクセル", "Word", "ワード", "PowerPoint", "パワポ",
            "メール", "Slack", "Teams", "Zoom", "LINE", "チャット",
            "システム", "ソフト", "アプリ", "ツール",
            "紙", "帳票", "伝票", "FAX", "電話",
            "基幹", "ERP", "CRM", "SFA", "BIツール",
            "スプレッドシート", "Googleスプレッドシート",
            "kintone", "キントーン", "Salesforce", "SAP",
        ],
        "extraction_patterns": [
            r"(Excel|エクセル|Word|ワード|PowerPoint|パワポ)",
            r"(Slack|Teams|Zoom|LINE|メール)",
            r"(.{2,10}システム)",
            r"(紙|帳票|伝票|FAX|電話)",
        ],
    },
    "people": {
        "keywords": [
            "担当", "担当者", "責任者", "マネージャー", "リーダー",
            "部長", "課長", "係長", "社長", "役員", "経営",
            "営業", "経理", "総務", "人事", "開発", "現場",
            "部署", "チーム", "グループ", "外注", "協力会社",
            "新人", "ベテラン", "パート", "派遣", "アルバイト",
            "上司", "部下", "同僚", "後輩", "先輩",
        ],
        "extraction_patterns": [
            r"(.{2,10}部)",
            r"(.{2,10}課)",
            r"(担当者?|責任者|マネージャー|リーダー)",
            r"(外注|協力会社|パート|派遣)",
        ],
    },
}


# ========================================
# 業務ドメイン別PIVOT重み
# ========================================

DOMAIN_PIVOT_WEIGHTS = {
    "requirements": {"P": 1.5, "I": 1.0, "V": 2.0, "O": 0.8, "T": 1.0},
    "biz_analysis": {"P": 2.0, "I": 1.2, "V": 1.0, "O": 1.0, "T": 1.5},
    "hr_evaluation": {"P": 1.0, "I": 2.0, "V": 1.5, "O": 1.8, "T": 1.2},
    "daily_concerns": {"P": 1.8, "I": 2.0, "V": 1.0, "O": 1.2, "T": 1.0},
    "customer_voice": {"P": 1.8, "I": 1.0, "V": 2.0, "O": 1.2, "T": 1.5},
    "retrospective": {"P": 1.5, "I": 1.2, "V": 1.5, "O": 1.2, "T": 1.8},
}


# ========================================
# 型定義
# ========================================

@dataclass
class MorphologyResult:
    """品詞分解結果"""
    verb_categories: List[VerbCategory] = field(default_factory=list)
    sentiment_score: float = 0.0
    degree_factor: float = 1.0
    certainty: float = 1.0
    pivot_tendency: Optional[str] = None
    matched_verbs: List[str] = field(default_factory=list)
    matched_adjectives: List[str] = field(default_factory=list)
    matched_adverbs: List[str] = field(default_factory=list)


@dataclass
class PIVOTInsight:
    """PIVOT分類されたインサイト"""
    id: str
    pivot_voice: str
    pivot_label: str
    pivot_score: int
    target_layers: Dict[str, Optional[str]]  # process, tool, people
    title: str
    body: str
    confidence: float
    temperature: str
    matched_keywords: List[str] = field(default_factory=list)
    video_id: Optional[str] = None
    timestamp: Optional[float] = None
    # 品詞分解情報
    intensity_score: float = 0.0
    degree_factor: float = 1.0
    certainty: float = 1.0
    reasoning: str = ""


@dataclass
class PIVOTAnalysisResult:
    """PIVOT分析結果"""
    items: List[PIVOTInsight]
    by_pivot: Dict[str, List[PIVOTInsight]]
    by_process: Dict[str, Dict[str, int]]
    by_tool: Dict[str, Dict[str, int]]
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
                    "target_layers": item.target_layers,
                    "morphology": {
                        "intensity_score": round(item.intensity_score, 2),
                        "degree_factor": item.degree_factor,
                        "certainty": item.certainty,
                        "reasoning": item.reasoning,
                    },
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
                "target_layers": item.target_layers,
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
                "morphology": {
                    "intensity_score": round(item.intensity_score, 2),
                    "degree_factor": item.degree_factor,
                    "certainty": item.certainty,
                    "reasoning": item.reasoning,
                },
            })

        return marts


# ========================================
# 品詞分解エンジン
# ========================================

class MorphologyAnalyzer:
    """品詞分解エンジン（ルールベース）"""

    def __init__(self):
        self.tail_patterns = [(re.compile(p), c, t) for p, c, t in TAIL_PATTERNS]

    def analyze(self, text: str) -> MorphologyResult:
        result = MorphologyResult()

        # 動詞抽出
        for verb, category in VERB_TO_CATEGORY.items():
            if verb in text:
                result.verb_categories.append(category)
                result.matched_verbs.append(verb)

        # 形容詞抽出
        positive_count = 0
        negative_count = 0
        anxiety_count = 0
        for adj, sentiment in ADJECTIVE_TO_SENTIMENT.items():
            if adj in text:
                result.matched_adjectives.append(adj)
                if sentiment == Sentiment.POSITIVE:
                    positive_count += 1
                elif sentiment == Sentiment.NEGATIVE:
                    negative_count += 1
                elif sentiment == Sentiment.ANXIETY:
                    anxiety_count += 1

        total_adj = positive_count + negative_count + anxiety_count
        if total_adj > 0:
            result.sentiment_score = (positive_count - negative_count - anxiety_count) / total_adj
            result.sentiment_score = max(-1.0, min(1.0, result.sentiment_score))

        # 副詞抽出
        max_degree = 1.0
        for adv, factor in ADVERB_TO_DEGREE.items():
            if adv in text:
                result.matched_adverbs.append(adv)
                if factor > max_degree:
                    max_degree = factor
                elif factor < 1.0 and max_degree == 1.0:
                    max_degree = factor
        result.degree_factor = max_degree

        # 語尾パターン検出
        for pattern, certainty, pivot_tendency in self.tail_patterns:
            if pattern.search(text):
                result.certainty = certainty
                result.pivot_tendency = pivot_tendency
                break

        return result


# ========================================
# PIVOT Analyzer
# ========================================

class PIVOTAnalyzer:
    """YouTube文字起こしのPIVOT分析エンジン（完全版）"""

    def __init__(
        self,
        domain: Optional[str] = None,
        min_confidence: float = 0.3,
        use_morphology: bool = True,
        split_by_sentence: bool = True,
    ):
        self.domain = domain
        self.min_confidence = min_confidence
        self.use_morphology = use_morphology
        self.split_by_sentence = split_by_sentence

        self.morphology_analyzer = MorphologyAnalyzer() if use_morphology else None
        self.weights = DOMAIN_PIVOT_WEIGHTS.get(domain, {p: 1.0 for p in PIVOT.ALL})

        self.pivot_patterns = {}
        for pivot, config in PIVOT_KEYWORDS.items():
            self.pivot_patterns[pivot] = [
                re.compile(p) for p in config.get("patterns", [])
            ]

        self.layer_extraction_patterns = {}
        for layer, config in LAYER_PATTERNS.items():
            self.layer_extraction_patterns[layer] = [
                re.compile(p) for p in config.get("extraction_patterns", [])
            ]

    def analyze_video(self, video: VideoData) -> VideoAnalysisResult:
        transcript_text = video.transcript.full_text if video.transcript else ""

        if not transcript_text:
            return VideoAnalysisResult(
                video_id=video.video_id,
                video_title=video.metadata.title,
                channel=video.metadata.channel,
                analyzed_at=datetime.now().isoformat(),
                pivot_result=PIVOTAnalysisResult(
                    items=[],
                    by_pivot={p: [] for p in PIVOT.ALL},
                    by_process={},
                    by_tool={},
                    total_score=0,
                    sentiment_index=0.0,
                    stats={"total": 0, "by_pivot": {p: 0 for p in PIVOT.ALL}},
                ),
            )

        sentences = self._split_sentences(transcript_text)
        timestamp_map = self._build_timestamp_map(video)

        items: List[PIVOTInsight] = []
        by_pivot: Dict[str, List[PIVOTInsight]] = {p: [] for p in PIVOT.ALL}
        by_process: Dict[str, Dict[str, int]] = {}
        by_tool: Dict[str, Dict[str, int]] = {}

        for sentence in sentences:
            insight = self._classify_sentence(sentence, video.video_id, timestamp_map)
            if insight and insight.confidence >= self.min_confidence:
                items.append(insight)
                by_pivot[insight.pivot_voice].append(insight)

                # 対象軸別集計
                process = insight.target_layers.get("process")
                tool = insight.target_layers.get("tool")

                if process:
                    if process not in by_process:
                        by_process[process] = {p: 0 for p in PIVOT.ALL}
                    by_process[process][insight.pivot_voice] += 1

                if tool:
                    if tool not in by_tool:
                        by_tool[tool] = {p: 0 for p in PIVOT.ALL}
                    by_tool[tool][insight.pivot_voice] += 1

        # ドメイン重みを適用してソート
        items = self._apply_domain_weights(items)

        total_score = sum(item.pivot_score for item in items)
        sentiment_index = total_score / len(items) if items else 0.0

        stats = {
            "total": len(items),
            "by_pivot": {p: len(lst) for p, lst in by_pivot.items()},
            "domain": self.domain,
            "total_score": total_score,
            "sentiment_index": sentiment_index,
        }

        return VideoAnalysisResult(
            video_id=video.video_id,
            video_title=video.metadata.title,
            channel=video.metadata.channel,
            analyzed_at=datetime.now().isoformat(),
            pivot_result=PIVOTAnalysisResult(
                items=items,
                by_pivot=by_pivot,
                by_process=by_process,
                by_tool=by_tool,
                total_score=total_score,
                sentiment_index=sentiment_index,
                stats=stats,
            ),
        )

    def analyze_videos(self, videos: List[VideoData]) -> List[VideoAnalysisResult]:
        return [self.analyze_video(video) for video in videos]

    def _split_sentences(self, text: str) -> List[str]:
        if not self.split_by_sentence:
            return [text]
        sentences = re.split(r'[。．！？\n]+', text)
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 10]

    def _build_timestamp_map(self, video: VideoData) -> Dict[str, float]:
        timestamp_map = {}
        if video.transcript and video.transcript.segments:
            for seg in video.transcript.segments:
                key = seg.text[:30] if len(seg.text) > 30 else seg.text
                timestamp_map[key] = seg.start
        return timestamp_map

    def _find_timestamp(self, text: str, timestamp_map: Dict[str, float]) -> Optional[float]:
        for key, timestamp in timestamp_map.items():
            if key in text or text[:30] in key:
                return timestamp
        return None

    def _extract_layers(self, text: str) -> Dict[str, Optional[str]]:
        """対象軸（Layer）を抽出"""
        layers: Dict[str, Optional[str]] = {"process": None, "tool": None, "people": None}

        for layer, config in LAYER_PATTERNS.items():
            for kw in config["keywords"]:
                if kw in text:
                    for pattern in self.layer_extraction_patterns[layer]:
                        match = pattern.search(text)
                        if match:
                            layers[layer] = match.group(1)
                            break
                    if layers[layer]:
                        break
                    if not layers[layer]:
                        layers[layer] = kw
                        break

        return layers

    def _classify_sentence(
        self,
        text: str,
        video_id: str,
        timestamp_map: Dict[str, float],
    ) -> Optional[PIVOTInsight]:
        if not text.strip():
            return None

        # 品詞分解
        morph_result = None
        degree_factor = 1.0
        certainty = 1.0
        reasoning = ""

        if self.use_morphology and self.morphology_analyzer:
            morph_result = self.morphology_analyzer.analyze(text)
            degree_factor = morph_result.degree_factor
            certainty = morph_result.certainty

            # 品詞分解によるPIVOT推定
            morph_pivot, morph_conf, morph_reason = self._infer_pivot_from_morphology(morph_result, text)
            if morph_pivot and morph_conf >= 0.6:
                pivot_voice = morph_pivot
                confidence = morph_conf
                matched_keywords = morph_result.matched_verbs + morph_result.matched_adjectives
                reasoning = morph_reason
            else:
                # フォールバック: キーワードベース
                pivot_result = self._classify_pivot(text)
                if not pivot_result:
                    return None
                pivot_voice, confidence, matched_keywords = pivot_result
                reasoning = "キーワードベース"
        else:
            pivot_result = self._classify_pivot(text)
            if not pivot_result:
                return None
            pivot_voice, confidence, matched_keywords = pivot_result
            reasoning = "キーワードベース"

        # 対象軸抽出
        target_layers = self._extract_layers(text)

        # 温度感判定
        temperature = self._detect_temperature(text)

        # 強度スコア算出
        base_score = PIVOT.SCORES[pivot_voice]
        intensity_score = base_score * degree_factor * certainty

        # タイムスタンプ
        timestamp = self._find_timestamp(text, timestamp_map)

        return PIVOTInsight(
            id=str(uuid.uuid4()),
            pivot_voice=pivot_voice,
            pivot_label=PIVOT.LABELS[pivot_voice],
            pivot_score=PIVOT.SCORES[pivot_voice],
            target_layers=target_layers,
            title=self._truncate(text, 50),
            body=text,
            confidence=confidence,
            temperature=temperature,
            matched_keywords=matched_keywords,
            video_id=video_id,
            timestamp=timestamp,
            intensity_score=intensity_score,
            degree_factor=degree_factor,
            certainty=certainty,
            reasoning=reasoning,
        )

    def _infer_pivot_from_morphology(
        self,
        morph: MorphologyResult,
        text: str,
    ) -> Tuple[Optional[str], float, str]:
        """品詞分解結果からPIVOTを推定"""
        reasons = []

        # 動詞カテゴリからの判定
        for cat in morph.verb_categories:
            if cat in VERB_CATEGORY_TO_PIVOT:
                pivot = VERB_CATEGORY_TO_PIVOT[cat]
                if cat == VerbCategory.OBSTACLE or cat == VerbCategory.DIFFICULTY:
                    if morph.sentiment_score < 0 and morph.certainty >= 0.9:
                        reasons.append(f"{cat.value}動詞+ネガティブ形容詞+高確信度")
                        return "P", 0.9, "; ".join(reasons)
                elif cat == VerbCategory.LOSS:
                    reasons.append(f"{cat.value}動詞")
                    return "I", 0.85, "; ".join(reasons)
                elif cat == VerbCategory.DESIRE:
                    reasons.append(f"{cat.value}動詞")
                    return "V", 0.85, "; ".join(reasons)
                elif cat == VerbCategory.REJECTION:
                    reasons.append(f"{cat.value}動詞")
                    return "O", 0.85, "; ".join(reasons)
                elif cat == VerbCategory.SUCCESS:
                    if morph.sentiment_score > 0:
                        reasons.append(f"{cat.value}動詞+ポジティブ形容詞")
                        return "T", 0.9, "; ".join(reasons)
                    else:
                        reasons.append(f"{cat.value}動詞")
                        return "T", 0.7, "; ".join(reasons)

        # 語尾パターンからの判定
        if morph.pivot_tendency:
            if morph.certainty <= 0.6 and morph.pivot_tendency == "I":
                reasons.append("推測/伝聞語尾")
                return "I", 0.75, "; ".join(reasons)
            elif morph.pivot_tendency == "V":
                reasons.append("願望語尾")
                return "V", 0.8, "; ".join(reasons)
            elif morph.pivot_tendency == "O":
                reasons.append("否定的願望語尾")
                return "O", 0.8, "; ".join(reasons)

        # 形容詞のみでの判定
        if morph.sentiment_score < -0.5:
            reasons.append("ネガティブ形容詞優位")
            return "P", 0.6, "; ".join(reasons)
        if morph.sentiment_score > 0.5:
            reasons.append("ポジティブ形容詞優位")
            return "T", 0.6, "; ".join(reasons)

        return None, 0.0, ""

    def _classify_pivot(self, text: str) -> Optional[Tuple[str, float, List[str]]]:
        """キーワード/パターンベースのPIVOT分類"""
        scores: Dict[str, Tuple[float, List[str]]] = {}

        for pivot in PIVOT.ALL:
            config = PIVOT_KEYWORDS[pivot]
            keywords = config["keywords"]
            patterns = self.pivot_patterns[pivot]

            matched_kw = [kw for kw in keywords if kw in text]
            kw_score = min(len(matched_kw) * 0.2, 0.6)

            pat_score = 0.0
            for pattern in patterns:
                if pattern.search(text):
                    pat_score = 0.35
                    break

            total_score = min(kw_score + pat_score, 0.95)

            if total_score > 0:
                scores[pivot] = (total_score, matched_kw)

        if not scores:
            return None

        best_pivot = max(scores.keys(), key=lambda p: scores[p][0])
        confidence, matched_keywords = scores[best_pivot]

        return best_pivot, confidence, matched_keywords

    def _detect_temperature(self, text: str) -> str:
        high_indicators = ["絶対", "本当に", "非常に", "とても", "すごく", "めちゃくちゃ", "いつも", "毎回", "必ず"]
        medium_indicators = ["かなり", "結構", "わりと", "時々", "たまに", "よく"]
        low_indicators = ["少し", "ちょっと", "多少", "若干", "たぶん", "おそらく"]

        if any(ind in text for ind in high_indicators):
            return "high"
        elif any(ind in text for ind in medium_indicators):
            return "medium"
        elif any(ind in text for ind in low_indicators):
            return "low"
        return "medium"

    def _apply_domain_weights(self, items: List[PIVOTInsight]) -> List[PIVOTInsight]:
        def weighted_score(item: PIVOTInsight) -> float:
            weight = self.weights.get(item.pivot_voice, 1.0)
            return abs(item.intensity_score) * weight

        return sorted(items, key=weighted_score, reverse=True)

    def _truncate(self, text: str, max_len: int) -> str:
        text = text.replace("\n", " ").strip()
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


# ========================================
# 便利関数
# ========================================

def analyze_video(video: VideoData, domain: Optional[str] = None) -> VideoAnalysisResult:
    analyzer = PIVOTAnalyzer(domain=domain)
    return analyzer.analyze_video(video)


def analyze_videos(videos: List[VideoData], domain: Optional[str] = None) -> List[VideoAnalysisResult]:
    analyzer = PIVOTAnalyzer(domain=domain)
    return analyzer.analyze_videos(videos)


def save_analysis_results(
    results: List[VideoAnalysisResult],
    output_path: str,
    format: str = "json",
) -> None:
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
    print("\n" + "=" * 60)
    print("PIVOT分析サマリー（品詞分解エンジン付き）")
    print("=" * 60)

    total_insights = sum(len(r.pivot_result.items) for r in results)
    total_score = sum(r.total_score for r in results)

    # 強度スコア集計
    total_intensity = sum(
        abs(item.intensity_score)
        for r in results
        for item in r.pivot_result.items
    )
    avg_intensity = total_intensity / total_insights if total_insights > 0 else 0

    print(f"\n📊 分析動画数: {len(results)}")
    print(f"📝 総インサイト数: {total_insights}")
    print(f"📈 総合スコア: {total_score}")
    print(f"⚡ 平均強度スコア: {avg_intensity:.2f}")

    # PIVOT別集計
    pivot_totals = {p: 0 for p in PIVOT.ALL}
    pivot_intensity = {p: 0.0 for p in PIVOT.ALL}
    for result in results:
        for pivot in PIVOT.ALL:
            items = result.pivot_result.by_pivot.get(pivot, [])
            pivot_totals[pivot] += len(items)
            pivot_intensity[pivot] += sum(abs(i.intensity_score) for i in items)

    print("\n📋 PIVOT分布（強度スコア付き）:")
    print("-" * 50)
    pivot_labels = {
        "P": "Pain (課題)",
        "I": "Insecurity (不安)",
        "V": "Vision (要望)",
        "O": "Objection (抵抗)",
        "T": "Traction (成功)",
    }
    for pivot, label in pivot_labels.items():
        count = pivot_totals[pivot]
        intensity = pivot_intensity[pivot]
        bar = "█" * min(count, 20)
        print(f"  {pivot} {label:20} {count:3}件 (強度:{intensity:6.1f}) {bar}")

    # 対象軸（Process）別集計
    process_totals: Dict[str, int] = {}
    for result in results:
        for process, counts in result.pivot_result.by_process.items():
            if process not in process_totals:
                process_totals[process] = 0
            process_totals[process] += sum(counts.values())

    if process_totals:
        print("\n🔧 対象軸（Process）別:")
        print("-" * 40)
        for process, count in sorted(process_totals.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {process}: {count}件")

    # 上位動画
    if results:
        print("\n🎯 課題が多い動画 (Top 5):")
        print("-" * 40)
        sorted_by_pain = sorted(results, key=lambda r: r.pain_count, reverse=True)[:5]
        for r in sorted_by_pain:
            print(f"  [{r.pain_count}P] {r.video_title[:40]}")

    print("\n" + "=" * 60)
