"""
프로세서 모듈 - 인플루언서 데이터 처리
======================================

1. FISCalculator: Fake Integrity Score 계산 (허수 필터링)
2. InfluencerClassifier: Expert/Trendsetter 분류
3. ImageAnalyzer: 이미지 스타일 분석 (LLM 비전)
"""

import os
import math
import json
import base64
import hashlib
from typing import Dict, List, Tuple, Optional

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ============================================================
# FIS Calculator - 허수 계정 탐지
# ============================================================

class FISCalculator:
    """
    Fake Integrity Score 계산기

    지표:
    - V: 조회수 변동성 (CV < 0.1 이면 뷰봇 의심)
    - A: 참여 비대칭성 (좋아요/조회수 2%~15% 정상)
    - E: 댓글 엔트로피 (댓글 수 변동성)
    - ACS: 활동 안정성 (업로드 간격)
    - D: 지리적 정합성 (한국 타겟 확인)

    FIS = (w1×V + w2×E + w3×A + w4×ACS) × D/100
    """

    def __init__(self):
        # 가중치
        self.w_view = 0.25
        self.w_comment = 0.20
        self.w_engagement = 0.25
        self.w_activity = 0.15
        self.w_geo = 0.15

    def calculate(self, influencer: Dict) -> Dict:
        """FIS 점수 계산"""
        posts = influencer.get('recent_posts', [])

        v_score, v_detail = self._view_variability(posts)
        a_score, a_detail = self._engagement_asymmetry(posts)
        e_score, e_detail = self._comment_entropy(posts)
        acs_score, acs_detail = self._activity_stability(influencer)
        d_score, d_detail = self._geographic_consistency(influencer)

        # 기본 점수
        base_score = (
            self.w_view * v_score +
            self.w_comment * e_score +
            self.w_engagement * a_score +
            self.w_activity * acs_score
        )

        # 지리적 정합성 반영
        final_score = base_score * (d_score / 100) + (self.w_geo * d_score)
        final_score = max(0, min(100, final_score))

        # 판정
        if final_score >= 80:
            verdict = '신뢰 계정'
        elif final_score >= 60:
            verdict = '주의 필요'
        else:
            verdict = '허수 의심'

        return {
            'username': influencer.get('username', ''),
            'fis_score': round(final_score, 1),
            'verdict': verdict,
            'breakdown': {
                'view_variability': v_score,
                'engagement_asymmetry': a_score,
                'comment_entropy': e_score,
                'activity_stability': acs_score,
                'geographic_consistency': d_score
            }
        }

    def _view_variability(self, posts: List[Dict]) -> Tuple[float, Dict]:
        """조회수 변동성 (CV)"""
        views = [p.get('views', 0) for p in posts if p.get('views', 0) > 0]

        if len(views) < 2:
            return 50.0, {'status': 'insufficient_data'}

        mean = sum(views) / len(views)
        if mean == 0:
            return 0.0, {'status': 'zero_mean'}

        variance = sum((v - mean) ** 2 for v in views) / len(views)
        cv = math.sqrt(variance) / mean

        # CV 0.08~0.5 정상
        if cv < 0.03:
            score = 30.0
        elif cv < 0.05:
            score = 55.0
        elif cv < 0.08:
            score = 75.0
        elif cv < 0.50:
            score = 95.0
        else:
            score = 80.0

        return score, {'cv': round(cv, 4)}

    def _engagement_asymmetry(self, posts: List[Dict]) -> Tuple[float, Dict]:
        """좋아요/조회수 비율 (정상: 2%~15%)"""
        ratios = []
        for p in posts:
            views = p.get('views', 0)
            likes = p.get('likes', 0)
            if views > 0:
                ratios.append(likes / views)

        if not ratios:
            return 50.0, {'status': 'no_data'}

        avg = sum(ratios) / len(ratios)

        if 0.02 <= avg <= 0.15:
            score = 90.0
        elif 0.01 <= avg < 0.02 or 0.15 < avg <= 0.25:
            score = 70.0
        elif avg < 0.01:
            score = 30.0  # 뷰봇 의심
        else:
            score = 40.0  # 좋아요 구매 의심

        return score, {'avg_ratio': round(avg * 100, 2)}

    def _comment_entropy(self, posts: List[Dict]) -> Tuple[float, Dict]:
        """댓글 비율 (정상: 0.1%~2%)"""
        ratios = []
        for p in posts:
            views = p.get('views', 0)
            comments = p.get('comments', 0)
            if views > 0:
                ratios.append(comments / views)

        if not ratios:
            return 50.0, {'status': 'no_data'}

        avg = sum(ratios) / len(ratios)

        if 0.001 <= avg <= 0.02:
            score = 90.0
        elif 0.0005 <= avg < 0.001:
            score = 70.0
        elif 0.02 < avg <= 0.05:
            score = 75.0
        elif avg < 0.0005:
            score = 40.0
        else:
            score = 50.0

        return max(0, score), {'avg_ratio': round(avg * 100, 3)}

    def _activity_stability(self, influencer: Dict) -> Tuple[float, Dict]:
        """업로드 간격 (정상: 1~7일)"""
        interval = influencer.get('avg_upload_interval_days', 0)

        if interval == 0:
            return 50.0, {'status': 'no_data'}

        if 1 <= interval <= 7:
            score = 90.0
        elif 0.5 <= interval < 1:
            score = 75.0
        elif 7 < interval <= 14:
            score = 80.0
        elif interval < 0.5:
            score = 40.0  # 봇 의심
        else:
            score = 60.0

        return score, {'interval_days': interval}

    def _geographic_consistency(self, influencer: Dict) -> Tuple[float, Dict]:
        """한국 팔로워 비율"""
        audience = influencer.get('audience_countries', {})
        bio = influencer.get('bio', '')

        if not audience:
            return 80.0, {'status': 'no_data'}

        kr_ratio = audience.get('KR', 0)

        # 한국어 콘텐츠 확인
        has_korean = any('\uac00' <= c <= '\ud7a3' for c in bio)
        for p in influencer.get('recent_posts', []):
            if any('\uac00' <= c <= '\ud7a3' for c in p.get('caption', '')):
                has_korean = True
                break

        is_korean_target = has_korean or kr_ratio >= 0.50

        if is_korean_target:
            if kr_ratio >= 0.70:
                score = 95.0
            elif kr_ratio >= 0.50:
                score = 90.0
            elif kr_ratio >= 0.35:
                score = 80.0
            else:
                score = 65.0
        else:
            score = 75.0 if kr_ratio >= 0.30 else 75.0

        return score, {'kr_ratio': kr_ratio}


