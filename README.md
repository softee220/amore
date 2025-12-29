# AI 헤어 인플루언서 큐레이션 에이전트

아모레퍼시픽 헤어 브랜드와 인플루언서 최적 매칭을 위한 AI 기반 추천 시스템

## 주요 기능

- **Expert/Trendsetter 분류**: 인플루언서 유형 자동 분류 및 분석 전략 분리
  - Expert: 텍스트 분석 Primary (bio/caption이 풍부)
  - Trendsetter: 이미지 분석 Primary (시각적 스타일 중심)
- **FIS (Fake Integrity Score)**: 6가지 지표로 허수 계정 필터링
- **7차원 벡터 매칭**: 코사인 유사도 기반 브랜드-인플루언서 매칭
- **LLM 기반 캠페인 분석**: 자연어로 캠페인 설명하면 최적 인플루언서 추천
- **XAI 추천 사유**: LLM이 생성하는 추천 이유 설명

## 시스템 아키텍처

```
Crawler → Processor → Vectorizer → Matcher → LLM Analyzer
   ↓          ↓           ↓           ↓           ↓
 수집       분류/분석    벡터화      매칭       추천이유
```

## 빠른 시작

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 설정

# 실행
./run.sh
# 또는
python server.py

# 종료
./stop.sh
```

## 접속

- **서버**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs

## 프로젝트 구조

```
amore/
├── server.py              # 메인 서버 (FastAPI)
├── run.sh / stop.sh       # 실행/종료 스크립트
├── requirements.txt       # 의존성
├── .env.example           # 환경변수 예시
│
├── api/                   # API 라우터
│   └── routes.py          # 엔드포인트 정의
│
├── pipeline/              # 핵심 파이프라인 모듈
│   ├── crawlers.py        # 데이터 수집
│   │   ├── BrandCrawler       # 브랜드 JSON 관리
│   │   └── InfluencerCrawler  # Instagram Graph API 수집
│   │
│   ├── processors.py      # 데이터 처리
│   │   ├── InfluencerProcessor  # 메인 처리 파이프라인
│   │   ├── FISCalculator        # 허수 계정 탐지 (6지표)
│   │   ├── InfluencerClassifier # Expert/Trendsetter 분류
│   │   └── ImageAnalyzer        # LLM 비전 이미지 분석
│   │
│   ├── vectorizer.py      # 벡터화
│   │   ├── BrandVectorizer      # 브랜드 7차원 벡터
│   │   ├── InfluencerVectorizer # 인플루언서 7차원 벡터
│   │   └── cosine_similarity    # 유사도 계산
│   │
│   ├── matcher.py         # 매칭 엔진
│   │   └── InfluencerMatcher    # 적합도 계산 및 추천
│   │
│   └── llm_analyzer.py    # LLM 분석
│       └── CampaignAnalyzer     # 캠페인 설명 분석
│
├── config/                # 설정
│   ├── products.py        # 제품 카테고리/키워드
│   └── instagram.py       # Instagram API 설정
│
├── data/                  # 데이터
│   ├── influencers_data.json  # 처리된 인플루언서 (100명)
│   ├── influencers_raw.json   # Raw 크롤링 데이터
│   └── amore_brands.json      # 아모레퍼시픽 헤어 브랜드
│
├── scripts/               # 유틸리티 스크립트
│   └── generate_sample_data.py  # 샘플 데이터 생성
│
└── static/                # 정적 파일
    └── index.html
```

## 핵심 알고리즘

### 1. Expert/Trendsetter 분류

```
Expert: 미용사, 살롱 원장, 시술 전문가
  → 텍스트 분석 Primary (bio/caption에 전문 정보 풍부)
  → 이미지 분석 Secondary (검증용)

Trendsetter: 스타일 크리에이터, 뷰티 인플루언서
  → 이미지 분석 Primary (bio가 간략하여 시각적 분석 필수)
  → 텍스트 분석 Secondary (해시태그 등 보조)
```

### 2. FIS (Fake Integrity Score)

```
FIS = (w1×V + w2×A + w3×E + w4×ACS + w5×DUP) × D/100

V:   조회수 변동성 (CV) - 뷰봇 탐지
A:   참여 비대칭성 (좋아요/조회수) - 좋아요 구매 탐지
E:   댓글 엔트로피 (댓글/조회수) - 봇 댓글 탐지
ACS: 활동 안정성 (업로드 간격)
D:   지리적 정합성 (한국 타겟)
DUP: 중복 콘텐츠 비율

가중치: V=0.20, A=0.25, E=0.15, ACS=0.10, D=0.15, DUP=0.15
```

### 3. 7차원 벡터 매칭

```
벡터: [luxury, professional, expert_pref, trend_pref, colorful, natural, modern]

적합도 = (유사도 × 0.25) + (FIS × 0.15) + (제품적합도 × 0.35) + (고유특성 × 0.25)
```

## API 엔드포인트

### 추천 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/api/recommend` | 기본 인플루언서 추천 |
| POST | `/api/recommend-campaign` | 캠페인 맞춤 추천 |

### 브랜드 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/api/brands` | 브랜드 목록 |
| GET | `/api/brands/{name}` | 브랜드 상세 |

### 제품 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/api/product-categories` | 제품 카테고리 |
| GET | `/api/product-categories/{name}` | 세부 제품 |

### 인플루언서 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/api/influencers` | 인플루언서 목록 |
| GET | `/api/influencers/{username}` | 인플루언서 분석 |

### 기타

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/api/chat` | 챗봇 대화 |
| GET | `/health` | 헬스 체크 |

## 캠페인 매칭 예시

```bash
curl -X POST "http://localhost:8000/api/recommend-campaign" \
  -H "Content-Type: application/json" \
  -d '{
    "brand_name": "려",
    "campaign_query": "탈모 고민 있는 30대 남성 대상 루트젠 샴푸 캠페인",
    "top_k": 5
  }'
```

## 지원 브랜드

| 브랜드 | 스타일 | 특징 |
|--------|--------|------|
| 려 (Ryo) | Natural | 한방, 탈모케어 |
| 미쟝센 | Trendy | 트렌디, 스타일링 |
| 라보에이치 | Natural | 더마, 두피과학 |
| 아모스프로페셔널 | Classic | 살롱 전문가용 |
| 아윤채 | Luxury | 프리미엄, 럭셔리 |
| 롱테이크 | Trendy | 지속가능, 향수 |

## 기술 스택

- **Backend**: FastAPI, Python 3.10+
- **AI/ML**: OpenAI API (GPT-4o-mini, Vision)
- **Data**: JSON 기반 데이터 저장
- **Algorithm**: 코사인 유사도, L2 정규화, Sigmoid 스케일링

## 데이터 스키마

### 인플루언서 (Processed)

```json
{
  "username": "hair_master_kim",
  "influencer_type": "expert",
  "followers": 85000,
  "bio": "청담동 헤어살롱 원장 | 15년차 미용사",
  "analysis_strategy": {
    "primary": "text",
    "secondary": "image"
  },
  "text_analysis": { ... },
  "image_analysis": { ... },
  "fis": {
    "score": 85.2,
    "verdict": "신뢰 계정"
  }
}
```

### 브랜드

```json
{
  "brand_name": "미쟝센",
  "aesthetic_style": "Trendy",
  "product_type": "샴푸",
  "marketing_approach": "consumer",
  "core_values": ["트렌디", "스타일링"]
}
```
