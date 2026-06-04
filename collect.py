#!/usr/bin/env python3
# collect.py - 새미네뉴스 수집기 v5
# 의존성: pip install feedparser anthropic

import feedparser
import json
import os
import re
import hashlib
import time
from datetime import datetime, timedelta, timezone

# ─────────────────────────────────────────
# ★ Gemini API 키 설정
# aistudio.google.com → Get API Key → Create API key
# 아래 "" 안에 본인 키 입력 (AIza... 로 시작)
# ─────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# aistudio.google.com → Get API Key → Create API key

USE_AI = bool(GEMINI_API_KEY.strip())

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT_FILE     = os.path.join(DATA_DIR, "news.json")
KEEP_DAYS    = 30
MAX_PER_FEED = 30
AI_DELAY     = 5.0   # API 호출 간격(초) — 15 RPM 한도 대응

feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ─────────────────────────────────────────
# 소스 목록
# ─────────────────────────────────────────

SOURCES = [
    # ── 국내 미디어 ─────────────────────────────────────
    {"name": "식품외식경제",   "lang": "ko", "cat_hint": None,
     "url": "http://www.foodbank.co.kr/rss/allArticle.xml"},
    {"name": "K푸드타임즈",    "lang": "ko", "cat_hint": None,
     "url": "http://www.kfoodtimes.com/rss/allArticle.xml"},
    {"name": "식품음료신문",   "lang": "ko", "cat_hint": None,
     "url": "https://www.thinkfood.co.kr/rss/allArticle.xml"},
    {"name": "식품뉴스",       "lang": "ko", "cat_hint": None,
     "url": "http://www.foodnews.co.kr/rss/allArticle.xml"},
    {"name": "푸드투데이",     "lang": "ko", "cat_hint": None,
     "url": "https://foodtoday.or.kr/rss/allArticle.xml"},
    {"name": "푸드아이콘",     "lang": "ko", "cat_hint": None,
     "url": "https://www.foodicon.co.kr/rss/allArticle.xml"},
    {"name": "리얼푸드",       "lang": "ko", "cat_hint": None,
     "url": "https://www.realfoods.co.kr/rss/allArticle.xml"},
    {"name": "쿡앤셰프뉴스",   "lang": "ko", "cat_hint": None,
     "url": "https://www.cooknchefnews.com/rss/allArticle.xml"},
    {"name": "한국경제 F&B",   "lang": "ko", "cat_hint": None,
     "url": "https://www.hankyung.com/rss/distribution.xml"},
    {"name": "비건뉴스",       "lang": "ko", "cat_hint": "식재료·원료",
     "url": "https://www.vegannews.co.kr/rss/allArticle.xml"},
    {"name": "비거로그",       "lang": "ko", "cat_hint": "식재료·원료",
     "url": "https://vegilog.com/feed"},
    # ── 편의점 (Google News RSS) ────────────────────────
    {"name": "편의점 신제품",  "lang": "ko", "cat_hint": "편의점",
     "url": "https://news.google.com/rss/search?q=%ED%8E%B8%EC%9D%98%EC%A0%90+%EC%8B%A0%EC%A0%9C%ED%92%88+%EC%B6%9C%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"},
    {"name": "CU 소식",        "lang": "ko", "cat_hint": "편의점",
     "url": "https://news.google.com/rss/search?q=CU+%EC%8B%A0%EC%A0%9C%ED%92%88+%EC%B6%9C%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"},
    {"name": "GS25 소식",      "lang": "ko", "cat_hint": "편의점",
     "url": "https://news.google.com/rss/search?q=GS25+%EC%8B%A0%EC%A0%9C%ED%92%88+%EC%B6%9C%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"},
    {"name": "세븐일레븐 소식", "lang": "ko", "cat_hint": "편의점",
     "url": "https://news.google.com/rss/search?q=%EC%84%B8%EB%B8%90%EC%9D%BC%EB%A0%88%EB%B8%90+%EC%8B%A0%EC%A0%9C%ED%92%88&hl=ko&gl=KR&ceid=KR:ko"},
    # ── 해외 ────────────────────────────────────────────
    {"name": "Food Navigator",           "lang": "en", "cat_hint": None,
     "url": "https://www.foodnavigator.com/rss/news"},
    {"name": "Food Dive",                "lang": "en", "cat_hint": None,
     "url": "https://www.fooddive.com/feeds/news/"},
    {"name": "Food Ingredients First",   "lang": "en", "cat_hint": None,
     "url": "https://www.foodingredientsfirst.com/rss/news"},
    {"name": "Nation's Restaurant News", "lang": "en", "cat_hint": None,
     "url": "https://www.nrn.com/rss.xml"},
    {"name": "Eater",                    "lang": "en", "cat_hint": None,
     "url": "https://www.eater.com/rss/index.xml"},
    # ── 일본 ────────────────────────────────────────────
    {"name": "NISSYOKU", "lang": "ja", "cat_hint": None,
     "url": "https://news.nissyoku.co.jp/rss"},
]

