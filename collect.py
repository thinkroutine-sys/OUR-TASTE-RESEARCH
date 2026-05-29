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
GEMINI_API_KEY = ""   # 예: "AIzaSy..."
# aistudio.google.com → Get API Key → Create API key

USE_AI = bool(GEMINI_API_KEY.strip())

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT_FILE     = os.path.join(DATA_DIR, "news.json")
KEEP_DAYS    = 30
MAX_PER_FEED = 30
AI_DELAY     = 0.3   # API 호출 간격(초) — 과호출 방지

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
# 카테고리 기준 (복수 태그 허용)
#
# [신제품]  제품 출시·론칭·리뉴얼 소식
# [트렌드]  시장 분석, 소비자 리포트, 통계, 성장 데이터
# [편의점]  편의점 브랜드 언급 또는 편의점 채널 관련
# [간편식]  HMR·밀키트·즉석식품·냉동식품 관련
# [식재료·원료] 원료·식재료·성분·공법(발효·유기농 등)
# [업계뉴스] 위에 해당 없는 기업 동향·정책·M&A 등
# ─────────────────────────────────────────
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("신제품", [
        "신제품", "출시", "론칭", "신규 출시", "새로 선보", "새로 나온", "리뉴얼", "리패키징",
        "launch", "launches", "new product", "introduces", "unveiled",
        "debut", "debuts", "released", "new launch",
    ]),
    ("트렌드", [
        "트렌드", "성장세", "소비 트렌드", "리포트", "조사 결과", "시장 분석",
        "급증", "소비자 선호", "인기 급상승", "%", "억원", "조원",
        "trend", "report", "survey", "forecast", "consumer insight",
        "market data", "growing demand", "rise of",
    ]),
    ("편의점", [
        "편의점", "CU", "GS25", "세븐일레븐", "이마트24", "미니스톱",
        "convenience store", "CVS",
    ]),
    ("간편식", [
        "간편식", "밀키트", "HMR", "즉석식품", "냉동식품", "레토르트",
        "가정간편식", "즉석조리", "냉동",
        "ready meal", "meal kit", "instant food", "frozen food",
        "heat and eat", "ready-to-eat",
    ]),
    ("식재료·원료", [
        "식재료", "원료", "원산지", "성분", "첨가물", "발효", "유기농",
        "비건", "식물성", "대체단백질", "배양육", "천연",
        "ingredient", "raw material", "organic", "fermented",
        "plant-based", "vegan", "alternative protein", "cultivated meat",
    ]),
]

# ─────────────────────────────────────────
# AI 요약 (Claude Haiku)
# ─────────────────────────────────────────

def gemini_analyze(title: str, raw_text: str, lang: str) -> dict:
    """Gemini Flash: 요약 + 키워드 + 해외 번역"""
    import urllib.request, json as _json
    try:
        if lang == "ko":
            prompt = f"""다음 F&B 뉴스를 분석해줘.

제목: {title}
본문: {raw_text[:600]}

아래 JSON 형식으로만 답해. 다른 말 절대 하지 마.
{{
  "summary": "핵심 내용 2문장 요약 (한국어, 간결하게)",
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""
        else:
            prompt = f"""Analyze this F&B news article.

Title: {title}
Text: {raw_text[:600]}

Reply ONLY in this JSON format, nothing else:
{{
  "title_ko": "제목을 자연스러운 한국어로 번역",
  "summary": "핵심 내용 2문장 요약 (한국어, 간결하게)",
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        body = _json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300}
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = raw.replace("```json","").replace("```","").strip()
        result = _json.loads(raw)
        time.sleep(AI_DELAY)
        return result
    except Exception as e:
        print(f"\n    !! Gemini 오류: {e}")
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

def shorten(text: str, n: int = 300) -> str:
    t = strip_html(text)
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

def categorize(title: str, summary: str, cat_hint) -> list[str]:
    """복수 카테고리 반환. cat_hint 있으면 해당 카테고리 + 키워드 매칭 추가."""
    text = (title + " " + summary).lower()
    matched = []
    for cat, kws in CATEGORY_RULES:
        if any(kw.lower() in text for kw in kws):
            matched.append(cat)
    # cat_hint(편의점 등)는 항상 포함, 중복 제거
    if cat_hint and cat_hint not in matched:
        matched.insert(0, cat_hint)
    if not matched:
        matched = ["업계뉴스"]
    return matched

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

                summary  = ai_result.get("summary") or shorten(raw_text, 150)
                keywords = ai_result.get("keywords") or extract_keywords(title, summary or raw_text)
                if src["lang"] != "ko" and ai_result.get("title_ko"):
                    title = ai_result["title_ko"]

                keywords    = keywords[:5]
                cats        = categorize(title, raw_text, src["cat_hint"])
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
                    "categories": cats,
                    "category":   cats[0],
                    "summary":    summary,
                    "keywords":   keywords,
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
