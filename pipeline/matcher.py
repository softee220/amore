"""
매처 모듈 - 브랜드-인플루언서 매칭 (v2)
=======================================

적합도 계산 공식:
  적합도 = (유사도 × 0.25) + (FIS × 0.15) + (제품적합도 × 0.35) + (고유특성 × 0.25)

제품 적합도 판단 기준:
  1. professional (전문가용): 살롱 전용 제품 → Expert 필수
  2. expert_oriented (전문성 지향 홍보): 성분/효능 강조 → Expert 선호, Trendsetter도 가능
  3. consumer (일반 소비자용): 감성/트렌드 중심 → Trendsetter 선호

파이프라인:
1. 브랜드 + 제품라인 정보 로드
2. 제품의 마케팅 접근법(marketing_approach) 확인
3. 인플루언서 분류 및 전문성 수준 평가
4. 제품-인플루언서 적합도 계산
5. 다양성 보장하며 추천
"""

import os
import json
import math
from pathlib import Path
from typing import Dict, List, Optional
from .processors import FISCalculator, InfluencerClassifier
from .vectorizer import BrandVectorizer, InfluencerVectorizer, cosine_similarity

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# LLM 추천 이유 생성 프롬프트
REASON_GENERATION_PROMPT = """인플루언서 추천 이유를 자연스럽고 설득력 있는 한국어 문장으로 작성하세요.

## 브랜드 정보
- 브랜드: {brand_name}
- 브랜드 스타일: {brand_style} (브랜드가 일반적으로 추구하는 이미지)
- 브랜드 전문성 수준: {expertise_level}
- 슬로건: {slogan}
- 핵심 가치: {core_values}

## 이번 캠페인/제품 정보
- 제품: {product_type}
- 마케팅 접근법: {marketing_approach} (professional=살롱전문가용, expert_oriented=전문성강조, consumer=일반소비자용)
- 캠페인 설명: {campaign_description}

## 브랜드와 제품의 관계
{brand_product_context}

## 인플루언서 정보
- 이름: @{username}
- 유형: {classification} (Expert=전문가, Trendsetter=트렌드세터)
- 팔로워: {followers}명
- 소개: {bio}
- 콘텐츠 분위기: {vibe}
- 적합도 점수: {fit_score}%

## 작성 지침
1. 첫 문장: 인플루언서 소개 (팔로워 수, 역할)
2. 빈 줄
3. 둘째~셋째 문장: 왜 이 인플루언서가 이번 캠페인에 적합한지 (브랜드와 제품 특성 모두 고려)
4. 마지막 문장: 기대되는 효과

**중요**:
- 브랜드의 기본 성격과 이번 제품/캠페인의 특성이 다르면 그 점을 자연스럽게 반영하세요.
- 예: "브랜드는 전문적인 이미지를 추구하지만, 이번 제품은 대중적인 접근이 필요한 만큼..."
- 템플릿처럼 딱딱하지 않고, 마치 마케팅 담당자가 설명하듯 자연스럽게 작성하세요.
- 3~4문장 정도로 간결하게 작성하세요.

추천 이유를 작성하세요:"""