# ─────────────────────────────────────────
# 카테고리 키워드
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# 기사 카테고리 (6개 / Gemini가 분류)
#
# [신제품·NPD]      제품 출시·론칭·리뉴얼·신메뉴
# [소비자·시장]     소비 트렌드·시장 리포트·소비자 조사
# [식재료·원료]     원료·성분·발효기술·기능성 소재 중심 기사
# [채널·유통]       편의점·마트·외식·배달 채널 전략
# [브랜드·기업]     기업 전략·투자·M&A·브랜드 포지셔닝
# [산업·정책]       규제·수급·식품안전·원가·수출입
# ─────────────────────────────────────────
# 편의점 여부는 채널 태그로 별도 저장 (is_cvs 필드)
VALID_CATEGORIES = [
    "신제품·NPD", "소비자·시장", "식재료·원료",
    "채널·유통", "브랜드·기업", "산업·정책"
]
CVS_KEYWORDS = ["편의점", "CU", "GS25", "세븐일레븐", "이마트24", "미니스톱", "convenience store"]

# ─────────────────────────────────────────
# AI 요약 (Claude Haiku)
# ─────────────────────────────────────────

def gemini_analyze(title: str, raw_text: str, lang: str) -> dict:
    """Gemini Flash: 요약 + 키워드 + 해외 번역"""
    import json as _json
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        if lang == "ko":
            prompt = f"""다음 F&B 뉴스를 분석해줘.

제목: {title}
본문: {raw_text[:600]}

JSON만 반환. 설명 금지.

[기사 주카테고리 - 반드시 1개]
아래 6개 중 기사의 핵심 성격에 맞는 것 1개만 선택:
- 신제품·NPD: 제품 출시·론칭·리뉴얼·신메뉴가 핵심 (출시가 핵심이면 편의점 기사도 이걸로)
- 소비자·시장: 소비자 니즈 변화·시장 성장·리포트·조사 결과가 핵심
- 식재료·원료: 특정 원료·성분·발효기술·기능성 소재가 기사 중심
- 채널·유통: 편의점·마트·외식·배달 채널 전략 변화가 핵심
- 브랜드·기업: 기업 전략·투자·M&A·브랜드 포지셔닝이 핵심
- 산업·정책: 규제·수급·식품안전·원가·수출입이 핵심

[시그널 키워드 - 메뉴 개발 관점]
food_cat/ingredient/trend/brand 중 하나로 분류. 애매하면 제외.
- food_cat: 매대/메뉴판에서 바로 고를 수 있는 완성형 식품 (그릭요거트, HMR, 오마카세 등)
- ingredient: 제품 안에 들어가는 원재료·성분 (귀리, 피스타치오, 콜라겐, 누룩 등)
- trend: 여러 카테고리에 걸친 소비자 니즈·가치관·섭취 맥락 (저속노화, 고단백, 홈술 등)
- brand: 기업·브랜드·유통사·외식체인 이름 (CJ, 파리바게뜨, CU 등)
- 일반어(인기, 출시, 건강, 프리미엄 등) 단독 저장 금지

{{
  "primary_category": "신제품·NPD|소비자·시장|식재료·원료|채널·유통|브랜드·기업|산업·정책",
  "summary": ["핵심 포인트1", "포인트2"],
  "keywords": [
    {{"word": "키워드", "cat": "food_cat|ingredient|trend|brand"}}
  ]
}}"""
        else:
            prompt = f"""Analyze this F&B news article.

Title: {title}
Text: {raw_text[:600]}

JSON only. No explanation.

[Primary category - pick exactly 1]
- 신제품·NPD: New product launch/renewal is the main focus
- 소비자·시장: Consumer trends, market growth, reports
- 식재료·원료: Specific ingredient, functional material, fermentation tech
- 채널·유통: Retail channel strategy (convenience store, delivery, etc.)
- 브랜드·기업: Corporate strategy, M&A, brand positioning
- 산업·정책: Regulation, supply chain, food safety, pricing

[Signal keywords - menu development perspective]
- food_cat: Ready-to-buy complete food/menu (greek yogurt, HMR, omakase)
- ingredient: Raw material inside products (oat, pistachio, collagen, yeast)
- trend: Consumer need/value across categories (high-protein, low-sugar, home dining)
- brand: Company/brand/retailer name (CJ, Starbucks, CU)
- Exclude generic words (popular, launch, health, premium)

{{
  "title_ko": "자연스러운 한국어 제목 번역",
  "primary_category": "신제품·NPD|소비자·시장|식재료·원료|채널·유통|브랜드·기업|산업·정책",
  "summary": ["key point 1", "point 2"],
  "keywords": [
    {{"word": "keyword", "cat": "food_cat|ingredient|trend|brand"}}
  ]
}}"""

        # 최대 3회 재시도 (503 일시적 과부하 대응)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config={"temperature": 0.1, "max_output_tokens": 300}
                )
                raw = response.text.strip().replace("```json","").replace("```","").strip()
                result = _json.loads(raw)
                time.sleep(AI_DELAY)
                return result
            except Exception as e:
                err_str = str(e)
                if '503' in err_str and attempt < 2:
                    print(f"\n    !! 503 일시 과부하, {10*(attempt+1)}초 후 재시도...", end="")
                    time.sleep(10 * (attempt + 1))
                    continue
                print(f"\n    !! Gemini 오류: {e}")
                return {}
        return {}
    except Exception as e:
        print(f"\n    !! Gemini 초기화 오류: {e}")
        return {}