# ============================================================
# Influencer Classifier - Expert/Trendsetter 분류
# ============================================================

class InfluencerClassifier:
    """
    인플루언서 분류기

    Expert: 미용사, 살롱 원장, 시술 전문가
    Trendsetter: 스타일 크리에이터, 뷰티 인플루언서
    """

    EXPERT_KEYWORDS = [
        '미용사', '원장', '살롱', '시술', '예약', '펌', '염색약', '레시피',
        '컬러리스트', '헤어아티스트', '디렉터', '전문가', '자격증', '교육',
        '클리닉', '두피케어', '발레아쥬', '테크닉', '조색', '미용실'
    ]

    TRENDSETTER_KEYWORDS = [
        '스타일링', '데일리룩', 'OOTD', '추천', '꿀팁', '셀프', '홈케어',
        '트렌드', '패션', '일상', '크리에이터', '인플루언서', '협찬',
        '리뷰', '가성비', '꿀템', '솔직후기', '루틴', '유튜브'
    ]

    EXPERT_WEIGHTS = {'원장': 3.0, '미용사': 2.5, '살롱': 2.0, '시술': 2.0, '디렉터': 2.5}
    TRENDSETTER_WEIGHTS = {'크리에이터': 2.5, '인플루언서': 2.5, '트렌드세터': 3.0, '협찬': 2.0}

    def classify(self, influencer: Dict) -> Dict:
        """인플루언서 분류"""
        bio = influencer.get('bio', '')
        posts = influencer.get('recent_posts', [])
        captions = ' '.join([p.get('caption', '') for p in posts])
        full_text = f"{bio} {captions}"

        image_analysis = influencer.get('image_analysis', {})

        # 키워드 점수 계산
        expert_score = 0
        trend_score = 0
        expert_found = []
        trend_found = []

        for kw in self.EXPERT_KEYWORDS:
            count = full_text.count(kw)
            if count > 0:
                weight = self.EXPERT_WEIGHTS.get(kw, 1.0)
                expert_score += count * weight
                expert_found.append(kw)

        for kw in self.TRENDSETTER_KEYWORDS:
            count = full_text.count(kw)
            if count > 0:
                weight = self.TRENDSETTER_WEIGHTS.get(kw, 1.0)
                trend_score += count * weight
                trend_found.append(kw)

        total = expert_score + trend_score

        # 분류 결정
        if total == 0:
            # 이미지 분석 결과 활용
            if image_analysis:
                trend_rel = image_analysis.get('trend_relevance_score', 0.5)
                prof = image_analysis.get('professionalism_score', 0.5)

                if trend_rel > prof and trend_rel > 0.5:
                    classification = 'Trendsetter'
                    confidence = min(0.8, trend_rel)
                elif prof > trend_rel and prof > 0.5:
                    classification = 'Expert'
                    confidence = min(0.8, prof)
                else:
                    classification = 'Trendsetter'
                    confidence = 0.5
            else:
                classification = 'Trendsetter'
                confidence = 0.4
        else:
            expert_ratio = expert_score / total
            trend_ratio = trend_score / total

            if expert_ratio > trend_ratio:
                classification = 'Expert'
                confidence = expert_ratio
            else:
                classification = 'Trendsetter'
                confidence = trend_ratio

        # 역할 벡터
        if classification == 'Expert':
            role_vector = [confidence, 1 - confidence]
        else:
            role_vector = [1 - confidence, confidence]

        return {
            'username': influencer.get('username', ''),
            'classification': classification,
            'confidence': round(confidence, 3),
            'role_vector': role_vector,
            'expert_keywords': expert_found,
            'trend_keywords': trend_found
        }


