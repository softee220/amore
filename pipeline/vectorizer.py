"""
벡터화 모듈 - 브랜드/인플루언서 벡터맵 생성
===========================================

벡터 구성 (7차원):
[luxury_score, professional_index, expert_pref, trendsetter_pref,
 colorfulness, natural_score, modern_score]

코사인 유사도로 매칭
"""

import math
from typing import Dict, List

# 스타일 정의
AESTHETIC_STYLES = {
    'Luxury': ['프리미엄', '럭셔리', '고급', '명품', 'VIP', '하이엔드'],
    'Natural': ['자연', '내추럴', '유기농', '비건', '친환경', '클린뷰티'],
    'Trendy': ['트렌디', '힙', '모던', 'MZ', '젊은', '감각적'],
    'Classic': ['클래식', '전통', '한방', '헤리티지'],
    'Minimal': ['미니멀', '심플', '깔끔', '베이직'],
    'Colorful': ['컬러풀', '화려', '비비드', '팝', '펀']
}

# 제품 전문성 지수
PRODUCT_PROFESSIONAL_INDEX = {
    # 전문가용
    '염색약': 0.9, '산화제': 0.95, '탈색제': 0.9, '펌제': 0.95, '클리닉': 0.9,
    '두피케어': 0.8, '손상모케어': 0.7, '살롱전용': 1.0,
    # 일반용
    '샴푸': 0.3, '린스': 0.25, '컨디셔너': 0.25, '트리트먼트': 0.4,
    '헤어에센스': 0.4, '헤어오일': 0.35, '헤어스프레이': 0.3, '왁스': 0.35,
    '고데기': 0.4, '드라이기': 0.35, '셀프염색': 0.45, '탈모샴푸': 0.55
}


class BrandVectorizer:
    """브랜드 데이터를 벡터로 변환"""

    def vectorize(self, brand_data: Dict) -> List[float]:
        """브랜드 벡터 생성"""
        # 스타일 분석
        aesthetic_style = brand_data.get('aesthetic_style', 'Trendy')
        slogan = brand_data.get('slogan', '')
        core_values = ' '.join(brand_data.get('core_values', []))
        full_text = f"{aesthetic_style} {slogan} {core_values}"

        # 럭셔리 점수
        luxury_score = 0.0
        if aesthetic_style == 'Luxury':
            luxury_score = 0.9
        else:
            luxury_keywords = AESTHETIC_STYLES.get('Luxury', [])
            matches = sum(1 for kw in luxury_keywords if kw in full_text)
            luxury_score = min(1.0, matches * 0.15)

        # 제품 전문성 지수
        product_type = brand_data.get('product_type', '샴푸')
        professional_index = PRODUCT_PROFESSIONAL_INDEX.get(product_type, 0.4)

        # 키워드로 전문성 보완
        for prod, idx in PRODUCT_PROFESSIONAL_INDEX.items():
            if prod in product_type:
                professional_index = idx
                break

        # Expert/Trendsetter 선호도
        if professional_index >= 0.7:
            expert_pref = 0.8
            trend_pref = 0.2
        elif professional_index <= 0.4:
            expert_pref = 0.2
            trend_pref = 0.8
        else:
            expert_pref = 0.5
            trend_pref = 0.5

        # 캠페인 설명 분석
        campaign = brand_data.get('campaign_description', '')
        trendy_keywords = ['트렌디', '힙', 'MZ', '젊은', 'Y2K', '스트릿']
        natural_keywords = ['자연', '내추럴', '순한', '친환경', '비건']
        colorful_keywords = ['화려', '컬러풀', '비비드', '팝']

        modern_score = sum(1 for kw in trendy_keywords if kw in campaign) * 0.15
        natural_score = sum(1 for kw in natural_keywords if kw in campaign) * 0.15
        colorfulness = sum(1 for kw in colorful_keywords if kw in campaign) * 0.15

        # 기본값 추가
        modern_score = min(1, modern_score + 0.3)
        natural_score = min(1, natural_score + 0.3)
        colorfulness = min(1, colorfulness + 0.3)

        # 스타일 기반 보정
        style_scores = self._get_style_scores(aesthetic_style)
        colorfulness = max(colorfulness, style_scores.get('colorful', 0))
        natural_score = max(natural_score, style_scores.get('natural', 0))
        modern_score = max(modern_score, style_scores.get('trendy', 0))

        # 벡터 생성
        vector = [
            luxury_score,
            professional_index,
            expert_pref,
            trend_pref,
            colorfulness,
            natural_score,
            modern_score
        ]

        return self._normalize(vector)

    def _get_style_scores(self, style: str) -> Dict[str, float]:
        """스타일별 점수"""
        style_map = {
            'Luxury': {'luxury': 0.9, 'colorful': 0.2, 'natural': 0.1, 'trendy': 0.3},
            'Natural': {'luxury': 0.3, 'colorful': 0.1, 'natural': 0.9, 'trendy': 0.2},
            'Trendy': {'luxury': 0.3, 'colorful': 0.5, 'natural': 0.2, 'trendy': 0.9},
            'Classic': {'luxury': 0.6, 'colorful': 0.1, 'natural': 0.3, 'trendy': 0.1},
            'Minimal': {'luxury': 0.5, 'colorful': 0.1, 'natural': 0.4, 'trendy': 0.4},
            'Colorful': {'luxury': 0.2, 'colorful': 0.9, 'natural': 0.1, 'trendy': 0.7}
        }
        return style_map.get(style, {'luxury': 0.3, 'colorful': 0.3, 'natural': 0.3, 'trendy': 0.3})

    def _normalize(self, vector: List[float]) -> List[float]:
        """L2 정규화"""
        magnitude = math.sqrt(sum(v ** 2 for v in vector))
        if magnitude > 0:
            return [v / magnitude for v in vector]
        return vector