# ─────────────────────────────────────────
# 키워드 추출
# ─────────────────────────────────────────

KO_STOPWORDS = {
    '이','가','은','는','의','를','을','에','에서','로','으로','과','와','도','만',
    '한','하는','하고','하여','해서','하면','되는','되어','있는','없는','같은','많은',
    '더','또','및','등','그','이','저','위한','통해','대한','관련','따른','대해',
    '위해','새로운','이번','지난','올해','최근','현재','국내','해외','글로벌',
}

def extract_keywords(title: str, summary: str) -> list[str]:
    text = title + " " + (summary or "")
    ko = re.findall(r'[가-힣]{2,6}', text)
    en = re.findall(r'[A-Z][A-Za-z]{2,}|[A-Z]{2,}', text)
    freq: dict[str, int] = {}
    for w in ko + en:
        if w not in KO_STOPWORDS and len(w) > 1:
            freq[w] = freq.get(w, 0) + 1
    for w in re.findall(r'[가-힣]{2,6}|[A-Z][A-Za-z]{2,}', title):
        if w in freq:
            freq[w] += 2
    seen: set[str] = set()
    result: list[str] = []
    for word, _ in sorted(freq.items(), key=lambda x: -x[1]):
        if word.lower() not in seen:
            seen.add(word.lower())
            result.append(word)
        if len(result) >= 5:
            break
    return result

# ─────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────

def make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()

def shorten(text, n: int = 300) -> str:
    if isinstance(text, list):
        text = ' '.join(text)
    t = strip_html(str(text))
    return (t[:n].rsplit(" ", 1)[0] + "…") if len(t) > n else t

