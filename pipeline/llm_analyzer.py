"""
LLM 분석 모듈 - 자연어 입력 분석
================================

제품 설명/홍보 내용에서 추출:
- target_audience: 타겟 고객층
- aesthetic_style: 원하는 스타일
- influencer_type: Expert/Trendsetter/Both
- keywords: 관련 키워드
"""

import os
import json
from typing import Dict, Optional

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


# 분석 프롬프트
ANALYSIS_PROMPT = """제품/홍보 설명을 분석하여 인플루언서 매칭에 필요한 정보를 추출하세요.

설명:
{description}

브랜드 정보:
- 브랜드명: {brand_name}
- 기본 스타일: {brand_style}
- 타겟층: {brand_target}
- 기본 마케팅 접근법: {brand_marketing_approach}

**중요**: 설명 내용이 브랜드 기본값과 다른 방향을 제시하면, 설명 내용을 우선하세요.
예: 고급 브랜드라도 "트렌디한 MZ세대 공략" 같은 설명이 있으면 Trendy 스타일을 반환.

JSON으로 응답하세요:
```json
{{
  "target_audience": "타겟 고객층 (예: 20대 여성). 없으면 null",
  "aesthetic_style": "Luxury/Trendy/Natural/Classic/Minimal/Colorful 중 하나. 없으면 null",
  "influencer_type": "Expert(전문가)/Trendsetter(트렌드세터)/Both 중 하나",
  "marketing_approach": "professional(살롱전문가용)/expert_oriented(전문성강조)/consumer(일반소비자) 중 하나. 없으면 null",
  "override_brand": true/false (설명이 브랜드 기본값과 다른 방향이면 true),
  "keywords": ["관련 키워드 3-5개"]
}}
```

JSON만 출력하세요."""