class InfluencerVectorizer:
    """인플루언서 데이터를 벡터로 변환"""

    def vectorize(self, influencer: Dict, classification_result: Dict = None) -> List[float]:
        """인플루언서 벡터 생성"""
        bio = influencer.get('bio', '')
        posts = influencer.get('recent_posts', [])
        captions = ' '.join([p.get('caption', '') for p in posts])
        image_analysis = influencer.get('image_analysis', {})

        # 분류 결과
        if classification_result:
            role_vector = classification_result.get('role_vector', [0.5, 0.5])
        else:
            role_vector = [0.5, 0.5]

        expert_score = role_vector[0]
        trendsetter_score = role_vector[1]

        # 럭셔리 점수 (bio + 이미지 분석)
        luxury_keywords = ['프리미엄', '럭셔리', '고급', 'VIP', '청담', '압구정']
        mass_keywords = ['가성비', '저렴', '다이소', '올리브영']

        luxury_count = sum(1 for kw in luxury_keywords if kw in bio)
        mass_count = sum(1 for kw in mass_keywords if kw in bio)

        if luxury_count > mass_count:
            luxury_score = 0.7 + (luxury_count * 0.1)
        elif mass_count > luxury_count:
            luxury_score = 0.3 - (mass_count * 0.05)
        else:
            luxury_score = 0.5

        # 이미지 분석 반영
        if image_analysis:
            dominant_style = image_analysis.get('dominant_style', '')
            if dominant_style == 'luxury':
                luxury_score = max(luxury_score, 0.85)
            elif dominant_style == 'minimal':
                luxury_score = max(luxury_score, 0.6)

        luxury_score = max(0, min(1, luxury_score))

        # 전문성 점수
        professional_score = expert_score * 0.8 + 0.1
        if image_analysis:
            prof = image_analysis.get('professionalism_score', 0.5)
            professional_score = (professional_score + prof) / 2

        # 스타일 점수
        colorful_keywords = ['화려', '컬러풀', '비비드', '핑크', '블루']
        natural_keywords = ['자연', '내추럴', '비건', '유기농', '친환경']
        modern_keywords = ['트렌드', '트렌디', 'MZ', '힙', 'Y2K']

        colorfulness = sum(1 for kw in colorful_keywords if kw in captions) * 0.2
        natural_score = sum(1 for kw in natural_keywords if kw in captions) * 0.2
        modern_score = sum(1 for kw in modern_keywords if kw in captions) * 0.2

        # 이미지 분석 반영
        if image_analysis:
            dominant_style = image_analysis.get('dominant_style', '')
            trend_rel = image_analysis.get('trend_relevance_score', 0.5)

            if dominant_style == 'colorful':
                colorfulness = max(colorfulness, 0.8)
            if dominant_style == 'natural':
                natural_score = max(natural_score, 0.8)
            if dominant_style == 'trendy':
                modern_score = max(modern_score, 0.8)

            modern_score = (modern_score + trend_rel) / 2

        # 정규화
        colorfulness = min(1, colorfulness + 0.3)
        natural_score = min(1, natural_score + 0.3)
        modern_score = min(1, modern_score + 0.3)

        # 벡터 생성
        vector = [
            luxury_score,
            professional_score,
            expert_score,
            trendsetter_score,
            colorfulness,
            natural_score,
            modern_score
        ]

        return self._normalize(vector)

    def _normalize(self, vector: List[float]) -> List[float]:
        """L2 정규화"""
        magnitude = math.sqrt(sum(v ** 2 for v in vector))
        if magnitude > 0:
            return [v / magnitude for v in vector]
        return vector


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """코사인 유사도 계산"""
    if len(vec1) != len(vec2):
        max_len = max(len(vec1), len(vec2))
        vec1 = vec1 + [0] * (max_len - len(vec1))
        vec2 = vec2 + [0] * (max_len - len(vec2))

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a ** 2 for a in vec1))
    mag2 = math.sqrt(sum(b ** 2 for b in vec2))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


# 테스트
if __name__ == "__main__":
    brand_vectorizer = BrandVectorizer()
    inf_vectorizer = InfluencerVectorizer()

    brand = {
        "brand_name": "미쟝센",
        "aesthetic_style": "Trendy",
        "product_type": "샴푸",
        "slogan": "SHINE YOUR SCENE"
    }
    brand_vec = brand_vectorizer.vectorize(brand)
    print(f"브랜드 벡터: {[round(v, 3) for v in brand_vec]}")

    influencer = {
        "username": "style_creator",
        "bio": "트렌디한 헤어 스타일링 크리에이터"
    }
    classification = {"role_vector": [0.3, 0.7]}
    inf_vec = inf_vectorizer.vectorize(influencer, classification)
    print(f"인플루언서 벡터: {[round(v, 3) for v in inf_vec]}")

    sim = cosine_similarity(brand_vec, inf_vec)
    print(f"유사도: {sim:.4f}")