class InfluencerMatcher:
    """브랜드-인플루언서 매칭 엔진 (v2)"""

    def __init__(self):
        self.fis_calc = FISCalculator()
        self.classifier = InfluencerClassifier()
        self.brand_vectorizer = BrandVectorizer()
        self.inf_vectorizer = InfluencerVectorizer()

        # 제품 분류 체계 로드
        self.taxonomy = self._load_taxonomy()

        # OpenAI API 키
        self.api_key = os.getenv("OPENAI_API_KEY")

        # 마케팅 접근법별 가중치
        self.approach_weights = {
            'professional': {
                'Expert': {'base': 1.0, 'certification_bonus': 0.2, 'tutorial_bonus': 0.15},
                'Trendsetter': {'base': 0.3, 'penalty_reason': '전문 시술 콘텐츠 불가'}
            },
            'expert_oriented': {
                'Expert': {'base': 0.9, 'knowledge_bonus': 0.15},
                'Trendsetter': {'base': 0.7, 'education_bonus': 0.1, 'trust_bonus': 0.1}
            },
            'consumer': {
                'Expert': {'base': 0.6, 'credibility_bonus': 0.1},
                'Trendsetter': {'base': 1.0, 'trend_bonus': 0.15, 'lifestyle_bonus': 0.1}
            }
        }

    def _load_taxonomy(self) -> Dict:
        """제품 분류 체계 로드"""
        taxonomy_path = Path(__file__).parent.parent / "data" / "product_taxonomy.json"
        if taxonomy_path.exists():
            with open(taxonomy_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def match(
        self,
        brand_data: Dict,
        influencers: List[Dict],
        top_k: int = 5,
        min_fis: float = 40.0,
        expert_count: int = None,
        trendsetter_count: int = None,
        product_line: str = None  # 특정 제품라인 지정 가능
    ) -> Dict:
        """
        브랜드에 맞는 인플루언서 매칭 (v2)

        Args:
            brand_data: 브랜드 정보
            influencers: 인플루언서 리스트
            top_k: 추천 인원 수
            min_fis: 최소 FIS 점수
            expert_count: 전문가 수 (None이면 자동)
            trendsetter_count: 트렌드세터 수 (None이면 자동)
            product_line: 특정 제품라인 (없으면 product_type 사용)

        Returns:
            추천 결과
        """
        # 1. 브랜드 벡터 생성
        brand_vector = self.brand_vectorizer.vectorize(brand_data)

        # 2. 제품 정보 및 마케팅 접근법 결정
        product_info = self._get_product_info(brand_data, product_line)
        marketing_approach = product_info.get('marketing_approach', 'consumer')
        product_type = product_info.get('product_type', brand_data.get('product_type', '샴푸'))
        ideal_influencer = product_info.get('ideal_influencer', 'Both')
        expertise_keywords = product_info.get('expertise_keywords', [])

        # 3. 선호 인플루언서 타입 결정 (마케팅 접근법 기반)
        preferred_type = self._get_preferred_type_v2(marketing_approach, ideal_influencer)

        # 4. 각 인플루언서 분석 및 점수 계산
        all_results = []

        for influencer in influencers:
            # 분류
            classification = self.classifier.classify(influencer)

            # FIS 계산
            fis_result = self.fis_calc.calculate(influencer)
            fis_score = fis_result['fis_score']

            # FIS 필터링
            if fis_score < min_fis:
                continue

            # 인플루언서 벡터 생성
            inf_vector = self.inf_vectorizer.vectorize(influencer, classification)

            # 인플루언서 전문성 평가
            expertise_score = self._evaluate_expertise(influencer, expertise_keywords)

            # 매칭 점수 계산 (v2: 제품적합도 반영)
            match_result = self._calculate_match_score_v2(
                brand_vector=brand_vector,
                inf_vector=inf_vector,
                fis_score=fis_score,
                classification=classification['classification'],
                marketing_approach=marketing_approach,
                influencer=influencer,
                brand_data=brand_data,
                expertise_score=expertise_score,
                expertise_keywords=expertise_keywords
            )

            all_results.append({
                'username': influencer.get('username', ''),
                'followers': influencer.get('followers', 0),
                'classification': classification['classification'],
                'confidence': classification['confidence'],
                'fis_score': fis_score,
                'fis_verdict': fis_result['verdict'],
                'match_score': round(match_result['total_score'], 4),
                'score_breakdown': match_result['breakdown'],
                'similarity': round(cosine_similarity(brand_vector, inf_vector), 4),
                'bio': influencer.get('bio', ''),
                'image_analysis': influencer.get('image_analysis', {}),
                'expertise_score': expertise_score,
                'marketing_approach': marketing_approach
            })

        # 5. 다양성 보장하며 선택
        selected = self._select_diverse(
            all_results, top_k, preferred_type,
            expert_count, trendsetter_count
        )

        # 6. 추천 사유 생성 (v2: 제품적합도 포함)
        recommendations = []
        for i, result in enumerate(selected, 1):
            reason = self._generate_reason_v2(brand_data, result, product_info)
            recommendations.append({
                'rank': i,
                'username': result['username'],
                'followers': result['followers'],
                'type': result['classification'],
                'match_score': min(100.0, max(0.0, round(result['match_score'] * 100, 1))),
                'fis_score': result['fis_score'],
                'reason': reason,
                'details': {
                    'confidence': result['confidence'],
                    'similarity': result['similarity'],
                    'bio': result['bio'],
                    'fis_verdict': result['fis_verdict'],
                    'score_breakdown': result.get('score_breakdown', {}),
                    'expertise_score': result.get('expertise_score', 0.5),
                    'marketing_approach': result.get('marketing_approach', 'consumer')
                }
            })

        return {
            'brand_info': {
                'name': brand_data.get('brand_name', ''),
                'style': brand_data.get('aesthetic_style', 'Trendy'),
                'product': product_type,
                'product_line': product_line,
                'marketing_approach': marketing_approach,
                'recommended_type': preferred_type,
                'expertise_level': brand_data.get('expertise_level', 'low')
            },
            'total_analyzed': len(influencers),
            'total_passed_fis': len(all_results),
            'recommendations': recommendations
        }

    def _get_product_info(self, brand_data: Dict, product_line: str = None) -> Dict:
        """
        브랜드 데이터에서 제품 정보 추출

        우선순위:
        1. brand_data['marketing_approach'] (제품 설명에서 분석한 접근법)
        2. product_line 정보
        3. product_type 매칭
        4. 브랜드 전문성 수준 기반 기본값
        """
        product_lines = brand_data.get('product_lines', {})

        # 제품 설명에서 분석된 marketing_approach가 있으면 우선 사용
        description_marketing_approach = brand_data.get('marketing_approach')
        description_override = brand_data.get('description_override', False)

        # 특정 제품라인이 지정된 경우
        if product_line and product_line in product_lines:
            line_info = product_lines[product_line]
            # 제품 설명이 브랜드를 오버라이드하면 설명의 marketing_approach 사용
            if description_override and description_marketing_approach:
                final_marketing_approach = description_marketing_approach
            else:
                final_marketing_approach = description_marketing_approach or line_info.get('marketing_approach', 'consumer')

            return {
                'product_type': product_line,
                'marketing_approach': final_marketing_approach,
                'ideal_influencer': line_info.get('ideal_influencer', 'Both'),
                'expertise_keywords': line_info.get('expertise_keywords', []),
                'key_claims': line_info.get('key_claims', []),
                'requires_certification': line_info.get('requires_certification', False),
                'description': line_info.get('description', '')
            }

        # product_type으로 매칭 시도
        product_type = brand_data.get('product_type', '')
        for line_name, line_info in product_lines.items():
            if product_type and product_type in line_name:
                if description_override and description_marketing_approach:
                    final_marketing_approach = description_marketing_approach
                else:
                    final_marketing_approach = description_marketing_approach or line_info.get('marketing_approach', 'consumer')

                return {
                    'product_type': line_name,
                    'marketing_approach': final_marketing_approach,
                    'ideal_influencer': line_info.get('ideal_influencer', 'Both'),
                    'expertise_keywords': line_info.get('expertise_keywords', []),
                    'key_claims': line_info.get('key_claims', []),
                    'requires_certification': line_info.get('requires_certification', False),
                    'description': line_info.get('description', '')
                }

        # 브랜드 전체 전문성 수준으로 판단 (제품 설명 분석 결과 우선)
        if description_marketing_approach:
            # 제품 설명에서 분석된 marketing_approach 사용
            marketing_approach = description_marketing_approach
            if marketing_approach == 'professional':
                ideal_influencer = 'Expert'
            elif marketing_approach == 'consumer':
                ideal_influencer = 'Trendsetter'
            else:
                ideal_influencer = 'Both'
        else:
            # 브랜드 기본 전문성 수준으로 판단
            expertise_level = brand_data.get('expertise_level', 'low')
            if expertise_level == 'high':
                marketing_approach = 'expert_oriented'
                ideal_influencer = 'Expert'
            elif expertise_level == 'medium_high':
                marketing_approach = 'expert_oriented'
                ideal_influencer = 'Both'
            else:
                marketing_approach = 'consumer'
                ideal_influencer = 'Trendsetter'

        return {
            'product_type': product_type or '일반',
            'marketing_approach': marketing_approach,
            'ideal_influencer': ideal_influencer,
            'expertise_keywords': [],
            'key_claims': [],
            'requires_certification': False,
            'description': ''
        }

    def _get_preferred_type_v2(self, marketing_approach: str, ideal_influencer: str) -> str:
        """마케팅 접근법 기반 선호 인플루언서 타입"""
        if marketing_approach == 'professional':
            return 'Expert'
        elif marketing_approach == 'consumer':
            return 'Trendsetter'
        else:  # expert_oriented
            return ideal_influencer if ideal_influencer != 'Both' else 'Expert'

    def _evaluate_expertise(self, influencer: Dict, expertise_keywords: List[str]) -> float:
        """인플루언서의 전문성 점수 평가"""
        score = 0.5  # 기본 점수

        bio = influencer.get('bio', '').lower()
        posts = influencer.get('recent_posts', [])
        captions = ' '.join([p.get('caption', '') for p in posts]).lower()
        full_text = f"{bio} {captions}"

        # 1. 제품 전문성 키워드 매칭 (+0.2)
        if expertise_keywords:
            matched = sum(1 for kw in expertise_keywords if kw.lower() in full_text)
            score += min(0.2, matched * 0.05)

        # 2. 일반 전문가 키워드 (+0.15)
        expert_keywords = ['원장', '디렉터', '미용사', '컬러리스트', '자격증', '전문', '년차', '경력']
        expert_matched = sum(1 for kw in expert_keywords if kw in full_text)
        score += min(0.15, expert_matched * 0.03)

        # 3. 교육/시술 콘텐츠 (+0.1)
        edu_keywords = ['레슨', '교육', '시술', '과정', '테크닉', '노하우', '비법']
        edu_matched = sum(1 for kw in edu_keywords if kw in full_text)
        score += min(0.1, edu_matched * 0.03)

        # 4. 자격 관련 (+0.05)
        if '자격증' in bio or '라이센스' in bio or '면허' in bio:
            score += 0.05

        return min(1.0, score)

    def _calculate_match_score_v2(
        self,
        brand_vector: List[float],
        inf_vector: List[float],
        fis_score: float,
        classification: str,
        marketing_approach: str,
        influencer: Dict,
        brand_data: Dict,
        expertise_score: float,
        expertise_keywords: List[str]
    ) -> Dict:
        """
        적합도 계산 v3 - 시그모이드 스케일링 모델

        핵심 아이디어:
        1. 원점수(Raw Score) = 유사도, 고유특성, FIS의 가중 평균
        2. 제품 적합도(Fit Score) = 인플루언서 유형이 제품에 얼마나 맞는지 (0~1)
        3. 최종 점수 = sigmoid_scale(원점수, 적합도)

        시그모이드 스케일링:
        - 적합도가 높으면 → 점수 상한이 95%까지 확장
        - 적합도가 낮으면 → 점수 상한이 75%로 제한
        - 자연스러운 S-커브로 점수 분포

        수식: Final = min + (max - min) × sigmoid(raw_score)
              min/max는 fit_score에 따라 결정
        """
        breakdown = {}

        # ========== 1. 기본 지표 계산 ==========

        # 코사인 유사도 (브랜드-인플루언서 벡터 유사성)
        similarity = cosine_similarity(brand_vector, inf_vector)
        similarity_norm = (similarity + 1) / 2  # -1~1 → 0~1
        breakdown['similarity'] = round(similarity_norm, 3)

        # 고유 특성 점수 (인플루언서 개별 특성)
        unique_score = self._calculate_unique_score_v2(influencer, brand_data, classification, marketing_approach)
        breakdown['unique'] = round(unique_score, 3)

        # FIS 정규화 (40~100 → 0.4~1.0)
        fis_norm = fis_score / 100
        breakdown['fis'] = round(fis_norm, 3)

        # ========== 2. 원점수 계산 (가중 평균) ==========
        # 각 요소의 기여도: 유사도 20%, 고유특성 40%, FIS 40%
        raw_score = (similarity_norm * 0.2) + (unique_score * 0.4) + (fis_norm * 0.4)
        breakdown['raw_score'] = round(raw_score, 3)

        # ========== 3. 제품 적합도 계산 ==========
        fit_score = self._calculate_fit_score(
            classification, marketing_approach, influencer, expertise_score
        )
        breakdown['fit_score'] = round(fit_score, 3)
        breakdown['product_fit_detail'] = self._get_fit_description(
            classification, marketing_approach, fit_score
        )

        # ========== 4. 점수 스케일링 (차별화 강화) ==========
        # 적합도에 따른 점수 범위 결정
        # fit_score = 1.0 → 범위 [0.70, 0.95]
        # fit_score = 0.5 → 범위 [0.55, 0.80]
        # fit_score = 0.0 → 범위 [0.40, 0.65]

        score_min = 0.40 + (fit_score * 0.30)  # 0.40 ~ 0.70
        score_max = 0.65 + (fit_score * 0.30)  # 0.65 ~ 0.95

        # 선형 스케일링 - raw_score를 직접 반영
        # raw_score 범위: 대략 0.5~0.9
        raw_normalized = (raw_score - 0.5) / 0.4  # 0.5~0.9 → 0~1
        raw_normalized = max(0.0, min(1.0, raw_normalized))

        # 차별화 폭 확대: raw_score 차이가 최종 점수에 더 많이 반영되도록
        total_score = score_min + (score_max - score_min) * raw_normalized
        total_score = max(0.50, min(0.99, total_score))

        breakdown['score_range'] = f"{round(score_min*100)}%-{round(score_max*100)}%"

        return {
            'total_score': total_score,
            'breakdown': breakdown
        }

    def _calculate_fit_score(
        self,
        classification: str,
        marketing_approach: str,
        influencer: Dict,
        expertise_score: float
    ) -> float:
        """
        제품-인플루언서 적합도 계산 (0~1) - 차등 강화 버전

        점수 차등 기준:
        - Professional: Expert 0.9~1.0, Trendsetter 0.1~0.2 (큰 차이)
        - Expert Oriented: Expert 0.8~0.95, Trendsetter 0.25~0.4 (중간 차이)
        - Consumer: Trendsetter 0.85~1.0, Expert 0.5~0.65 (적당한 차이)
        """
        bio = influencer.get('bio', '')
        image_analysis = influencer.get('image_analysis', {})

        if marketing_approach == 'professional':
            # 전문가용: Expert 필수, Trendsetter는 매우 낮음
            if classification == 'Expert':
                base = 0.9
                # 보너스: 원장, 디렉터, 살롱 경력
                if '원장' in bio or '디렉터' in bio:
                    base += 0.05
                if '시술' in bio or '살롱' in bio:
                    base += 0.05
                return min(1.0, base)
            else:
                # Trendsetter는 전문가용 제품에 매우 부적합
                return 0.15

        elif marketing_approach == 'expert_oriented':
            # 전문성 지향: Expert 선호, Trendsetter는 낮음
            if classification == 'Expert':
                base = 0.85
                base += expertise_score * 0.1
                if '전문' in bio or '박사' in bio or '연구' in bio:
                    base += 0.05
                return min(1.0, base)
            else:
                # Trendsetter는 전문성 제품에 부적합
                prof_score = image_analysis.get('professionalism_score', 0.5)
                # 0.25 ~ 0.4 범위
                return 0.25 + (prof_score - 0.3) * 0.2

        else:  # consumer
            # 소비자용: Trendsetter 선호, Expert도 어느 정도 괜찮음
            if classification == 'Trendsetter':
                base = 0.85
                trend_score = image_analysis.get('trend_relevance_score', 0.5)
                base += (trend_score - 0.5) * 0.15  # 0.775 ~ 0.925
                # 라이프스타일 키워드 보너스
                if any(kw in bio for kw in ['데일리', '일상', '루틴', '꿀팁', '추천', '리뷰']):
                    base += 0.07
                return min(1.0, base)
            else:
                # Expert는 소비자용에 약간 부적합하지만 신뢰도 있음
                prof_score = image_analysis.get('professionalism_score', 0.5)
                # 0.5 ~ 0.65 범위
                return 0.5 + (prof_score - 0.3) * 0.2

    def _get_fit_description(self, classification: str, marketing_approach: str, fit_score: float) -> str:
        """적합도 설명 생성 - 자연스러운 문장으로 풀어서 설명"""
        if fit_score >= 0.85:
            # 최적 매칭
            descriptions = {
                ('Expert', 'professional'): '살롱 전문가로서 전문가용 제품을 시술하며 보여줄 수 있어 최고의 시너지가 기대됩니다.',
                ('Trendsetter', 'professional'): '전문가용 제품이지만, 영향력 있는 콘텐츠로 제품 인지도를 높일 수 있습니다.',
                ('Expert', 'expert_oriented'): '성분과 효능을 전문적으로 설명할 수 있어 제품의 가치를 잘 전달할 수 있습니다.',
                ('Trendsetter', 'expert_oriented'): '전문적인 내용을 친근하게 풀어내어 폭넓은 공감을 이끌어낼 수 있습니다.',
                ('Expert', 'consumer'): '전문가의 추천이라는 신뢰감으로 구매 결정에 긍정적인 영향을 줄 수 있습니다.',
                ('Trendsetter', 'consumer'): '일상에서 자연스럽게 제품을 활용하는 모습으로 공감대를 형성할 수 있습니다.'
            }
        elif fit_score >= 0.7:
            # 적합 매칭
            descriptions = {
                ('Expert', 'professional'): '전문가로서 살롱 제품을 효과적으로 소개할 수 있는 역량을 갖추고 있습니다.',
                ('Trendsetter', 'professional'): '전문가용 제품이라 다소 한계가 있지만, 제품의 매력을 감성적으로 전달할 수 있습니다.',
                ('Expert', 'expert_oriented'): '제품의 전문적인 효능을 설득력 있게 전달할 수 있습니다.',
                ('Trendsetter', 'expert_oriented'): '트렌디한 방식으로 제품의 효능을 알기 쉽게 소개할 수 있습니다.',
                ('Expert', 'consumer'): '전문가적 시각에서 제품의 장점을 분석하여 전달할 수 있습니다.',
                ('Trendsetter', 'consumer'): '라이프스타일 콘텐츠를 통해 제품의 일상적 활용법을 보여줄 수 있습니다.'
            }
        elif fit_score >= 0.5:
            # 보통 매칭
            descriptions = {
                ('Expert', 'professional'): '전문가 콘텐츠 제작이 가능하나, 더 강한 전문성이 필요할 수 있습니다.',
                ('Trendsetter', 'professional'): '전문가용 제품 특성상 시술 콘텐츠는 어렵지만, 제품 소개는 가능합니다.',
                ('Expert', 'expert_oriented'): '전문성 기반 콘텐츠 제작이 가능합니다.',
                ('Trendsetter', 'expert_oriented'): '전문적 내용을 다루기엔 한계가 있지만, 감성적 접근이 가능합니다.',
                ('Expert', 'consumer'): '전문가적 접근이 대중 제품과 다소 맞지 않을 수 있습니다.',
                ('Trendsetter', 'consumer'): '대중적인 콘텐츠 제작이 가능합니다.'
            }
        else:
            # 낮은 매칭
            descriptions = {
                ('Expert', 'professional'): '전문가이지만 해당 제품군과의 연관성이 낮을 수 있습니다.',
                ('Trendsetter', 'professional'): '전문가용 제품에는 Expert 인플루언서가 더 적합할 수 있습니다.',
                ('Expert', 'expert_oriented'): '전문성이 제품 카테고리와 일치하지 않을 수 있습니다.',
                ('Trendsetter', 'expert_oriented'): '제품의 전문적 특성을 전달하기 어려울 수 있습니다.',
                ('Expert', 'consumer'): '전문가적 접근이 대중 제품 홍보에 효과적이지 않을 수 있습니다.',
                ('Trendsetter', 'consumer'): '콘텐츠 스타일이 브랜드와 맞지 않을 수 있습니다.'
            }

        return descriptions.get((classification, marketing_approach), '브랜드 캠페인에 적합한 콘텐츠 제작이 가능합니다.')

    def _calculate_product_fit(
        self,
        classification: str,
        marketing_approach: str,
        expertise_score: float,
        influencer: Dict
    ) -> float:
        """제품-인플루언서 적합도 계산"""
        weights = self.approach_weights.get(marketing_approach, self.approach_weights['consumer'])
        type_weights = weights.get(classification, {'base': 0.5})

        # 기본 점수
        base_score = type_weights.get('base', 0.5)

        # 보너스 계산
        bonus = 0.0
        bio = influencer.get('bio', '')
        image_analysis = influencer.get('image_analysis', {})

        if marketing_approach == 'professional':
            # 전문가용: 자격증, 시술 콘텐츠 보너스
            if classification == 'Expert':
                if '원장' in bio or '디렉터' in bio:
                    bonus += type_weights.get('certification_bonus', 0.1)
                if '시술' in bio or '레슨' in bio:
                    bonus += type_weights.get('tutorial_bonus', 0.1)

        elif marketing_approach == 'expert_oriented':
            # 전문성 지향: 지식 전달 능력 보너스
            if classification == 'Expert':
                bonus += expertise_score * type_weights.get('knowledge_bonus', 0.1)
            else:
                # Trendsetter도 신뢰도가 높으면 보너스
                prof_score = image_analysis.get('professionalism_score', 0.5)
                if prof_score > 0.6:
                    bonus += type_weights.get('trust_bonus', 0.05)

        else:  # consumer
            # 일반 소비자용: 트렌드/라이프스타일 보너스
            if classification == 'Trendsetter':
                trend_score = image_analysis.get('trend_relevance_score', 0.5)
                bonus += (trend_score - 0.5) * type_weights.get('trend_bonus', 0.1) * 2
            else:
                # Expert도 신뢰도 보너스
                bonus += type_weights.get('credibility_bonus', 0.05)

        return min(1.0, base_score + bonus)

    def _get_product_fit_reason(self, classification: str, marketing_approach: str, match_bonus: float) -> str:
        """제품 적합도 이유 설명 - 보너스/페널티에 따른 메시지"""
        if match_bonus >= 0.10:
            # 높은 보너스 - 최적 매칭
            reasons = {
                ('Expert', 'professional'): '✅ 전문가용 제품에 최적화된 Expert',
                ('Expert', 'expert_oriented'): '✅ 전문성 지향 홍보에 최적인 Expert',
                ('Trendsetter', 'consumer'): '✅ 소비자용 제품에 최적화된 Trendsetter'
            }
        elif match_bonus >= 0.05:
            # 보너스 - 좋은 매칭
            reasons = {
                ('Expert', 'professional'): '전문가용 제품과 잘 맞는 Expert',
                ('Expert', 'expert_oriented'): '전문성 기반 홍보에 적합한 Expert',
                ('Trendsetter', 'consumer'): '소비자용 제품과 잘 맞는 Trendsetter'
            }
        elif match_bonus >= 0:
            # 중립 또는 약간의 보너스
            reasons = {
                ('Expert', 'professional'): '전문가용 제품 홍보 가능',
                ('Expert', 'expert_oriented'): '전문성 홍보에 기여 가능',
                ('Trendsetter', 'expert_oriented'): '성분 설명 콘텐츠 제작 가능',
                ('Trendsetter', 'consumer'): '소비자용 제품 홍보 가능',
                ('Expert', 'consumer'): '신뢰도 기반 제품 홍보 가능'
            }
        else:
            # 페널티 - 미스매칭
            reasons = {
                ('Trendsetter', 'professional'): '전문가용 제품은 Expert가 더 적합',
                ('Expert', 'consumer'): '트렌디한 콘텐츠는 Trendsetter가 유리',
                ('Trendsetter', 'expert_oriented'): '전문 설명에는 Expert가 더 적합'
            }
        return reasons.get((classification, marketing_approach), '제품 홍보 가능')

    def _get_role_weight(self, classification: str, marketing_approach: str) -> float:
        """
        역할 가중치 - 제품 유형과 인플루언서 분류 매칭도 (완화 버전)

        매칭이 잘 되면 1.0, 미스매칭이면 0.75~0.92
        전체적인 점수가 너무 낮아지지 않도록 페널티 완화
        """
        role_weights = {
            # professional 제품: Expert 필수
            ('Expert', 'professional'): 1.0,
            ('Trendsetter', 'professional'): 0.75,  # 페널티 완화 (0.6 → 0.75)

            # expert_oriented 제품: Expert 선호, Trendsetter도 가능
            ('Expert', 'expert_oriented'): 1.0,
            ('Trendsetter', 'expert_oriented'): 0.92,  # 페널티 완화 (0.85 → 0.92)

            # consumer 제품: Trendsetter 선호, Expert도 충분히 가능
            ('Expert', 'consumer'): 0.95,  # 페널티 완화 (0.85 → 0.95)
            ('Trendsetter', 'consumer'): 1.0
        }
        return role_weights.get((classification, marketing_approach), 0.9)

    def _get_preferred_type(self, product_type: str) -> str:
        """(레거시) 제품 유형에 따른 선호 인플루언서 타입"""
        professional_products = ['염색약', '펌제', '클리닉', '살롱전용', '두피케어', '탈색제']

        for prod in professional_products:
            if prod in product_type:
                return 'Expert'

        consumer_products = ['샴푸', '트리트먼트', '에센스', '오일', '스타일링']
        for prod in consumer_products:
            if prod in product_type:
                return 'Trendsetter'

        return 'Both'

    def _calculate_match_score(
        self,
        brand_vector: List[float],
        inf_vector: List[float],
        fis_score: float,
        classification: str,
        preferred_type: str,
        influencer: Dict = None,
        brand_data: Dict = None
    ) -> float:
        """매칭 점수 계산 - 인플루언서 고유 특성 반영"""
        # 1. 기본 코사인 유사도 (40% 가중치)
        similarity = cosine_similarity(brand_vector, inf_vector)
        similarity_norm = (similarity + 1) / 2
        base_score = similarity_norm * 0.4

        # 2. FIS 점수 (20% 가중치)
        fis_norm = max(0.0, min(1.0, fis_score / 100))
        fis_component = fis_norm * 0.2

        # 3. 역할 적합도 (15% 가중치)
        if preferred_type == 'Both':
            role_score = 0.8
        elif preferred_type == classification:
            role_score = 1.0
        else:
            role_score = 0.5
        role_component = role_score * 0.15

        # 4. 인플루언서 고유 특성 점수 (25% 가중치)
        unique_score = self._calculate_unique_score(influencer, brand_data, classification)
        unique_component = unique_score * 0.25

        # 최종 점수
        raw_score = base_score + fis_component + role_component + unique_component
        return max(0.0, min(1.0, raw_score))

    def _calculate_unique_score(self, influencer: Dict, brand_data: Dict, classification: str) -> float:
        """인플루언서 고유 특성 기반 점수 계산"""
        if not influencer:
            return 0.5

        score = 0.5  # 기본 점수
        bio = influencer.get('bio', '')
        image_analysis = influencer.get('image_analysis', {})
        posts = influencer.get('recent_posts', [])
        followers = influencer.get('followers', 0)

        product_type = brand_data.get('product_type', '') if brand_data else ''
        brand_style = brand_data.get('aesthetic_style', '') if brand_data else ''
        campaign_desc = brand_data.get('campaign_description', '') if brand_data else ''

        # 1. Bio와 제품 연관성 (+0.15)
        product_keywords = {
            '염색': ['염색', '컬러', '컬러리스트'],
            '펌': ['펌', '웨이브', '컬'],
            '샴푸': ['케어', '샴푸', '세정'],
            '두피': ['두피', '탈모', '스캘프'],
            '트리트먼트': ['트리트먼트', '손상모', '케어'],
            '살롱': ['살롱', '원장', '미용실', '헤어샵']
        }
        for prod_key, keywords in product_keywords.items():
            if prod_key in product_type:
                if any(kw in bio for kw in keywords):
                    score += 0.15
                    break

        # 2. 이미지 스타일과 브랜드 스타일 매칭 (+0.1)
        dominant_style = image_analysis.get('dominant_style', '')
        style_match_map = {
            'Luxury': ['luxury', 'minimal', 'elegant'],
            'Natural': ['natural', 'organic', 'clean'],
            'Trendy': ['trendy', 'modern', 'hip'],
            'Colorful': ['colorful', 'vibrant', 'pop']
        }
        if brand_style in style_match_map:
            if dominant_style in style_match_map[brand_style]:
                score += 0.1

        # 3. 트렌드 적합도 (Trendsetter인 경우) (+0.1)
        if classification == 'Trendsetter':
            trend_score = image_analysis.get('trend_relevance_score', 0.5)
            score += (trend_score - 0.5) * 0.2  # -0.1 ~ +0.1

        # 4. 전문성 점수 (Expert인 경우) (+0.1)
        if classification == 'Expert':
            prof_score = image_analysis.get('professionalism_score', 0.5)
            score += (prof_score - 0.5) * 0.2  # -0.1 ~ +0.1
            # Bio에서 전문가 키워드
            expert_keywords = ['원장', '디렉터', '년차', '전문', '자격증', '의사', '박사']
            expert_count = sum(1 for kw in expert_keywords if kw in bio)
            score += min(0.1, expert_count * 0.03)

        # 5. 참여율 기반 점수 (+0.05)
        if posts:
            total_engagement = sum(p.get('likes', 0) + p.get('comments', 0) for p in posts)
            avg_engagement = total_engagement / len(posts) if posts else 0
            if followers > 0:
                engagement_rate = avg_engagement / followers
                if engagement_rate > 0.05:  # 5% 이상
                    score += 0.05
                elif engagement_rate > 0.03:  # 3% 이상
                    score += 0.03

        # 6. 캠페인 키워드 매칭 (+0.1)
        if campaign_desc:
            campaign_lower = campaign_desc.lower()
            vibe = image_analysis.get('vibe', '').lower()
            aesthetic_tags = [t.lower() for t in image_analysis.get('aesthetic_tags', [])]

            # 캠페인 키워드와 인플루언서 특성 매칭
            campaign_keywords = ['프리미엄', '럭셔리', '자연', '트렌디', 'mz', '젊은', '전문가', '살롱']
            matched = 0
            for kw in campaign_keywords:
                if kw in campaign_lower:
                    if kw in vibe or any(kw in tag for tag in aesthetic_tags) or kw in bio.lower():
                        matched += 1
            score += min(0.1, matched * 0.03)

        return max(0.0, min(1.0, score))

    def _calculate_unique_score_v2(
        self, influencer: Dict, brand_data: Dict, classification: str, marketing_approach: str
    ) -> float:
        """
        인플루언서 고유 특성 기반 점수 계산 v2 - 차별화 강화

        점수 범위: 0.3 ~ 1.0 (더 넓은 분포)
        """
        if not influencer:
            return 0.3

        score = 0.3  # 기본 점수 낮춤 (차별화 폭 확대)
        bio = influencer.get('bio', '')
        image_analysis = influencer.get('image_analysis', {})
        posts = influencer.get('recent_posts', [])
        followers = influencer.get('followers', 0)
        username = influencer.get('username', '')

        product_type = brand_data.get('product_type', '') if brand_data else ''
        brand_style = brand_data.get('aesthetic_style', '') if brand_data else ''
        campaign_desc = brand_data.get('campaign_description', '') if brand_data else ''

        # 1. Bio와 제품 연관성 (+0.25) - 가중치 증가
        product_keywords = {
            '염색': ['염색', '컬러', '컬러리스트', '헤어컬러', '블리치'],
            '펌': ['펌', '웨이브', '컬', '볼륨', '스타일링'],
            '샴푸': ['케어', '샴푸', '세정', '클렌징', '모발'],
            '두피': ['두피', '탈모', '스캘프', '모근', '두피케어'],
            '트리트먼트': ['트리트먼트', '손상모', '케어', '영양', '복구'],
            '살롱': ['살롱', '원장', '미용실', '헤어샵', '헤어디자이너'],
            '에센스': ['에센스', '세럼', '오일', '윤기', '광채'],
            '스타일링': ['스타일링', '왁스', '스프레이', '무스', '젤']
        }

        bio_match_score = 0
        for prod_key, keywords in product_keywords.items():
            if prod_key in product_type.lower():
                matched_count = sum(1 for kw in keywords if kw in bio.lower())
                bio_match_score = min(0.25, matched_count * 0.08)
                break
        score += bio_match_score

        # 2. 이미지 스타일과 브랜드 스타일 매칭 (+0.2)
        dominant_style = image_analysis.get('dominant_style', '')
        style_match_map = {
            'Luxury': ['luxury', 'minimal', 'elegant', 'premium'],
            'Natural': ['natural', 'organic', 'clean', 'minimal'],
            'Trendy': ['trendy', 'modern', 'hip', 'edgy'],
            'Colorful': ['colorful', 'vibrant', 'pop', 'bold'],
            'Classic': ['classic', 'elegant', 'traditional'],
            'Minimal': ['minimal', 'clean', 'simple']
        }
        if brand_style in style_match_map:
            if dominant_style in style_match_map[brand_style]:
                score += 0.2
            elif dominant_style:  # 스타일이 있지만 매칭 안됨
                score += 0.05

        # 3. 분류별 특화 점수 (+0.2)
        if classification == 'Trendsetter':
            # 트렌드 점수 (완화)
            trend_score = image_analysis.get('trend_relevance_score', 0.5)
            score += (trend_score - 0.4) * 0.3  # 0.03 ~ 0.18

            # 팔로워 기반 영향력 (완화)
            if followers >= 100000:
                score += 0.05
            elif followers >= 50000:
                score += 0.03
            elif followers >= 10000:
                score += 0.01

        elif classification == 'Expert':
            # 전문성 점수 (완화)
            prof_score = image_analysis.get('professionalism_score', 0.5)
            score += (prof_score - 0.4) * 0.3  # 0.03 ~ 0.18

            # Bio에서 전문가 키워드
            expert_keywords = ['원장', '디렉터', '년차', '전문', '자격증', '미용사', '컬러리스트']
            expert_count = sum(1 for kw in expert_keywords if kw in bio)
            score += min(0.10, expert_count * 0.03)

        # 4. 참여율 기반 점수 (+0.15) - 가중치 증가
        if posts:
            total_engagement = sum(p.get('likes', 0) + p.get('comments', 0) for p in posts)
            avg_engagement = total_engagement / len(posts) if posts else 0
            if followers > 0:
                engagement_rate = avg_engagement / followers
                if engagement_rate > 0.08:  # 8% 이상 (매우 높음)
                    score += 0.15
                elif engagement_rate > 0.05:  # 5% 이상
                    score += 0.10
                elif engagement_rate > 0.03:  # 3% 이상
                    score += 0.05
                elif engagement_rate > 0.01:  # 1% 이상
                    score += 0.02

        # 5. 마케팅 접근법별 추가 보너스 (+0.1)
        if marketing_approach == 'professional':
            # 전문가용: 시술/교육 키워드
            if any(kw in bio for kw in ['시술', '레슨', '교육', '클래스', '세미나']):
                score += 0.1
        elif marketing_approach == 'expert_oriented':
            # 전문성 지향: 성분/효능 키워드
            if any(kw in bio for kw in ['성분', '효과', '효능', '과학', '연구']):
                score += 0.1
        else:  # consumer
            # 일반 소비자용: 라이프스타일 키워드
            if any(kw in bio for kw in ['데일리', '일상', 'GRWM', '루틴', '꿀팁', '추천']):
                score += 0.1

        # 6. 콘텐츠 vibe 매칭 (+0.05)
        vibe = image_analysis.get('vibe', '').lower()
        if vibe:
            if any(word in vibe for word in ['전문', 'professional', 'expert']) and classification == 'Expert':
                score += 0.05
            elif any(word in vibe for word in ['트렌디', 'trendy', '감성', '스타일']) and classification == 'Trendsetter':
                score += 0.05

        # 7. 브랜드 고유 특성 매칭 (+0.15) - 브랜드별 차별화 핵심
        brand_identity_score = self._calculate_brand_identity_match(
            influencer, brand_data, image_analysis
        )
        score += brand_identity_score

        # 8. 인플루언서별 개인 특성 변동 (+/-0.05)
        # 같은 조건이라도 개인별로 미세하게 다른 점수가 나오도록
        personal_seed = hash(username) % 1000 / 10000  # 0 ~ 0.1
        follower_factor = (followers % 10000) / 100000  # 0 ~ 0.1
        personal_variation = (personal_seed + follower_factor - 0.1) * 0.5  # -0.05 ~ +0.05
        score += personal_variation

        return max(0.0, min(1.0, score))

    def _calculate_brand_identity_match(
        self, influencer: Dict, brand_data: Dict, image_analysis: Dict
    ) -> float:
        """
        브랜드 고유 정체성과 인플루언서 매칭 점수 계산

        같은 aesthetic_style이라도 브랜드마다 다른 철학과 가치를 가짐:
        - 려: 한방, 전통, 아시아 유산 → '한방', '전통', '자연'을 다루는 인플루언서
        - 라보에이치: 피부과학, 더마 → '과학', '임상', '더마'를 언급하는 인플루언서
        - 롱테이크: 감성, 라이프스타일, 향기 → '감성', '무드', '향'을 다루는 인플루언서

        Returns:
            0.0 ~ 0.15 범위의 브랜드 정체성 매칭 점수
        """
        if not brand_data:
            return 0.0

        bio = influencer.get('bio', '').lower()
        posts = influencer.get('recent_posts', [])
        captions = ' '.join([p.get('caption', '') for p in posts]).lower()
        vibe = image_analysis.get('vibe', '').lower()
        aesthetic_tags = [t.lower() for t in image_analysis.get('aesthetic_tags', [])]

        # 인플루언서의 전체 텍스트
        inf_text = f"{bio} {captions} {vibe} {' '.join(aesthetic_tags)}"

        # 브랜드 고유 키워드 추출
        brand_name = brand_data.get('brand_name', '')
        core_values = brand_data.get('core_values', [])
        target_keywords = brand_data.get('target_keywords', [])
        brand_philosophy = brand_data.get('brand_philosophy', '')
        expertise_focus = brand_data.get('expertise_focus', '')

        # 브랜드별 고유 특성 키워드 매핑
        brand_specific_keywords = self._get_brand_specific_keywords(brand_name)

        match_score = 0.0

        # 1. 브랜드 고유 키워드 매칭 (+0.08)
        if brand_specific_keywords:
            matched = sum(1 for kw in brand_specific_keywords if kw.lower() in inf_text)
            match_score += min(0.08, matched * 0.02)

        # 2. core_values 매칭 (+0.04)
        core_value_match = sum(1 for cv in core_values if cv.lower() in inf_text)
        match_score += min(0.04, core_value_match * 0.01)

        # 3. expertise_focus 키워드 매칭 (+0.03)
        if expertise_focus:
            focus_words = expertise_focus.lower().split()
            focus_match = sum(1 for word in focus_words if len(word) > 2 and word in inf_text)
            match_score += min(0.03, focus_match * 0.01)

        # 4. 브랜드 배타적 적합성 (+0.1 ~ -0.05)
        # 경쟁 브랜드 대비 현재 브랜드에 더 적합한 인플루언서에게 보너스
        exclusivity_score = self._calculate_brand_exclusivity_score(
            influencer, brand_name, image_analysis
        )
        match_score += exclusivity_score

        return match_score

    def _get_brand_specific_keywords(self, brand_name: str) -> List[str]:
        """
        브랜드별 고유 특성 키워드 반환

        같은 스타일이라도 브랜드마다 추구하는 방향이 다름
        핵심 차별화 키워드를 앞에 배치 (가중치 높음)
        """
        brand_keywords = {
            '려': [
                # 핵심 차별화: 한방/전통
                '한방', '인삼', '한약', '생약', '전통', '동양의학', '자양', '청아', '흑운',
                '모근', '뿌리', '근본', '아시아', '유산', '진생', '영양'
            ],
            '미쟝센': [
                # 핵심 차별화: 트렌드/스타일/셀프
                '트렌드', 'MZ', 'Z세대', '힙', '스타일', '패션', '개성', '표현', '대담',
                '셀프', 'GRWM', '룩', '헬로버블', '컬러', '염색', '스타일링'
            ],
            '라보에이치': [
                # 핵심 차별화: 피부과학/더마/임상
                '피부과', '더마', '더마톨로지', '피부과학', '임상', '과학적',
                '피부장벽', '스킨케어', '민감성', '성분', '피지', '스캘프'
            ],
            '아윤채': [
                # 핵심 차별화: 살롱/디자이너/본질
                '디자이너', '본질', '살롱케어', '테이크홈', '홈케어',
                '프로', '프로페셔널', '미용사', '원장', '시술', '클리닉'
            ],
            '아모스 프로페셔널': [
                # 핵심 차별화: 테크닉/노하우/신뢰
                '테크닉', '노하우', '신뢰', '검증', '커리큘럼', '그린티',
                '살롱', '프로', '전문가', '스타일리스트', '디자이너'
            ],
            '롱테이크': [
                # 핵심 차별화: 향/감성/라이프스타일
                '향기', '퍼퓸', '향', '우디', '숲', '자연향', '디퓨저',
                '감성', '무드', '힐링', '라이프스타일', '공간', '편안', '휴식'
            ]
        }
        return brand_keywords.get(brand_name, [])

    def _calculate_brand_exclusivity_score(
        self, influencer: Dict, brand_name: str, image_analysis: Dict
    ) -> float:
        """
        브랜드 배타적 적합성 점수 - 다른 브랜드보다 이 브랜드에 더 맞는지

        다른 경쟁 브랜드와의 적합성 대비 현재 브랜드와의 적합성을 계산하여
        같은 카테고리 내에서도 브랜드별로 다른 인플루언서가 추천되도록 함
        """
        bio = influencer.get('bio', '').lower()
        posts = influencer.get('recent_posts', [])
        captions = ' '.join([p.get('caption', '') for p in posts]).lower()
        vibe = image_analysis.get('vibe', '').lower()
        inf_text = f"{bio} {captions} {vibe}"

        # 현재 브랜드와의 매칭 점수
        current_keywords = self._get_brand_specific_keywords(brand_name)
        current_match = sum(1 for kw in current_keywords[:8] if kw.lower() in inf_text)  # 핵심 키워드 우선

        # 경쟁 브랜드와의 매칭 점수 (같은 스타일의 다른 브랜드들)
        competitor_brands = {
            '려': ['라보에이치'],  # 같은 Natural 스타일
            '라보에이치': ['려'],
            '미쟝센': ['롱테이크'],
            '롱테이크': ['미쟝센'],
            '아윤채': ['아모스 프로페셔널'],
            '아모스 프로페셔널': ['아윤채']
        }

        competitors = competitor_brands.get(brand_name, [])
        competitor_scores = []
        for comp in competitors:
            comp_keywords = self._get_brand_specific_keywords(comp)
            comp_match = sum(1 for kw in comp_keywords[:8] if kw.lower() in inf_text)
            competitor_scores.append(comp_match)

        # 경쟁 브랜드 대비 현재 브랜드가 더 잘 맞으면 보너스
        if competitors and competitor_scores:
            avg_competitor = sum(competitor_scores) / len(competitor_scores)
            diff = current_match - avg_competitor

            if diff > 0:
                # 현재 브랜드에 더 적합: 보너스
                return min(0.15, diff * 0.04)
            elif diff < 0:
                # 경쟁 브랜드에 더 적합: 페널티 (더 강화)
                return max(-0.1, diff * 0.03)

        # 키워드 매칭이 없는 경우에도 브랜드별 차별화
        # 같은 Expert라도 브랜드에 따라 약간씩 다른 점수
        brand_seed = hash(brand_name) % 100 / 1000  # 브랜드별 미세 변동 (0~0.1)
        inf_seed = hash(influencer.get('username', '')) % 100 / 1000
        return (brand_seed + inf_seed) * 0.05 - 0.025  # -0.025 ~ +0.025

    def _select_diverse(
        self,
        results: List[Dict],
        top_k: int,
        preferred_type: str,
        expert_count: int = None,
        trendsetter_count: int = None
    ) -> List[Dict]:
        """다양성 보장하며 선택"""
        experts = sorted(
            [r for r in results if r['classification'] == 'Expert'],
            key=lambda x: x['match_score'], reverse=True
        )
        trendsetters = sorted(
            [r for r in results if r['classification'] == 'Trendsetter'],
            key=lambda x: x['match_score'], reverse=True
        )

        # 수 결정
        if expert_count is not None and trendsetter_count is not None:
            exp_count = min(len(experts), expert_count)
            trend_count = min(len(trendsetters), trendsetter_count)
        elif preferred_type == 'Expert':
            exp_count = min(len(experts), max(1, int(top_k * 0.6)))
            trend_count = min(len(trendsetters), top_k - exp_count)
        elif preferred_type == 'Trendsetter':
            trend_count = min(len(trendsetters), max(1, int(top_k * 0.6)))
            exp_count = min(len(experts), top_k - trend_count)
        else:
            exp_count = min(len(experts), max(1, top_k // 2))
            trend_count = min(len(trendsetters), top_k - exp_count)

        # 부족한 경우 다른 그룹에서 채우기
        if exp_count + trend_count < top_k:
            remaining = top_k - exp_count - trend_count
            if len(experts) > exp_count:
                extra = min(len(experts) - exp_count, remaining)
                exp_count += extra
                remaining -= extra
            if remaining > 0 and len(trendsetters) > trend_count:
                trend_count += min(len(trendsetters) - trend_count, remaining)

        # 선택 및 정렬
        selected = experts[:exp_count] + trendsetters[:trend_count]
        selected.sort(key=lambda x: x['match_score'], reverse=True)

        return selected[:top_k]

    def _generate_reason_v2(self, brand_data: Dict, result: Dict, product_info: Dict) -> str:
        """추천 사유 생성 v2 - LLM 활용 자연스러운 문장 생성"""
        username = result['username']
        classification = result['classification']
        match_percent = int(result['match_score'] * 100)
        followers = result['followers']
        bio = result.get('bio', '')
        image_analysis = result.get('image_analysis', {})
        score_breakdown = result.get('score_breakdown', {})
        marketing_approach = result.get('marketing_approach', 'consumer')

        brand_name = brand_data.get('brand_name', '브랜드')
        product_type = product_info.get('product_type', brand_data.get('product_type', ''))
        aesthetic_style = brand_data.get('aesthetic_style', 'Trendy')
        expertise_level = brand_data.get('expertise_level', 'low')
        slogan = brand_data.get('slogan', '')
        core_values = brand_data.get('core_values', [])
        campaign_description = brand_data.get('campaign_description', '')

        # LLM 사용 가능하면 LLM으로 생성
        if OPENAI_AVAILABLE and self.api_key:
            llm_reason = self._generate_reason_with_llm(
                brand_name=brand_name,
                brand_style=aesthetic_style,
                expertise_level=expertise_level,
                slogan=slogan,
                core_values=core_values,
                product_type=product_type,
                marketing_approach=marketing_approach,
                campaign_description=campaign_description,
                username=username,
                classification=classification,
                followers=followers,
                bio=bio,
                vibe=image_analysis.get('vibe', ''),
                fit_score=match_percent
            )
            if llm_reason:
                return llm_reason

        # 폴백: 기존 템플릿 기반 생성
        intro = self._build_influencer_intro(username, classification, followers, bio)
        reason = self._build_natural_reason(
            classification, marketing_approach, aesthetic_style,
            image_analysis, bio, brand_name, product_type, score_breakdown
        )

        return f"{intro}\n\n{reason}"

    def _generate_reason_with_llm(
        self,
        brand_name: str,
        brand_style: str,
        expertise_level: str,
        slogan: str,
        core_values: List[str],
        product_type: str,
        marketing_approach: str,
        campaign_description: str,
        username: str,
        classification: str,
        followers: int,
        bio: str,
        vibe: str,
        fit_score: int
    ) -> Optional[str]:
        """LLM을 활용한 추천 이유 생성"""
        try:
            client = openai.OpenAI(api_key=self.api_key)

            # 브랜드와 제품의 관계 컨텍스트 생성
            brand_product_context = self._build_brand_product_context(
                brand_style, expertise_level, marketing_approach, campaign_description
            )

            # 팔로워 포맷팅
            if followers >= 10000:
                followers_text = f"{followers/10000:.1f}만"
            else:
                followers_text = f"{followers:,}"

            # 마케팅 접근법 한글 변환
            approach_korean = {
                'professional': '살롱 전문가용',
                'expert_oriented': '전문성 강조',
                'consumer': '일반 소비자용'
            }

            prompt = REASON_GENERATION_PROMPT.format(
                brand_name=brand_name,
                brand_style=brand_style,
                expertise_level=expertise_level,
                slogan=slogan or '없음',
                core_values=', '.join(core_values) if core_values else '없음',
                product_type=product_type or '일반 제품',
                marketing_approach=approach_korean.get(marketing_approach, marketing_approach),
                campaign_description=campaign_description or '없음',
                brand_product_context=brand_product_context,
                username=username,
                classification=classification,
                followers=followers_text,
                bio=bio or '정보 없음',
                vibe=vibe or '정보 없음',
                fit_score=fit_score
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 인플루언서 마케팅 전문가입니다. 자연스럽고 설득력 있는 한국어로 추천 이유를 작성합니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"LLM 추천 이유 생성 오류: {e}")
            return None

    def _build_brand_product_context(
        self,
        brand_style: str,
        expertise_level: str,
        marketing_approach: str,
        campaign_description: str
    ) -> str:
        """브랜드와 제품의 관계 컨텍스트 문장 생성"""
        contexts = []

        # 브랜드 전문성과 제품 마케팅 접근법 비교
        expertise_to_approach = {
            'high': 'professional',
            'medium_high': 'expert_oriented',
            'medium': 'consumer',
            'low': 'consumer'
        }

        expected_approach = expertise_to_approach.get(expertise_level, 'consumer')

        if expected_approach != marketing_approach:
            # 브랜드와 제품의 특성이 다른 경우
            if expertise_level in ['high', 'medium_high'] and marketing_approach == 'consumer':
                contexts.append(
                    f"브랜드는 전문적인 이미지를 가지고 있지만, 이번 제품/캠페인은 대중적인 소비자를 타겟으로 합니다. "
                    f"따라서 전문성과 대중성을 모두 아우를 수 있는 인플루언서가 필요합니다."
                )
            elif expertise_level in ['low', 'medium'] and marketing_approach == 'professional':
                contexts.append(
                    f"브랜드는 대중적인 이미지가 강하지만, 이번 제품은 전문가용 라인입니다. "
                    f"전문성을 보여주면서도 브랜드의 친근한 이미지를 유지할 수 있는 인플루언서가 적합합니다."
                )
            elif expertise_level in ['low', 'medium'] and marketing_approach == 'expert_oriented':
                contexts.append(
                    f"브랜드는 일반 소비자 친화적이지만, 이번 캠페인은 전문적인 효능을 강조합니다. "
                    f"신뢰감을 주면서도 친근하게 설명할 수 있는 인플루언서가 필요합니다."
                )
        else:
            # 브랜드와 제품의 특성이 일치하는 경우
            if marketing_approach == 'professional':
                contexts.append("브랜드와 제품 모두 전문가용으로 일관된 이미지를 가지고 있습니다.")
            elif marketing_approach == 'expert_oriented':
                contexts.append("브랜드와 제품 모두 전문성을 강조하는 방향으로 일치합니다.")
            else:
                contexts.append("브랜드와 제품 모두 대중적인 소비자를 타겟으로 합니다.")

        # 캠페인 설명이 있으면 추가 컨텍스트
        if campaign_description:
            # 캠페인 설명에서 특별한 방향성 감지
            desc_lower = campaign_description.lower()
            if '젊은' in campaign_description or 'mz' in desc_lower or '트렌디' in campaign_description:
                if brand_style not in ['Trendy', 'Colorful']:
                    contexts.append("캠페인이 젊은 층을 타겟으로 하여 브랜드의 기존 이미지와 다른 접근이 필요합니다.")
            elif '프리미엄' in campaign_description or '고급' in campaign_description:
                if brand_style not in ['Luxury', 'Classic']:
                    contexts.append("캠페인이 프리미엄 이미지를 추구하여 브랜드의 기존 이미지를 한 단계 높이려 합니다.")

        return ' '.join(contexts) if contexts else "브랜드와 제품의 방향성이 일치합니다."

    def _build_influencer_intro(self, username: str, classification: str, followers: int, bio: str) -> str:
        """인플루언서 소개 문장 생성 (간결하고 자연스럽게)"""
        # 팔로워 규모
        if followers >= 100000:
            follower_text = f"{followers/10000:.1f}만"
        elif followers >= 10000:
            follower_text = f"{followers/10000:.1f}만"
        else:
            follower_text = f"{followers:,}"

        # 역할 설명
        if classification == 'Expert':
            role = "헤어 전문가"
            # bio에서 구체적 직함 추출
            if '원장' in bio:
                role = "살롱 원장"
            elif '디렉터' in bio:
                role = "헤어 디렉터"
            elif '스타일리스트' in bio:
                role = "헤어 스타일리스트"
            elif '피부과' in bio or '의사' in bio:
                role = "피부과 전문의"
        else:
            role = "뷰티 크리에이터"
            if '크리에이터' in bio:
                role = "뷰티 크리에이터"
            elif '블로거' in bio:
                role = "뷰티 블로거"
            elif '에디터' in bio:
                role = "뷰티 에디터"

        return f"@{username}은 팔로워 {follower_text}명을 보유한 {role}입니다."

    def _build_natural_reason(
        self, classification: str, marketing_approach: str, aesthetic_style: str,
        image_analysis: Dict, bio: str, brand_name: str, product_type: str, score_breakdown: Dict
    ) -> str:
        """자연스러운 추천 이유 문장 생성"""
        sentences = []

        vibe = image_analysis.get('vibe', '')
        dominant_style = image_analysis.get('dominant_style', '')
        fit_score = score_breakdown.get('fit_score', 0.7)

        # 1. 핵심 추천 이유 (왜 이 인플루언서인가)
        core_reason = self._get_core_reason(classification, marketing_approach, bio, fit_score)
        sentences.append(core_reason)

        # 2. 콘텐츠 스타일 매칭 (있는 경우)
        style_match = self._get_style_match_sentence(vibe, dominant_style, aesthetic_style, brand_name)
        if style_match:
            sentences.append(style_match)

        # 3. 기대 효과
        effect = self._get_expected_effect(classification, marketing_approach, product_type)
        sentences.append(effect)

        return " ".join(sentences)

    def _get_core_reason(self, classification: str, marketing_approach: str, bio: str, fit_score: float) -> str:
        """핵심 추천 이유 생성"""
        if classification == 'Expert':
            if marketing_approach == 'professional':
                if '원장' in bio:
                    return "살롱 운영 경험을 바탕으로 전문가용 제품의 시술 과정을 생생하게 보여줄 수 있습니다."
                elif '디렉터' in bio:
                    return "헤어 디렉터로서의 전문성을 살려 제품의 효과를 설득력 있게 전달할 수 있습니다."
                else:
                    return "전문가 자격과 경험을 갖추고 있어 살롱 전용 제품 홍보에 적합합니다."
            elif marketing_approach == 'expert_oriented':
                if '피부과' in bio or '의사' in bio:
                    return "의료 전문가로서 성분과 효능에 대한 신뢰도 높은 설명이 가능합니다."
                else:
                    return "전문적인 지식을 바탕으로 제품의 효능을 깊이 있게 설명할 수 있습니다."
            else:  # consumer
                return "전문가의 추천이라는 신뢰감으로 소비자들의 구매 결정을 도울 수 있습니다."
        else:  # Trendsetter
            if marketing_approach == 'consumer':
                if '크리에이터' in bio:
                    return "트렌디한 콘텐츠 제작 능력으로 MZ세대의 관심을 끌 수 있습니다."
                elif '일상' in bio or '라이프' in bio:
                    return "자연스러운 일상 콘텐츠 속에서 제품을 효과적으로 노출할 수 있습니다."
                else:
                    return "감각적인 콘텐츠로 제품의 매력을 젊은 소비자에게 전달할 수 있습니다."
            elif marketing_approach == 'expert_oriented':
                return "친근한 설명으로 전문적인 제품 정보를 대중에게 쉽게 전달할 수 있습니다."
            else:  # professional
                return "넓은 팔로워층을 통해 전문가용 제품의 인지도를 높이는 데 기여할 수 있습니다."

    def _get_style_match_sentence(self, vibe: str, dominant_style: str, aesthetic_style: str, brand_name: str) -> str:
        """스타일 매칭 문장 생성"""
        if not vibe and not dominant_style:
            return ""

        # vibe 기반 매칭
        if vibe:
            vibe_lower = vibe.lower()
            if aesthetic_style == 'Luxury' and any(w in vibe_lower for w in ['고급', '럭셔리', '세련', '프리미엄']):
                return f"고급스러운 피드 분위기가 {brand_name}의 프리미엄 이미지와 잘 어울립니다."
            elif aesthetic_style == 'Natural' and any(w in vibe_lower for w in ['자연', '내추럴', '편안', '건강']):
                return f"자연스럽고 건강한 이미지가 {brand_name}의 브랜드 철학과 일치합니다."
            elif aesthetic_style == 'Trendy' and any(w in vibe_lower for w in ['트렌디', '힙', '스타일', '감각']):
                return f"트렌디한 감성이 {brand_name}의 젊은 브랜드 이미지와 시너지를 냅니다."
            elif vibe:
                return f"'{vibe}' 분위기의 콘텐츠가 브랜드와 조화롭습니다."

        # dominant_style 기반 매칭
        if dominant_style:
            style_map = {
                'luxury': '세련되고 고급스러운',
                'natural': '자연스럽고 편안한',
                'trendy': '트렌디하고 감각적인',
                'minimal': '깔끔하고 세련된',
                'colorful': '화려하고 개성있는'
            }
            style_desc = style_map.get(dominant_style.lower(), '')
            if style_desc:
                return f"{style_desc} 피드 스타일이 브랜드 이미지와 어울립니다."

        return ""

    def _get_expected_effect(self, classification: str, marketing_approach: str, product_type: str) -> str:
        """기대 효과 문장 생성"""
        if classification == 'Expert':
            if marketing_approach == 'professional':
                return "시술 영상과 비포/애프터 콘텐츠로 제품의 전문성을 입증할 수 있을 것으로 기대됩니다."
            elif marketing_approach == 'expert_oriented':
                return "성분 분석과 효능 리뷰로 제품에 대한 신뢰도를 높일 수 있을 것으로 보입니다."
            else:
                return "전문가의 객관적인 평가로 제품의 신뢰도를 높일 수 있습니다."
        else:
            if marketing_approach == 'consumer':
                return "GRWM, 루틴 영상 등 일상 콘텐츠로 자연스러운 바이럴이 기대됩니다."
            elif marketing_approach == 'expert_oriented':
                return "친근한 방식으로 제품 정보를 전달해 폭넓은 관심을 유도할 수 있습니다."
            else:
                return "영향력 있는 콘텐츠로 제품 인지도 확산에 기여할 수 있습니다."

    def _generate_reason(self, brand_data: Dict, result: Dict) -> str:
        """(레거시) 추천 사유 생성"""
        username = result['username']
        classification = result['classification']
        match_percent = int(result['match_score'] * 100)
        followers = result['followers']
        bio = result.get('bio', '')
        image_analysis = result.get('image_analysis', {})

        brand_name = brand_data.get('brand_name', '브랜드')
        product_type = brand_data.get('product_type', '')
        aesthetic_style = brand_data.get('aesthetic_style', 'Trendy')
        slogan = brand_data.get('slogan', '')
        core_values = brand_data.get('core_values', [])
        target_audience = brand_data.get('target_audience', '')
        campaign_description = brand_data.get('campaign_description', '')

        # 인플루언서 특성 설명
        inf_desc = self._get_influencer_description(username, bio, image_analysis, classification, followers)

        # 매칭 이유 설명 (제품 설명 포함)
        match_reason = self._get_match_reason(
            classification, aesthetic_style, product_type, target_audience, image_analysis, campaign_description, bio
        )

        return f"【인플루언서 특성】 {inf_desc}\n\n【추천 이유】 {match_reason} 종합 적합도 {match_percent}%로 평가됩니다."

    def _get_brand_description(self, brand_name: str, style: str, slogan: str, core_values: list, product_type: str) -> str:
        """브랜드 특성 설명 생성"""
        style_desc_map = {
            'Luxury': '프리미엄과 고급스러움을 추구하는',
            'Natural': '자연친화적이고 건강한 이미지의',
            'Trendy': '트렌디하고 젊은 감성의',
            'Classic': '클래식하고 전통적인 가치를 중시하는',
            'Minimal': '심플하고 세련된 미니멀리즘의',
            'Colorful': '화려하고 개성있는'
        }
        style_text = style_desc_map.get(style, '다양한 매력을 가진')

        values_text = ""
        if core_values:
            values_text = f" 핵심 가치는 '{', '.join(core_values[:3])}'입니다."

        slogan_text = ""
        if slogan:
            slogan_text = f" '{slogan}'이라는 슬로건처럼"

        return f"'{brand_name}'은 {style_text} 브랜드입니다.{slogan_text}{values_text} {product_type} 제품 홍보에 어울리는 인플루언서가 필요합니다."

    def _get_influencer_description(self, username: str, bio: str, image_analysis: Dict, classification: str, followers: int) -> str:
        """인플루언서 특성 설명 생성"""
        # 팔로워 규모
        if followers >= 100000:
            scale = "대형 인플루언서"
        elif followers >= 30000:
            scale = "중형 인플루언서"
        elif followers >= 10000:
            scale = "마이크로 인플루언서"
        else:
            scale = "나노 인플루언서"

        if followers >= 10000:
            follower_text = f"{followers/10000:.1f}만명의 팔로워를 보유한 {scale}"
        else:
            follower_text = f"{followers:,}명의 팔로워를 보유한 {scale}"

        # 전문 분야
        if classification == 'Expert':
            role_desc = "헤어 전문가로서 시술 과정과 전문 노하우를 공유하며 신뢰도가 높습니다"
        else:
            role_desc = "트렌드세터로서 스타일링 콘텐츠와 라이프스타일을 공유하며 MZ세대에게 인기가 높습니다"

        # 콘텐츠 스타일
        vibe = image_analysis.get('vibe', '')
        hair_tags = image_analysis.get('hair_style_tags', [])
        content_style = ""
        if vibe:
            content_style = f" {vibe} 분위기의 콘텐츠를 제작합니다."
        elif hair_tags:
            content_style = f" {', '.join(hair_tags[:2])} 관련 콘텐츠를 주로 게시합니다."

        # Bio 분석
        bio_insight = ""
        if '원장' in bio or '디렉터' in bio:
            bio_insight = " 살롱 운영 경험이 있어 전문성이 돋보입니다."
        elif '크리에이터' in bio:
            bio_insight = " 콘텐츠 크리에이터로서 영상 제작 능력이 뛰어납니다."
        elif '리뷰' in bio:
            bio_insight = " 솔직한 리뷰로 팔로워들의 신뢰를 받고 있습니다."

        return f"@{username}은 {follower_text}입니다. {role_desc}.{content_style}{bio_insight}"

    def _get_match_reason(self, classification: str, style: str, product_type: str, target_audience: str, image_analysis: Dict, campaign_description: str = "", bio: str = "") -> str:
        """매칭 이유 설명 생성 - 인플루언서 고유 특성을 반영한 개인화된 추천"""
        reasons = []

        # 1. 인플루언서의 고유 특성 먼저 언급 (vibe, aesthetic_tags 활용)
        vibe = image_analysis.get('vibe', '')
        aesthetic_tags = image_analysis.get('aesthetic_tags', [])
        hair_tags = image_analysis.get('hair_style_tags', [])
        dominant_style = image_analysis.get('dominant_style', '')

        # 인플루언서 특성 기반 첫 문장
        if vibe:
            reasons.append(f"'{vibe}' 분위기의 콘텐츠를 제작하여 브랜드 이미지와 잘 어울립니다")
        elif aesthetic_tags:
            tags_text = ', '.join(aesthetic_tags[:3])
            reasons.append(f"{tags_text} 스타일의 콘텐츠를 주로 게시하며 독특한 개성을 가지고 있습니다")

        # 2. Bio 기반 전문성/특징 (구체적으로)
        if bio:
            if '원장' in bio:
                if '청담' in bio or '강남' in bio or '압구정' in bio:
                    reasons.append("청담/강남 지역 살롱 원장으로서 프리미엄 시장에서의 인지도가 높습니다")
                else:
                    reasons.append("살롱 원장 경력으로 시술 과정과 제품 효과를 전문적으로 설명할 수 있습니다")
            if '년차' in bio or '경력' in bio:
                reasons.append("풍부한 현장 경험을 바탕으로 신뢰성 있는 제품 리뷰가 가능합니다")
            if '염색' in bio and ('염색' in product_type or '컬러' in product_type):
                reasons.append("염색 전문가로서 컬러 관련 제품 홍보에 최적화되어 있습니다")
            if '펌' in bio and '펌' in product_type:
                reasons.append("펌 전문가로서 관련 제품의 효과를 직접 시연할 수 있습니다")
            if '의사' in bio or '피부과' in bio:
                reasons.append("의료 전문가로서 두피/탈모 관련 제품에 대한 과학적 설명이 가능합니다")
            if '크리에이터' in bio or '유튜브' in bio:
                reasons.append("영상 콘텐츠 제작 능력이 뛰어나 제품 튜토리얼이나 리뷰 영상 제작에 적합합니다")
            if '리뷰' in bio:
                reasons.append("솔직한 리뷰어로 알려져 있어 팔로워들의 구매 결정에 영향력이 큽니다")

        # 3. 헤어 스타일 태그와 제품 연결
        if hair_tags:
            hair_text = ', '.join(hair_tags[:2])
            if '염색' in product_type or '컬러' in product_type:
                if any('컬러' in tag or '염색' in tag or '브라운' in tag or '블랙' in tag for tag in hair_tags):
                    reasons.append(f"평소 {hair_text} 스타일을 선보이며 컬러 제품 홍보에 자연스러운 연결이 가능합니다")
            elif '펌' in product_type or '웨이브' in product_type:
                if any('웨이브' in tag or '컬' in tag or '펌' in tag for tag in hair_tags):
                    reasons.append(f"{hair_text} 스타일로 펌/웨이브 제품과의 시너지가 기대됩니다")
            else:
                reasons.append(f"{hair_text} 스타일을 주로 연출하며 헤어케어 콘텐츠와 자연스럽게 어울립니다")

        # 4. 제품 유형과 인플루언서 타입 매칭
        professional_products = ['염색약', '펌제', '클리닉', '살롱전용', '두피케어', '탈색제']
        is_professional = any(p in product_type for p in professional_products)

        if is_professional and classification == 'Expert':
            reasons.append(f"'{product_type}' 같은 전문가용 제품은 살롱에서의 실제 시술 과정을 보여줄 수 있는 전문가가 효과적입니다")
        elif not is_professional and classification == 'Trendsetter':
            reasons.append(f"'{product_type}'은 일상 콘텐츠에 자연스럽게 녹여낼 수 있어 라이프스타일 인플루언서와 궁합이 좋습니다")

        # 5. 캠페인 설명과 인플루언서 특성 연결
        if campaign_description:
            campaign_lower = campaign_description.lower()
            if '탈모' in campaign_description or '두피' in campaign_description:
                if dominant_style == 'natural' or '건강' in vibe:
                    reasons.append("건강하고 자연스러운 이미지로 두피케어 캠페인 메시지를 효과적으로 전달할 수 있습니다")
            if '20대' in campaign_description or 'mz' in campaign_lower:
                trend_score = image_analysis.get('trend_relevance_score', 0)
                if trend_score > 0.7:
                    reasons.append(f"트렌드 적합도가 {int(trend_score*100)}%로 높아 MZ세대 타겟 캠페인에 효과적입니다")
            if '프리미엄' in campaign_description or '럭셔리' in campaign_description:
                if dominant_style == 'luxury' or '럭셔리' in vibe or '고급' in vibe:
                    reasons.append("프리미엄 브랜드 이미지와 일치하는 고급스러운 피드 분위기를 갖추고 있습니다")

        # 6. 브랜드 스타일과 인플루언서 스타일 매칭
        style_match = {
            ('Luxury', 'luxury'): "럭셔리 브랜드와 동일한 고급스러운 피드 분위기",
            ('Luxury', 'minimal'): "미니멀하면서도 세련된 이미지로 프리미엄 브랜드와 조화",
            ('Natural', 'natural'): "자연주의 브랜드 철학과 완벽히 일치하는 건강한 이미지",
            ('Trendy', 'trendy'): "트렌디한 감성으로 브랜드의 젊은 이미지와 시너지",
            ('Trendy', 'modern'): "모던하고 세련된 스타일로 트렌디 브랜드와 잘 어울림",
            ('Colorful', 'colorful'): "화려한 색감으로 컬러풀 브랜드 제품을 돋보이게 함"
        }
        match_key = (style, dominant_style)
        if match_key in style_match:
            reasons.append(style_match[match_key])

        # 최소 2개 이상의 이유 보장
        if len(reasons) < 2:
            if target_audience:
                reasons.append(f"'{target_audience}' 타겟층의 관심사와 일치하는 콘텐츠를 제작합니다")
            reasons.append("브랜드 캠페인에 적합한 콘텐츠 제작 역량을 갖추고 있습니다")

        return " ".join(reasons)

    def _get_style_description(self, bio: str, image_analysis: Dict, classification: str) -> str:
        """스타일 설명 생성"""
        vibe = image_analysis.get('vibe', '')
        if vibe:
            return vibe

        if '원장' in bio or '디렉터' in bio:
            return "프로페셔널 헤어 아티스트"
        elif '크리에이터' in bio or '인플루언서' in bio:
            return "트렌디한 스타일 크리에이터"
        elif '리뷰' in bio:
            return "솔직한 뷰티 리뷰어"
        elif classification == 'Expert':
            return "전문적인 헤어 시술 전문가"
        else:
            return "스타일링 콘텐츠를 제작하는 인플루언서"

    def _get_content_description(self, classification: str, image_analysis: Dict) -> str:
        """콘텐츠 설명 생성"""
        hair_tags = image_analysis.get('hair_style_tags', [])
        if hair_tags:
            styles = ', '.join(hair_tags[:2])
            if classification == 'Expert':
                return f"{styles} 시술 과정과 전문 노하우를 공유합니다."
            else:
                return f"{styles} 스타일링 콘텐츠로 높은 참여도를 보입니다."

        if classification == 'Expert':
            return "전문적인 시술 과정과 케어 팁을 공유합니다."
        else:
            return "트렌디한 스타일링 콘텐츠로 MZ세대에게 인기입니다."


# 테스트
if __name__ == "__main__":
    import json
    from pathlib import Path

    data_dir = Path(__file__).parent.parent / "data"

    # 데이터 로드
    with open(data_dir / "amore_brands.json", "r", encoding="utf-8") as f:
        brand_db = json.load(f)

    with open(data_dir / "influencers_data.json", "r", encoding="utf-8") as f:
        influencers = json.load(f).get("influencers", [])

    # 매칭 테스트
    matcher = InfluencerMatcher()

    brand = brand_db["brands"].get("미쟝센", {})
    brand["product_type"] = "샴푸"

    results = matcher.match(brand, influencers, top_k=5)

    print(f"\n=== {results['brand_info']['name']} 추천 결과 ===")
    print(f"분석: {results['total_analyzed']}명, FIS 통과: {results['total_passed_fis']}명")

    for rec in results['recommendations']:
        print(f"\n{rec['rank']}. @{rec['username']} ({rec['type']})")
        print(f"   적합도: {rec['match_score']}%")
        print(f"   사유: {rec['reason'][:80]}...")
