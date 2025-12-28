"""
AI 헤어 인플루언서 큐레이션 파이프라인
=====================================

파이프라인 구조:
1. Crawlers: 브랜드/인플루언서 데이터 수집
2. Processors: FIS 측정, 분류, 이미지 분석
3. Vectorizer: 브랜드/인플루언서 벡터맵 생성
4. Matcher: 코사인 유사도 기반 매칭
5. LLM Analyzer: 자연어 입력 분석
"""

from .crawlers import BrandCrawler
from .processors import FISCalculator, InfluencerClassifier, ImageAnalyzer
from .vectorizer import BrandVectorizer, InfluencerVectorizer
from .matcher import InfluencerMatcher
from .llm_analyzer import CampaignAnalyzer

__all__ = [
    'BrandCrawler',
    'FISCalculator',
    'InfluencerClassifier',
    'ImageAnalyzer',
    'BrandVectorizer',
    'InfluencerVectorizer',
    'InfluencerMatcher',
    'CampaignAnalyzer'
]
