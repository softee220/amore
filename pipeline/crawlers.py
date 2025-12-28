"""
크롤러 모듈 - 브랜드 및 인플루언서 데이터 수집
==============================================

1. BrandCrawler: 아모레퍼시픽 헤어 브랜드 크롤링 + LLM 구조화
2. (인스타 인플루언서는 MVP용 데이터 사용)
"""

import os
import json
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

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

logger = logging.getLogger(__name__)

# 헤어 브랜드 URL
HAIR_BRANDS_URL = "https://www.apgroup.com/int/ko/brands/brands.html#Hair"
BASE_URL = "https://www.apgroup.com"

# LLM 브랜드 구조화 프롬프트
BRAND_EXTRACTION_PROMPT = """브랜드 정보를 분석하여 구조화된 JSON으로 추출하세요.

브랜드명: {brand_name}
슬로건: {slogan}
설명: {description}
상세페이지 URL: {detail_url}

JSON 형식:
{{
  "brand_name": "한글 브랜드명",
  "brand_name_en": "영문 브랜드명",
  "slogan": "핵심 슬로건",
  "tagline": "짧은 태그라인",
  "core_values": ["핵심가치1", "핵심가치2", ...],
  "brand_philosophy": "브랜드 철학 (2-3문장)",
  "target_keywords": ["타겟키워드1", "타겟키워드2", ...],
  "aesthetic_style": "Natural/Trendy/Luxury/Classic/Minimal 중 하나",
  "product_categories": ["제품카테고리1", "제품카테고리2", ...],
  "price_tier": "Premium/Mid-range/Professional/Mass 중 하나",
  "age_target": "타겟 연령층",
  "category": "Hair Care"
}}

JSON만 출력하세요."""


class BrandCrawler:
    """아모레퍼시픽 헤어 브랜드 크롤러"""

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent.parent / "data"
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0'
        })

    def crawl_hair_brands(self) -> Dict:
        """헤어 브랜드 목록 크롤링"""
        try:
            response = self.session.get(HAIR_BRANDS_URL, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            brands = {}
            hair_brands = []

            # 브랜드 카드 파싱
            brand_cards = soup.select('.brand-card, .brand-item, [data-category="Hair"]')

            for card in brand_cards:
                brand_info = self._parse_brand_card(card)
                if brand_info:
                    name = brand_info['brand_name']
                    brands[name] = brand_info
                    hair_brands.append(name)

            return {
                "brands": brands,
                "hair_brands": hair_brands,
                "metadata": {
                    "source": HAIR_BRANDS_URL,
                    "last_updated": datetime.now().isoformat(),
                    "total_brands": len(brands)
                }
            }

        except Exception as e:
            logger.error(f"브랜드 크롤링 실패: {e}")
            return {"brands": {}, "hair_brands": [], "error": str(e)}

    def _parse_brand_card(self, card) -> Optional[Dict]:
        """브랜드 카드에서 정보 추출"""
        try:
            name_elem = card.select_one('.brand-name, h3, .title')
            name = name_elem.get_text(strip=True) if name_elem else None

            if not name:
                return None

            slogan_elem = card.select_one('.brand-slogan, .slogan, .description')
            slogan = slogan_elem.get_text(strip=True) if slogan_elem else ""

            link_elem = card.select_one('a[href]')
            detail_url = ""
            if link_elem:
                href = link_elem.get('href', '')
                detail_url = urljoin(BASE_URL, href)

            return {
                "brand_name": name,
                "slogan": slogan,
                "detail_url": detail_url
            }

        except Exception as e:
            logger.warning(f"브랜드 카드 파싱 실패: {e}")
            return None

    def enrich_with_llm(self, brand_data: Dict) -> Dict:
        """LLM으로 브랜드 정보 구조화"""
        if not OPENAI_AVAILABLE or not self.api_key:
            return brand_data

        try:
            client = openai.OpenAI(api_key=self.api_key)

            prompt = BRAND_EXTRACTION_PROMPT.format(
                brand_name=brand_data.get("brand_name", ""),
                slogan=brand_data.get("slogan", ""),
                description=brand_data.get("description", ""),
                detail_url=brand_data.get("detail_url", "")
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "브랜드 분석 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.3
            )

            result_text = response.choices[0].message.content.strip()

            # JSON 파싱
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            enriched = json.loads(result_text.strip())
            enriched["detail_url"] = brand_data.get("detail_url", "")
            enriched["llm_structured"] = True

            return enriched

        except Exception as e:
            logger.warning(f"LLM 구조화 실패: {e}")
            return brand_data

    def crawl_and_save(self, use_llm: bool = True) -> Dict:
        """크롤링 후 파일 저장"""
        data = self.crawl_hair_brands()

        if use_llm and data.get("brands"):
            enriched_brands = {}
            for name, info in data["brands"].items():
                enriched = self.enrich_with_llm(info)
                enriched_brands[name] = enriched
                logger.info(f"브랜드 구조화 완료: {name}")

            data["brands"] = enriched_brands
            data["metadata"]["llm_structured"] = True

        # 저장
        output_path = self.data_dir / "amore_brands.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"브랜드 데이터 저장: {output_path}")
        return data

    def load_brands(self) -> Dict:
        """저장된 브랜드 데이터 로드"""
        path = self.data_dir / "amore_brands.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"brands": {}, "hair_brands": []}


# 테스트
if __name__ == "__main__":
    crawler = BrandCrawler()
    data = crawler.load_brands()
    print(f"로드된 브랜드: {len(data.get('brands', {}))}")
