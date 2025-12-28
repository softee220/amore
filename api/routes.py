"""
API 라우터 - 인플루언서 추천 API
================================

엔드포인트:
- GET  /brands: 브랜드 목록
- GET  /brands/{name}: 브랜드 상세
- POST /recommend: 인플루언서 추천
- GET  /product-categories: 제품 카테고리
- GET  /influencers: 인플루언서 목록
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging

from config.products import PRODUCT_CATEGORIES
from pipeline import InfluencerMatcher, CampaignAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter()


# ============== Pydantic 모델 ==============

class RecommendRequest(BaseModel):
    """추천 요청"""
    brand_name: str
    product_type: Optional[str] = None
    product_line: Optional[str] = None  # 특정 제품라인 (자양윤모, PRO샴푸 등)
    description: Optional[str] = None  # 제품 설명 및 홍보 내용
    expert_count: Optional[int] = None  # None이면 자동 결정
    trendsetter_count: Optional[int] = None


# ============== 의존성 ==============

_campaign_analyzer: CampaignAnalyzer = None
_matcher: InfluencerMatcher = None
_influencers: List[Dict] = None
_brand_db: Dict = None


def init_routes(brand_db: Dict, influencers: List[Dict]):
    """라우터 초기화"""
    global _campaign_analyzer, _matcher, _influencers, _brand_db

    _brand_db = brand_db
    _influencers = influencers
    _campaign_analyzer = CampaignAnalyzer(brand_db)
    _matcher = InfluencerMatcher()


# ============== 브랜드 API ==============

@router.get("/brands")
async def get_brands():
    """브랜드 목록"""
    hair_brands = _brand_db.get("hair_brands", [])
    brands_detail = {}

    for name in hair_brands:
        info = _brand_db.get("brands", {}).get(name, {})
        brands_detail[name] = {
            "slogan": info.get("slogan", ""),
            "aesthetic_style": info.get("aesthetic_style", ""),
            "core_values": info.get("core_values", [])
        }

    return {
        "brands": list(_brand_db.get("brands", {}).keys()),
        "hair_brands": hair_brands,
        "brands_detail": brands_detail
    }


@router.get("/brands/{brand_name}")
async def get_brand_info(brand_name: str):
    """브랜드 상세 정보"""
    info = _brand_db.get("brands", {}).get(brand_name)
    if not info:
        raise HTTPException(status_code=404, detail="브랜드를 찾을 수 없습니다")
    return info


# ============== 추천 API ==============

@router.post("/recommend")
async def recommend_influencers(request: RecommendRequest):
    """
    인플루언서 추천

    파이프라인:
    1. 제품 설명 LLM 분석 (타겟, 스타일, 인플루언서 유형 추출)
    2. 브랜드 벡터 생성
    3. 각 인플루언서: 분류 → FIS 계산 → 벡터 생성
    4. 코사인 유사도 × FIS로 매칭 점수 계산
    5. Expert/Trendsetter 균형있게 추천
    """
    brand_info = _brand_db.get("brands", {}).get(request.brand_name, {})

    if not brand_info:
        raise HTTPException(
            status_code=404,
            detail=f"브랜드 '{request.brand_name}'을(를) 찾을 수 없습니다"
        )

    description = request.description or ""

    # 1. 제품 설명 LLM 분석 (설명이 있는 경우)
    analysis = {}
    if description:
        analysis = _campaign_analyzer.analyze(description, request.brand_name)

    # 설명이 브랜드 기본값과 다른 방향을 제시하는지 확인
    override_brand = analysis.get("override_brand", False)

    # 분석 결과 우선 적용 (설명이 브랜드와 다른 방향이면 설명 우선)
    if override_brand and analysis.get("aesthetic_style"):
        aesthetic_style = analysis.get("aesthetic_style")
    else:
        aesthetic_style = analysis.get("aesthetic_style") or brand_info.get("aesthetic_style", "Trendy")

    if override_brand and analysis.get("marketing_approach"):
        marketing_approach = analysis.get("marketing_approach")
    else:
        # 설명에서 추출한 marketing_approach 또는 브랜드 기본값
        marketing_approach = analysis.get("marketing_approach") or brand_info.get("marketing_approach")

    target_audience = analysis.get("target_audience") or brand_info.get("age_target", "")

    # 브랜드 데이터 구성 (product_lines 포함 + 브랜드 고유 특성)
    brand_data = {
        "brand_name": request.brand_name,
        "slogan": brand_info.get("slogan", ""),
        "core_values": brand_info.get("core_values", []),
        "target_keywords": brand_info.get("target_keywords", []),  # 브랜드 타겟 키워드
        "brand_philosophy": brand_info.get("brand_philosophy", ""),  # 브랜드 철학
        "expertise_focus": brand_info.get("expertise_focus", ""),  # 전문성 초점
        "target_audience": target_audience,
        "product_type": request.product_type or "",
        "aesthetic_style": aesthetic_style,
        "campaign_description": description,
        "expertise_level": brand_info.get("expertise_level", "low"),
        "product_lines": brand_info.get("product_lines", {}),
        "marketing_approach": marketing_approach,  # 설명에서 추출한 접근법 추가
        "description_override": override_brand  # 설명 우선 여부
    }

    # 2-5. 매칭 수행 (product_line 전달)
    total_count = 5
    if request.expert_count is not None and request.trendsetter_count is not None:
        total_count = request.expert_count + request.trendsetter_count

    results = _matcher.match(
        brand_data,
        _influencers,
        top_k=total_count,
        min_fis=40,
        expert_count=request.expert_count,
        trendsetter_count=request.trendsetter_count,
        product_line=request.product_line  # 제품라인 전달
    )

    # 브랜드 분석 텍스트 생성 (제품라인 정보 활용)
    product_type_display = results["brand_info"].get("product", "") or request.product_line or ""
    marketing_approach = results["brand_info"].get("marketing_approach", "consumer")

    results["brand_analysis"] = _generate_brand_analysis_v2(
        request.brand_name,
        brand_info,
        product_type_display,
        marketing_approach,
        description
    )

    # 분석 결과 추가 (설명이 있는 경우)
    if description:
        results["campaign_analysis"] = {
            "description": description,
            "target_audience": analysis.get("target_audience"),
            "aesthetic_style": analysis.get("aesthetic_style"),
            "marketing_approach": analysis.get("marketing_approach"),
            "influencer_type": analysis.get("influencer_type", "Both"),
            "keywords": analysis.get("keywords", []),
            "llm_analyzed": analysis.get("llm_analyzed", False),
            "override_brand": override_brand,  # 설명이 브랜드 기본값을 오버라이드했는지
            "applied_style": aesthetic_style,  # 실제 적용된 스타일
            "applied_marketing_approach": marketing_approach  # 실제 적용된 마케팅 접근법
        }

    return results


def _generate_brand_analysis_v2(
    brand_name: str, brand_info: Dict, product_type: str,
    marketing_approach: str, description: str = ""
) -> str:
    """브랜드 분석 텍스트 생성 v2 - 브랜드 설명만 간단히"""
    style = brand_info.get("aesthetic_style", "Trendy")
    slogan = brand_info.get("slogan", "")
    core_values = brand_info.get("core_values", [])

    # 스타일 설명
    style_desc_map = {
        'Luxury': '프리미엄과 고급스러움을 추구하는',
        'Natural': '자연친화적이고 건강한 이미지의',
        'Trendy': '트렌디하고 젊은 감성의',
        'Classic': '클래식하고 전통적인 가치를 중시하는',
        'Minimal': '심플하고 세련된 미니멀리즘의',
        'Colorful': '화려하고 개성있는'
    }
    style_text = style_desc_map.get(style, '다양한 매력을 가진')

    # 브랜드 설명만 간단히
    analysis = f"'{brand_name}'은 {style_text} 브랜드입니다."

    if slogan:
        analysis += f" '{slogan}'이라는 슬로건 아래,"

    if core_values:
        analysis += f" '{', '.join(core_values[:3])}'을 핵심 가치로 삼고 있습니다."

    return analysis


def _generate_brand_analysis(brand_name: str, brand_info: Dict, product_type: str, description: str = "") -> str:
    """(레거시) 브랜드 분석 텍스트 생성"""
    return _generate_brand_analysis_v2(brand_name, brand_info, product_type, "consumer", description)


# ============== 제품 API ==============

@router.get("/product-categories")
async def get_product_categories():
    """제품 카테고리 목록"""
    categories = []
    for name, info in PRODUCT_CATEGORIES.items():
        categories.append({
            'name': name,
            'description': info['description'],
            'icon': info['icon'],
            'target': info['target'],
            'product_count': len(info['products'])
        })
    return {"categories": categories, "total_categories": len(categories)}


@router.get("/product-categories/{category_name}")
async def get_products_by_category(category_name: str):
    """카테고리별 제품 목록"""
    if category_name not in PRODUCT_CATEGORIES:
        raise HTTPException(
            status_code=404,
            detail=f"카테고리 '{category_name}'을(를) 찾을 수 없습니다"
        )

    info = PRODUCT_CATEGORIES[category_name]
    return {
        "category": category_name,
        "description": info['description'],
        "icon": info['icon'],
        "target": info['target'],
        "products": info['products'],
        "product_count": len(info['products'])
    }


@router.get("/product-types")
async def get_product_types():
    """전체 제품 유형 목록"""
    categories = {name: info['products'] for name, info in PRODUCT_CATEGORIES.items()}
    all_products = []
    for info in PRODUCT_CATEGORIES.values():
        all_products.extend(info['products'])

    return {
        "categories": categories,
        "all_products": all_products,
        "total": len(all_products)
    }


# ============== 인플루언서 API ==============

@router.get("/influencers")
async def get_influencers():
    """인플루언서 목록"""
    return {"influencers": _influencers, "total": len(_influencers)}


@router.get("/influencers/{username}")
async def get_influencer_detail(username: str):
    """인플루언서 상세 정보"""
    from pipeline import FISCalculator, InfluencerClassifier

    influencer = next((inf for inf in _influencers if inf["username"] == username), None)
    if not influencer:
        raise HTTPException(status_code=404, detail="인플루언서를 찾을 수 없습니다")

    fis_calc = FISCalculator()
    classifier = InfluencerClassifier()

    return {
        "influencer": influencer,
        "classification": classifier.classify(influencer),
        "fis": fis_calc.calculate(influencer)
    }