def parse_date(entry, lang: str = "en") -> str:
    """
    발행일 파싱.
    한국 사이트는 날짜에 시간대 정보가 없어서 feedparser가 KST를 UTC로 착각.
    → lang="ko"이고 원문에 시간대 없으면 KST(UTC+9)로 보정.
    """
    import re
    from email.utils import parsedate_to_datetime

    KST_OFFSET = timedelta(hours=9)

    def raw_has_tz(raw: str) -> bool:
        """원문 날짜 문자열에 시간대 정보가 있는지 확인"""
        return bool(re.search(r'[+\-]\d{2}:?\d{2}|GMT|UTC| Z$', raw.strip()))

    # ① published_parsed / updated_parsed 시도
    for parsed_attr, raw_attr in (
        ("published_parsed", "published"),
        ("updated_parsed",   "updated"),
        ("created_parsed",   "created"),
    ):
        t = getattr(entry, parsed_attr, None)
        if not (t and t[0] > 1990):
            continue
        try:
            dt = datetime(t[0],t[1],t[2],t[3],t[4],t[5], tzinfo=timezone.utc)
            # 한국 소스이고 원문에 시간대 없으면 KST → UTC 보정
            raw = getattr(entry, raw_attr, "") or ""
            if lang == "ko" and raw and not raw_has_tz(raw):
                dt = dt - KST_OFFSET
            return dt.isoformat()
        except Exception:
            pass

    # ② 원문 문자열 직접 파싱
    for attr in ("published", "updated", "created"):
        raw = getattr(entry, attr, None) or entry.get(attr, "")
        if not raw:
            continue
        # RFC 2822 ("Wed, 28 May 2026 09:00:00 +0900")
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        # ISO 8601 ("2026-05-28T14:26:41-04:00")
        try:
            raw_clean = raw.strip().replace("Z", "+00:00")
            return datetime.fromisoformat(raw_clean).astimezone(timezone.utc).isoformat()
        except Exception:
            pass

    # ③ 최후 수단: 수집 시각
    return datetime.now(timezone.utc).isoformat()

def categorize_fallback(title: str, summary: str) -> str:
    """Gemini 분류 실패 시 키워드 기반 fallback."""
    text = (title + " " + summary).lower()
    if any(k in text for k in ["출시", "론칭", "신제품", "리뉴얼", "launch", "new product"]):
        return "신제품·NPD"
    if any(k in text for k in ["트렌드", "리포트", "성장", "조사", "trend", "report", "survey"]):
        return "소비자·시장"
    if any(k in text for k in ["원료", "식재료", "성분", "발효", "ingredient", "ferment"]):
        return "식재료·원료"
    if any(k in text for k in ["편의점", "cu", "gs25", "세븐일레븐", "배달", "유통"]):
        return "채널·유통"
    if any(k in text for k in ["전략", "투자", "m&a", "인수", "브랜드", "기업"]):
        return "브랜드·기업"
    if any(k in text for k in ["규제", "정책", "수급", "안전", "수출", "수입"]):
        return "산업·정책"
    return "브랜드·기업"

def is_cvs(title: str, summary: str) -> bool:
    """편의점 관련 기사 여부."""
    text = (title + " " + summary).lower()
    return any(k.lower() in text for k in CVS_KEYWORDS)

# ─────────────────────────────────────────
# 수집
# ─────────────────────────────────────────