class CampaignAnalyzer:
    """제품/홍보 설명 분석기"""

    def __init__(self, brand_db: Dict = None):
        self.brand_db = brand_db or {}
        self.api_key = os.getenv("OPENAI_API_KEY")

    def analyze(self, description: str, brand_name: str = None) -> Dict:
        """
        제품 설명을 분석하여 매칭에 필요한 정보 추출

        Args:
            description: 제품/홍보 설명
            brand_name: 브랜드명 (선택)

        Returns:
            추출된 정보
        """
        if not description or not description.strip():
            return {
                "target_audience": None,
                "aesthetic_style": None,
                "influencer_type": "Both",
                "keywords": []
            }

        # 브랜드 정보 가져오기
        brand_info = {}
        if brand_name:
            brand_info = self.brand_db.get("brands", {}).get(brand_name, {})

        # LLM 사용 가능하면 LLM으로 분석
        if OPENAI_AVAILABLE and self.api_key:
            result = self._analyze_with_llm(description, brand_name, brand_info)
            if result:
                return result

        # 폴백: 키워드 매칭
        return self._analyze_with_keywords(description)

    def _analyze_with_llm(self, description: str, brand_name: str, brand_info: Dict) -> Optional[Dict]:
        """LLM으로 분석"""
        try:
            client = openai.OpenAI(api_key=self.api_key)

            prompt = ANALYSIS_PROMPT.format(
                description=description,
                brand_name=brand_name or "미지정",
                brand_style=brand_info.get("aesthetic_style", "미지정"),
                brand_target=brand_info.get("age_target", "미지정"),
                brand_marketing_approach=brand_info.get("marketing_approach", "미지정")
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "제품 분석 전문가입니다. JSON만 출력하세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.2
            )

            result_text = response.choices[0].message.content.strip()

            # JSON 파싱
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            parsed = json.loads(result_text.strip())
            parsed["llm_analyzed"] = True
            return parsed

        except Exception as e:
            print(f"LLM 분석 오류: {e}")
            return None

    def _analyze_with_keywords(self, description: str) -> Dict:
        """키워드 매칭으로 분석 (폴백)"""
        desc = description.lower()

        # 타겟 추출
        target = None
        for age in ["20대", "30대", "40대", "50대"]:
            if age in description:
                target = age
                break

        if "여성" in description:
            target = (target + " " if target else "") + "여성"
        elif "남성" in description:
            target = (target + " " if target else "") + "남성"

        # 스타일 추출
        style = None
        style_map = {
            "Luxury": ["럭셔리", "고급", "프리미엄", "하이엔드"],
            "Trendy": ["트렌디", "힙", "mz", "젊은", "y2k", "감각적"],
            "Natural": ["자연", "내추럴", "건강", "유기농", "비건", "클린"],
            "Classic": ["클래식", "전통", "한방"],
            "Minimal": ["미니멀", "심플", "깔끔"],
            "Colorful": ["컬러풀", "화려", "비비드", "팝"]
        }

        for style_name, keywords in style_map.items():
            if any(kw in desc for kw in keywords):
                style = style_name
                break

        # 인플루언서 유형
        expert_kw = ["전문가", "살롱", "원장", "미용사", "시술", "전문"]
        trend_kw = ["인스타", "릴스", "유튜브", "크리에이터", "인플루언서", "바이럴"]

        expert_score = sum(1 for kw in expert_kw if kw in desc)
        trend_score = sum(1 for kw in trend_kw if kw in desc)

        if expert_score > trend_score:
            inf_type = "Expert"
        elif trend_score > expert_score:
            inf_type = "Trendsetter"
        else:
            inf_type = "Both"

        # 마케팅 접근법 추출
        marketing_approach = None
        professional_kw = ["살롱", "프로", "pro", "전문가용", "시술", "미용사", "원장"]
        expert_oriented_kw = ["두피", "탈모", "성분", "효능", "과학", "임상", "전문성"]
        consumer_kw = ["일상", "데일리", "셀프", "홈케어", "간편", "쉽게", "누구나"]

        prof_score = sum(1 for kw in professional_kw if kw in desc)
        exp_ori_score = sum(1 for kw in expert_oriented_kw if kw in desc)
        cons_score = sum(1 for kw in consumer_kw if kw in desc)

        if prof_score > exp_ori_score and prof_score > cons_score:
            marketing_approach = "professional"
        elif exp_ori_score > cons_score:
            marketing_approach = "expert_oriented"
        elif cons_score > 0:
            marketing_approach = "consumer"
        # marketing_approach가 None이면 브랜드 기본값 사용

        # 키워드
        keywords = []
        kw_pool = ["탈모", "두피", "염색", "펌", "손상모", "볼륨", "윤기", "케어", "트리트먼트", "샴푸"]
        for kw in kw_pool:
            if kw in description:
                keywords.append(kw)

        # override_brand: 스타일이나 마케팅 접근법이 명시되었으면 True
        override_brand = style is not None or marketing_approach is not None

        return {
            "target_audience": target.strip() if target else None,
            "aesthetic_style": style,
            "influencer_type": inf_type,
            "marketing_approach": marketing_approach,
            "override_brand": override_brand,
            "keywords": keywords[:5],
            "llm_analyzed": False
        }


# 하위 호환성
ChatBot = CampaignAnalyzer


# 테스트
if __name__ == "__main__":
    analyzer = CampaignAnalyzer()

    test_cases = [
        "20대 여성 대상 탈모 예방 샴푸, 전문가 느낌으로",
        "MZ세대 타겟 트렌디한 염색약, 인스타 릴스로 바이럴",
        "프리미엄 두피케어 제품, 고급스러운 이미지로"
    ]

    print("제품 설명 분석 테스트")
    print("=" * 50)

    for desc in test_cases:
        print(f"\n설명: {desc}")
        result = analyzer.analyze(desc)
        print(f"  타겟: {result['target_audience']}")
        print(f"  스타일: {result['aesthetic_style']}")
        print(f"  인플루언서: {result['influencer_type']}")
        print(f"  키워드: {result['keywords']}")
