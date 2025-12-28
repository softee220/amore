"""
아모레퍼시픽 헤어 브랜드 제품 카테고리
=====================================

브랜드별 주요 제품:
- 려: 탈모케어 샴푸, 두피세럼, 트리트먼트
- 미쟝센: 에센스, 셀프염색(헬로버블), 샴푸, 스타일링
- 라보에이치: 두피케어 샴푸, 스캘프 세럼
- 아윤채: PRO 샴푸/트리트먼트(살롱전용), 염색약, 펌제
- 아모스 프로페셔널: 살롱 염색약, 펌제, 클리닉
- 롱테이크: 헤어 퍼퓸, 디퓨저, 샴푸
"""

# 아모레퍼시픽 헤어 브랜드 기준 제품 카테고리
PRODUCT_CATEGORIES = {
    '샴푸': {
        'description': '모발 세정 제품',
        'icon': '🧴',
        'target': 'consumer',
        'marketing_approach': 'consumer',
        'brands': ['려', '미쟝센', '라보에이치', '롱테이크'],
        'products': [
            '일반 샴푸',
            '탈모케어 샴푸',
            '두피케어 샴푸',
            '손상모 샴푸',
            '지성두피 샴푸',
            '볼륨 샴푸'
        ]
    },
    '트리트먼트': {
        'description': '모발 영양 및 집중 케어',
        'icon': '✨',
        'target': 'consumer',
        'marketing_approach': 'consumer',
        'brands': ['려', '미쟝센'],
        'products': [
            '데일리 트리트먼트',
            '손상모 트리트먼트',
            '헤어팩',
            '헤어마스크'
        ]
    },
    '에센스': {
        'description': '모발 보호 및 윤기 케어 (에센스, 세럼, 오일)',
        'icon': '💧',
        'target': 'consumer',
        'marketing_approach': 'consumer',
        'brands': ['미쟝센', '려'],
        'products': [
            '헤어 에센스',
            '헤어 오일',
            '헤어 세럼',
            '열보호 에센스'
        ]
    },
    '두피케어': {
        'description': '두피 건강 및 탈모 예방 전문 케어',
        'icon': '🌿',
        'target': 'both',
        'marketing_approach': 'expert_oriented',
        'brands': ['려', '라보에이치'],
        'products': [
            '두피 토닉',
            '두피 세럼',
            '두피 앰플',
            '탈모케어 앰플',
            '스캘프 스케일러'
        ]
    },
    '스타일링': {
        'description': '헤어 스타일링 제품',
        'icon': '💇',
        'target': 'consumer',
        'marketing_approach': 'consumer',
        'brands': ['미쟝센', '아모스 프로페셔널'],
        'products': [
            '헤어 왁스',
            '헤어 스프레이',
            '헤어 무스',
            '볼륨 파우더'
        ]
    },
    '셀프염색': {
        'description': '가정용 셀프 염색 제품',
        'icon': '🎨',
        'target': 'consumer',
        'marketing_approach': 'consumer',
        'brands': ['미쟝센'],
        'products': [
            '거품 염색약 (헬로버블)',
            '새치 커버',
            '컬러 트리트먼트'
        ]
    },
    '살롱 케어': {
        'description': '살롱 전용 세정 및 케어 (샴푸, 트리트먼트)',
        'icon': '🏪',
        'target': 'professional',
        'marketing_approach': 'professional',
        'brands': ['아윤채', '아모스 프로페셔널'],
        'products': [
            'PRO 샴푸',
            'PRO 트리트먼트',
            '살롱 클리닉'
        ]
    },
    '살롱 염색': {
        'description': '살롱 전용 염색 제품',
        'icon': '🎨',
        'target': 'professional',
        'marketing_approach': 'professional',
        'brands': ['아윤채', '아모스 프로페셔널'],
        'products': [
            '프로페셔널 염색약',
            '산화제',
            '탈색제'
        ]
    },
    '살롱 펌': {
        'description': '살롱 전용 펌 제품',
        'icon': '🌀',
        'target': 'professional',
        'marketing_approach': 'professional',
        'brands': ['아윤채', '아모스 프로페셔널'],
        'products': [
            '펌제',
            '중화제',
            '디지털펌 전용'
        ]
    },
    '헤어 프래그런스': {
        'description': '헤어 향수 및 라이프스타일',
        'icon': '🌸',
        'target': 'consumer',
        'marketing_approach': 'consumer',
        'brands': ['롱테이크'],
        'products': [
            '헤어 퍼퓸',
            '헤어 미스트',
            '디퓨저'
        ]
    }
}