# ============================================================
# Image Analyzer - LLM 비전 기반 이미지 분석
# ============================================================

class ImageAnalyzer:
    """
    LLM 비전 기반 이미지 스타일 분석

    - 스타일: luxury, natural, trendy, colorful, minimal, professional
    - 트렌드 부합도, 전문성 점수 등 추출
    """

    STYLE_CATEGORIES = ['luxury', 'natural', 'trendy', 'colorful', 'minimal', 'professional']

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = "gpt-4o-mini"

    def analyze(self, influencer: Dict, image_urls: List[str] = None) -> Dict:
        """인플루언서 비주얼 분석"""
        username = influencer.get('username', 'unknown')
        posts = influencer.get('recent_posts', [])

        # 이미 분석된 데이터가 있으면 사용
        if influencer.get('image_analysis'):
            return influencer['image_analysis']

        # 이미지 URL 추출
        if not image_urls:
            image_urls = [
                p.get('image_url') or p.get('thumbnail_url')
                for p in posts
                if p.get('image_url') or p.get('thumbnail_url')
            ]

        # 이미지가 없으면 시뮬레이션
        if not image_urls:
            return self._simulate_analysis(username, posts)

        # 각 이미지 분석
        analyses = []
        for url in image_urls[:5]:
            if url:
                result = self._analyze_single_image(url)
                analyses.append(result)

        return self._aggregate_results(username, analyses)

    def _analyze_single_image(self, image_url: str) -> Dict:
        """단일 이미지 분석"""
        if not self.api_key or not OPENAI_AVAILABLE:
            return self._simulate_single(image_url)

        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """헤어 스타일 비주얼 분석 전문가입니다.
JSON으로 응답하세요:
{
  "style_category": "luxury/natural/trendy/colorful/minimal/professional 중 하나",
  "style_confidence": 0.0-1.0,
  "professionalism_level": 0.0-1.0,
  "trend_relevance": 0.0-1.0,
  "color_palette": "warm/cool/neutral/vivid/muted"
}"""
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "이미지를 분석하세요."},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                max_tokens=300
            )

            text = response.choices[0].message.content.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            return json.loads(text.strip())

        except Exception as e:
            return self._simulate_single(image_url)

    def _simulate_single(self, source: str) -> Dict:
        """시뮬레이션 분석 (API 없을 때)"""
        hash_val = int(hashlib.md5(source.encode()).hexdigest(), 16)

        return {
            "style_category": self.STYLE_CATEGORIES[hash_val % len(self.STYLE_CATEGORIES)],
            "style_confidence": 0.6 + (hash_val % 40) / 100,
            "professionalism_level": 0.5 + (hash_val % 50) / 100,
            "trend_relevance": 0.5 + (hash_val % 50) / 100,
            "color_palette": ["warm", "cool", "neutral", "vivid", "muted"][hash_val % 5],
            "simulated": True
        }

    def _simulate_analysis(self, username: str, posts: List[Dict]) -> Dict:
        """포스트 기반 시뮬레이션"""
        analyses = []
        for i, post in enumerate(posts[:3]):
            sim = self._simulate_single(f"{username}_{post.get('caption', '')}_{i}")
            analyses.append(sim)
        return self._aggregate_results(username, analyses)

    def _aggregate_results(self, username: str, analyses: List[Dict]) -> Dict:
        """분석 결과 집계"""
        if not analyses:
            return {
                "username": username,
                "dominant_style": "trendy",
                "style_confidence": 0.5,
                "professionalism_score": 0.5,
                "trend_relevance_score": 0.5
            }

        # 스타일 집계
        style_counts = {}
        total_prof = 0
        total_trend = 0

        for a in analyses:
            style = a.get("style_category", "trendy")
            style_counts[style] = style_counts.get(style, 0) + 1
            total_prof += a.get("professionalism_level", 0.5)
            total_trend += a.get("trend_relevance", 0.5)

        dominant = max(style_counts, key=style_counts.get)
        avg_prof = total_prof / len(analyses)
        avg_trend = total_trend / len(analyses)

        return {
            "username": username,
            "dominant_style": dominant,
            "style_distribution": {k: v / len(analyses) for k, v in style_counts.items()},
            "style_confidence": 0.7,
            "professionalism_score": round(avg_prof, 3),
            "trend_relevance_score": round(avg_trend, 3),
            "visual_type_hint": "Trendsetter" if dominant in ["trendy", "colorful", "natural"] and avg_trend > 0.6 else "Expert"
        }


# 테스트
if __name__ == "__main__":
    # FIS 테스트
    fis_calc = FISCalculator()
    test_inf = {
        "username": "test_user",
        "recent_posts": [
            {"views": 45000, "likes": 3200, "comments": 89},
            {"views": 38000, "likes": 2800, "comments": 72}
        ],
        "audience_countries": {"KR": 0.92, "US": 0.03},
        "avg_upload_interval_days": 3.2
    }
    fis = fis_calc.calculate(test_inf)
    print(f"FIS: {fis['fis_score']} - {fis['verdict']}")

    # 분류 테스트
    classifier = InfluencerClassifier()
    test_inf["bio"] = "청담동 헤어살롱 원장 | 15년차 미용사"
    result = classifier.classify(test_inf)
    print(f"분류: {result['classification']} ({result['confidence']:.2f})")
