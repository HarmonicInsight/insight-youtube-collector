"""
PIVOT Analyzer module for YouTube transcript analysis.

Uses the PIVOT Framework to classify transcript text into:
- P (Pain): 課題・困りごと
- I (Insecurity): 不安・心配
- V (Vision): 要望・理想像
- O (Objection): 摩擦・抵抗
- T (Traction): 成功・強み
"""

from .pivot_analyzer import (
    PIVOTAnalyzer,
    PIVOTAnalysisResult,
    VideoAnalysisResult,
    analyze_video,
    analyze_videos,
)

__all__ = [
    "PIVOTAnalyzer",
    "PIVOTAnalysisResult",
    "VideoAnalysisResult",
    "analyze_video",
    "analyze_videos",
]