def collect():
    os.makedirs(DATA_DIR, exist_ok=True)
    existing: dict[str, dict] = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, encoding="utf-8") as f:
                for a in json.load(f).get("articles", []):
                    existing[a["id"]] = a
        except Exception as e:
            print(f"  !! 기존 파일 로드 실패: {e}")

    if USE_AI:
        print("  [AI 모드] Gemini Flash — 요약+키워드+번역\n")
    else:
        print("  [일반 모드] GEMINI_API_KEY 미설정 — RSS 원문 사용\n")

    new_total, errors = 0, []

    for src in SOURCES:
        name = src["name"]
        try:
            print(f"  [{name}] ...", end="", flush=True)
            feed = feedparser.parse(src["url"])
            status = getattr(feed, "status", 200)
            if status in (403, 404, 410):
                errors.append(f"{name}: HTTP {status}")
                print(f" HTTP {status}")
                continue
            if not feed.entries:
                errors.append(f"{name}: 빈 피드")
                print(" 빈 피드")
                continue

            added = 0
            for entry in feed.entries[:MAX_PER_FEED]:
                url = entry.get("link", "").strip()
                if not url:
                    continue
                aid = make_id(url)
                if aid in existing:
                    continue

                title    = strip_html(entry.get("title", "")).strip()
                raw_text = shorten(entry.get("summary", entry.get("description", "")))

                # AI 분석 (요약 + 키워드 + 해외 번역)
                ai_result = {}
                if USE_AI and raw_text:
                    ai_result = gemini_analyze(title, raw_text, src["lang"])

                # summary: AI는 리스트, 없으면 RSS 원문 축약
                raw_summary = ai_result.get("summary")
                if isinstance(raw_summary, list):
                    summary = raw_summary  # 불릿 포인트 리스트
                elif isinstance(raw_summary, str) and raw_summary:
                    summary = raw_summary
                else:
                    summary = shorten(raw_text, 150)
                # keywords: AI가 [{word, cat}] 형태로 반환, 없으면 빈 리스트
                raw_kws = ai_result.get("keywords", [])
                if raw_kws and isinstance(raw_kws[0], dict):
                    # 새 형식: [{word, cat}] → word만 추출 (cat은 별도 저장)
                    keywords = [k["word"] for k in raw_kws if isinstance(k, dict) and k.get("word")]
                    kw_cats  = {k["word"]: k.get("cat","") for k in raw_kws if isinstance(k, dict) and k.get("word")}
                elif raw_kws and isinstance(raw_kws[0], str):
                    # 구 형식: 문자열 리스트
                    keywords = raw_kws
                    kw_cats  = {}
                else:
                    keywords = extract_keywords(title, raw_text)
                    kw_cats  = {}

                keywords = keywords[:5]

                # extract_keywords용: summary가 list면 합쳐서 문자열로
                summary_str = ' '.join(summary) if isinstance(summary, list) else (summary or '')

                if src["lang"] != "ko" and ai_result.get("title_ko"):
                    title = ai_result["title_ko"]

                # 기사 카테고리: Gemini 결과 우선, 실패 시 fallback
                primary_cat = ai_result.get("primary_category", "")
                if primary_cat not in VALID_CATEGORIES:
                    primary_cat = categorize_fallback(title, raw_text)
                # 편의점 채널 태그
                cvs_tag = is_cvs(title, raw_text)

                parsed_date = parse_date(entry, lang=src["lang"])

                # 디버그: 소스별 첫 기사 날짜 원문 출력
                if added == 0:
                    raw_pub = getattr(entry, "published", None) or getattr(entry, "updated", "없음")
                    pp      = getattr(entry, "published_parsed", None)
                    print(f"\n      날짜원문: {str(raw_pub)[:60]}")
                    print(f"      결과   : {parsed_date}", end=" ")

                existing[aid] = {
                    "id":         aid,
                    "title":      title,
                    "url":        url,
                    "source":     name,
                    "lang":       src["lang"],
                    "category":   primary_cat,
                    "is_cvs":     cvs_tag,
                    "summary":    summary,
                    "keywords":   keywords,
                    "kw_cats":    kw_cats,
                    "date":       parsed_date,
                }
                added += 1

            new_total += added
            print(f" +{added}건")
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f" 오류 ({e})")

    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    kept = []
    for a in existing.values():
        try:
            dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
            if dt >= cutoff:
                kept.append(a)
        except Exception:
            kept.append(a)
    kept.sort(key=lambda x: x["date"], reverse=True)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(),
                   "total": len(kept), "articles": kept},
                  f, ensure_ascii=False, indent=2)

    print(f"\n>> 완료 - 신규 {new_total}건 / 전체 {len(kept)}건 보관")
    if errors:
        print(f"-- 오류 {len(errors)}건:")
        for e in errors:
            print(f"   {e}")

if __name__ == "__main__":
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"{'='*44}")
    print(f"  새미네뉴스 수집기  [{now}]")
    print(f"{'='*44}")
    collect()