# 자연어 추출용 제품 키워드 매핑 (아모레 브랜드 제품 기준)
PRODUCT_KEYWORDS = {
    # 샴푸
    "샴푸": ["샴푸", "shampoo", "세정"],
    "탈모샴푸": ["탈모샴푸", "탈모케어", "자양윤모"],
    "두피샴푸": ["두피샴푸", "두피케어", "스캘프"],
    "손상모샴푸": ["손상모", "데미지케어"],

    # 트리트먼트
    "트리트먼트": ["트리트먼트", "treatment", "린스"],
    "헤어팩": ["헤어팩", "hair pack", "헤어마스크"],

    # 에센스/세럼
    "에센스": ["에센스", "essence", "퍼펙트세럼"],
    "오일": ["오일", "oil"],
    "세럼": ["세럼", "serum"],

    # 두피케어
    "두피토닉": ["두피토닉", "토닉", "스캘프토닉"],
    "두피세럼": ["두피세럼", "스캘프세럼"],
    "두피앰플": ["두피앰플", "탈모앰플", "앰플"],

    # 스타일링
    "왁스": ["왁스", "wax"],
    "스프레이": ["스프레이", "spray", "헤어스프레이"],
    "무스": ["무스", "mousse"],

    # 셀프염색
    "셀프염색": ["셀프염색", "헬로버블", "거품염색", "홈염색"],
    "새치커버": ["새치", "새치커버", "흑운"],
    "컬러트리트먼트": ["컬러트리트먼트"],

    # 살롱 제품
    "살롱샴푸": ["PRO샴푸", "프로샴푸", "살롱샴푸"],
    "살롱트리트먼트": ["PRO트리트먼트", "살롱케어", "클리닉"],
    "염색약": ["염색약", "프로페셔널염색", "살롱염색"],
    "탈색제": ["탈색", "블리치", "하이리프트"],
    "펌제": ["펌제", "펌약", "웨이브"],

    # 프래그런스
    "헤어퍼퓸": ["헤어퍼퓸", "헤어향수", "퍼퓸"],
    "디퓨저": ["디퓨저", "diffuser", "공간향"]
}


# 브랜드별 대표 제품 라인 (API에서 활용)
BRAND_PRODUCT_LINES = {
    '려': {
        'main_categories': ['샴푸', '트리트먼트', '두피케어'],
        'featured_lines': ['자양윤모', '청아', '흑운', '두피 세럼'],
        'expertise_level': 'medium_high'
    },
    '미쟝센': {
        'main_categories': ['샴푸', '트리트먼트', '에센스/세럼', '스타일링', '셀프염색'],
        'featured_lines': ['퍼펙트 세럼', '헬로버블', '샤이닝 에센스', '손상모 샴푸'],
        'expertise_level': 'low'
    },
    '라보에이치': {
        'main_categories': ['샴푸', '두피케어'],
        'featured_lines': ['탈모증상케어', '두피강화케어', '지성두피케어', '스캘프 세럼'],
        'expertise_level': 'high'
    },
    '아윤채': {
        'main_categories': ['살롱 샴푸/트리트먼트', '살롱 염색', '살롱 펌'],
        'featured_lines': ['PRO 샴푸', 'PRO 트리트먼트', 'TAKE HOME 라인', '펌제', '염색약'],
        'expertise_level': 'high'
    },
    '아모스 프로페셔널': {
        'main_categories': ['살롱 샴푸/트리트먼트', '살롱 염색', '살롱 펌', '스타일링'],
        'featured_lines': ['그린티 샴푸', '커리큘럼', '염색약', '펌제', '스타일링'],
        'expertise_level': 'high'
    },
    '롱테이크': {
        'main_categories': ['샴푸', '헤어 프래그런스'],
        'featured_lines': ['헤어 퍼퓸', '디퓨저', '샴푸'],
        'expertise_level': 'low'
    }
}


# 마케팅 접근법별 카테고리 그룹
MARKETING_APPROACH_CATEGORIES = {
    'professional': ['살롱 케어', '살롱 염색', '살롱 펌'],
    'expert_oriented': ['두피케어'],
    'consumer': ['샴푸', '트리트먼트', '에센스', '스타일링', '셀프염색', '헤어 프래그런스']
}
