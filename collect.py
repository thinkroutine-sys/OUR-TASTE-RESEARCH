#!/usr/bin/env python3
# collect.py - 새미네뉴스 수집기 v5
# 의존성: pip install feedparser anthropic

import feedparser
import json
import os
import re
import html
import hashlib
import time
from datetime import datetime, timedelta, timezone

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ─────────────────────────────────────────
# ★ Gemini API 키 설정
# aistudio.google.com → Get API Key → Create API key
# 아래 "" 안에 본인 키 입력 (AIza... 로 시작)
# ─────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# aistudio.google.com → Get API Key → Create API key

USE_AI = bool(GEMINI_API_KEY.strip())

# ─────────────────────────────────────────
# Supabase 설정 (자동 태깅용)
# ─────────────────────────────────────────
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "https://cnfxyqmhtvcuhbjyxjrk.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
BOT_EMAIL         = "ai-bot@woorimat.internal"
BOT_PASSWORD      = "ai-bot@woorimat.internal"
BOT_USER_ID       = "5279089a-ffbd-4b26-8041-902217ba5b9a"
BOT_USER_NAME     = "AI 자동태그"

# ─────────────────────────────────────────
# Teams 알림 설정 (Incoming Webhook, Adaptive Card)
# ─────────────────────────────────────────
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
DASHBOARD_URL     = "https://our-taste-research.vercel.app"

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT_FILE     = os.path.join(DATA_DIR, "news.json")
KEEP_DAYS    = 30
MAX_PER_FEED = 30

# ─────────────────────────────────────────
# 테스트 모드 (빠른 확인용 - Supabase 저장/Teams 알림/news.json 저장 생략)
# ─────────────────────────────────────────
TEST_MODE          = os.environ.get("TEST_MODE", "") == "1"
TEST_SOURCE_LIMIT   = int(os.environ.get("TEST_SOURCE_LIMIT", "3"))
TEST_MAX_PER_FEED   = int(os.environ.get("TEST_MAX_PER_FEED", "3"))
AI_DELAY     = 8.0   # API 호출 간격(초) — 무료 티어 분당 15회 한도 대응
HANKYUNG_FNB_PAGES = 2  # 페이지당 50건. 첫 실행 후 백필 끝나면 1로 낮춰도 됨

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
    {"name": "한국외식신문",    "lang": "ko", "cat_hint": None,
     "url": "http://www.kfoodtimes.com/rss/allArticle.xml"},
    {"name": "식품음료신문",   "lang": "ko", "cat_hint": None,
     "url": "https://www.thinkfood.co.kr/rss/allArticle.xml"},
    {"name": "식품저널",       "lang": "ko", "cat_hint": None,
     "url": "http://www.foodnews.co.kr/rss/allArticle.xml"},
    {"name": "푸드아이콘",     "lang": "ko", "cat_hint": None,
     "url": "https://www.foodicon.co.kr/rss/allArticle.xml"},
    {"name": "리얼푸드",       "lang": "ko", "cat_hint": None,
     "url": "https://www.realfoods.co.kr/rss/allArticle.xml"},
    {"name": "베지로그",       "lang": "ko", "cat_hint": "식재료·원료",
     "url": "https://vegilog.com/feed"},
    {"name": "푸드투데이",     "lang": "ko", "cat_hint": None,
     "url": "https://foodtoday.or.kr/data/rss/news.xml"},
    {"name": "쿡앤셰프",       "lang": "ko", "cat_hint": None,
     "url": "https://www.cooknchefnews.com/news/rss.php"},
    {"name": "비건뉴스",       "lang": "ko", "cat_hint": None, "food_filter": True,
     "url": "https://www.vegannews.co.kr/data/rss/news.xml"},
    # ── 한국경제 (RSS 없음 → 정적 페이지 스크래핑) ───────
    {"name": "한국경제 F&B",  "lang": "ko", "cat_hint": None,
     "type": "scrape", "scraper": "hankyung_fnb"},
    {"name": "농식품정보누리", "lang": "ko", "cat_hint": None,
     "type": "scrape", "scraper": "foodnuri"},
    {"name": "KATI 수출정보", "lang": "ko", "cat_hint": None,
     "type": "scrape", "scraper": "kati"},
    # ── 편의점 (스크래핑: CU·GS25 / Google News RSS: 신제품·세븐일레븐) ─
    {"name": "CU 보도자료",    "lang": "ko", "cat_hint": "편의점",
     "type": "scrape", "scraper": "cu"},
    {"name": "GS25 보도자료",  "lang": "ko", "cat_hint": "편의점",
     "type": "scrape", "scraper": "gs25"},
    {"name": "편의점 신제품",  "lang": "ko", "cat_hint": "편의점",
     "url": "https://news.google.com/rss/search?q=%ED%8E%B8%EC%9D%98%EC%A0%90+%EC%8B%A0%EC%A0%9C%ED%92%88+%EC%B6%9C%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"},
    {"name": "세븐일레븐 소식", "lang": "ko", "cat_hint": "편의점",
     "url": "https://news.google.com/rss/search?q=%EC%84%B8%EB%B8%90%EC%9D%BC%EB%A0%88%EB%B8%90+%EC%8B%A0%EC%A0%9C%ED%92%88&hl=ko&gl=KR&ceid=KR:ko"},
    # ── 해외 ────────────────────────────────────────────
    {"name": "Food Dive",                "lang": "en", "cat_hint": None,
     "url": "https://www.fooddive.com/feeds/news/"},
    {"name": "Nation's Restaurant News", "lang": "en", "cat_hint": None,
     "url": "https://www.nrn.com/rss.xml"},
    {"name": "Eater",                    "lang": "en", "cat_hint": None,
     "url": "https://www.eater.com/rss/index.xml"},
    {"name": "Food Ingredients First",   "lang": "en", "cat_hint": None,
     "url": "https://resource.innovadatabase.com/rss/fifnews.xml"},
    {"name": "Food Navigator",           "lang": "en", "cat_hint": None,
     "type": "scrape", "scraper": "foodnavigator"},
    # ── 일본 ────────────────────────────────────────────
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
# food_filter: True인 소스는 아래 키워드가 제목+본문에 하나도 없으면
# 저장하지 않음 (전체 뉴스를 RSS로 뿌리는 사이트에서 비F&B 기사 제외용)
# ─────────────────────────────────────────
FOOD_FILTER_KEYWORDS = [
    "식품", "푸드", "food", "음식", "메뉴", "레시피", "요리", "맛집",
    "비건", "채식", "대체육", "대체식품", "플렉시테리언",
    "식재료", "농산물", "수산물", "축산", "농식품", "급식", "외식",
    "카페", "레스토랑", "프랜차이즈", "디저트", "베이커리", "제과",
    "커피", "음료", "주류", "소스", "양념", "장류", "발효",
    "hmr", "밀키트", "간편식", "영양", "다이어트", "식단", "미식",
]

def passes_food_filter(src: dict, title: str, raw_text: str) -> bool:
    """food_filter 소스에서 F&B 무관 기사 걸러내기."""
    if not src.get("food_filter"):
        return True
    text = (title + " " + (raw_text or "")).lower()
    return any(k.lower() in text for k in FOOD_FILTER_KEYWORDS)

# ─────────────────────────────────────────
# AI 요약 (Claude Haiku)
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# Supabase 자동 태깅
# ─────────────────────────────────────────

# 브랜드·업무 태그 정의 (Gemini 프롬프트에 그대로 주입)
# key: 태그명, value: 태그를 달 기준
TAG_DEFINITIONS = {
    # ── 브랜드 태그 ──────────────────────────────────────
    "새미네부엌":    "김치양념·요리소스·샤브샤브소스·간편 한식 양념 소스 관련",
    "연두":          "발효 천연조미료·우마미·천연감칠맛 소재 관련",
    "폰타나":        "파스타·수프·올리브오일·이탈리안·유럽식 식문화 관련",
    "티아시아":      "동남아·아시안 소스·커리·태국/베트남 식문화 관련",
    "차오차이":      "중화요리·마라·중국식 소스·중식 트렌드 관련",
    "백년동안":      "식초·발효·전통 발효식품 관련",
    "질러":          "육포·스낵·건조육·간식 트렌드 관련",
    "순작":          "차(茶)·티·허브음료·웰니스 음료 관련",
    "샘표 장류":     "간장·된장·고추장·쌈장 등 장류 전반 관련",
    "샘표 국수":     "국수·면류 트렌드 관련",
    "간편식":        "간편식·HMR·밀키트 시장·트렌드 관련",
    "샘표 기본양념": "맛술·식초·참기름·들기름 등 기본 양념류·오일 관련",
    "샘표 간편·양념":"간편 요리용 양념소스·쿠킹소스 트렌드 관련",
    "샘표 간장":     "간장 특화 기사 (장류 전반보다 좁은 범위, 간장이 핵심 소재일 때)",
    "해외":          "해외(국내 외) F&B 트렌드·시장 동향 전반",
    # ── 업무 태그 ──────────────────────────────────────
    "맛방향물":  "특정 맛·향·풍미 원료·소재가 기사의 핵심일 때",
    "메뉴개발":  "신메뉴·레시피·외식 메뉴 트렌드·메뉴 기획 관련",
    "콘텐츠":    "소비자 인사이트·식문화 트렌드·SNS 식문화 관련",
}

# tag_type 매핑 (Supabase article_tags 컬럼값)
BRAND_TAGS = {"새미네부엌", "연두", "폰타나", "티아시아", "차오차이", "백년동안",
              "질러", "순작", "샘표 장류", "샘표 국수", "간편식", "샘표 기본양념",
              "샘표 간편·양념", "샘표 간장", "해외"}
WORK_TAGS  = {"맛방향물", "메뉴개발", "콘텐츠"}

_supa_token = None  # 봇 로그인 토큰 캐시

def supa_login() -> str | None:
    """봇 계정으로 Supabase 로그인 후 access_token 반환."""
    global _supa_token
    if _supa_token:
        return _supa_token
    if not REQUESTS_AVAILABLE or not SUPABASE_ANON_KEY:
        return None
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": BOT_EMAIL, "password": BOT_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            _supa_token = resp.json().get("access_token")
            return _supa_token
        print(f"\n    !! Supabase 봇 로그인 실패: {resp.status_code}")
    except Exception as e:
        print(f"\n    !! Supabase 로그인 오류: {e}")
    return None

def supa_auto_tag(article_id: str, tags: list[str]) -> int:
    """
    article_tags 테이블에 봇 태그 저장.
    이미 봇이 단 태그는 중복 추가 안 함.
    반환값: 실제 추가된 태그 수
    """
    if not tags or not REQUESTS_AVAILABLE or not SUPABASE_ANON_KEY:
        return 0
    token = supa_login()
    if not token:
        return 0

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates",  # 중복 무시
    }

    # 이미 저장된 봇 태그 조회
    try:
        existing_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/article_tags"
            f"?article_id=eq.{article_id}&user_id=eq.{BOT_USER_ID}&select=tag",
            headers=headers,
            timeout=10,
        )
        existing_tags = {r["tag"] for r in existing_resp.json()} if existing_resp.status_code == 200 else set()
    except Exception:
        existing_tags = set()

    new_tags = [t for t in tags if t not in existing_tags]
    if not new_tags:
        return 0

    rows = [
        {
            "article_id": article_id,
            "tag":        t,
            "tag_type":   "brand" if t in BRAND_TAGS else "work",
            "user_id":    BOT_USER_ID,
            "user_name":  BOT_USER_NAME,
        }
        for t in new_tags
    ]
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/article_tags",
            headers=headers,
            json=rows,
            timeout=10,
        )
        return len(new_tags) if resp.status_code in (200, 201) else 0
    except Exception as e:
        print(f"\n    !! 태그 저장 오류: {e}")
        return 0

def pick_auto_tags(ai_result: dict) -> list:
    """
    Gemini가 기사 내용을 보고 직접 판단한 태그 목록을 반환.
    TAG_DEFINITIONS에 있는 태그만 유효한 것으로 필터링.
    """
    raw = ai_result.get("tags", [])
    return [t for t in raw if isinstance(t, str) and t in TAG_DEFINITIONS]

# ─────────────────────────────────────────
# Teams 알림 (Adaptive Card)
# ─────────────────────────────────────────

# 액센트 바 색상(#E8000D) 1px 레드 픽셀 - 카드 상단에 stretch로 늘려서 표시
_RED_BAR_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

def _fmt_time(date_str: str) -> str:
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%H:%M")
    except Exception:
        return ""

MAX_CARD_BYTES = 24 * 1024  # Teams "채널에 카드 게시" 실전 한도(약 28KB) 대비 여유

def build_teams_card(tagged_articles: list, total: int | None = None,
                      part_no: int = 1, part_total: int = 1) -> dict:
    """
    tagged_articles: [{..기사 필드.., "tags": ["연두","콘텐츠",...]}]
    확정 목업(레드 액센트 바 + 태그 배지 + 요약 + 하단 링크) 그대로 Adaptive Card로 구성.
    total/part_no/part_total: 카드가 여러 장으로 쪼개졌을 때 헤더에 표시할 정보.
    """
    n = total if total is not None else len(tagged_articles)
    header = f"⚡ 오늘 자동 태깅된 기사 ({n}건)"
    if part_total > 1:
        header += f" - {part_no}/{part_total}"

    body = [
        {"type": "Image", "url": _RED_BAR_IMG, "height": "6px", "width": "stretch"},
        {
            "type": "TextBlock",
            "text": header,
            "weight": "Bolder",
            "size": "Medium",
            "spacing": "Medium",
        },
    ]

    for i, a in enumerate(tagged_articles):
        summary = a.get("summary", "")
        if isinstance(summary, list):
            summary = " ".join(summary)
        summary = (summary or "").strip()
        if len(summary) > 80:
            summary = summary[:80] + "..."

        body.append({
            "type": "Container",
            "spacing": "Medium",
            "separator": i > 0,
            "items": [
                {"type": "TextBlock", "text": f"[{a.get('title','')}]({a.get('url','')})",
                 "weight": "Bolder", "size": "Small", "wrap": True},
                {"type": "TextBlock", "text": summary, "size": "Small",
                 "isSubtle": True, "wrap": True},
            ],
        })

    body.append({
        "type": "TextBlock",
        "text": f"[대시보드에서 전체 보기 →]({DASHBOARD_URL})",
        "horizontalAlignment": "Right",
        "color": "Attention",
        "weight": "Bolder",
        "spacing": "Medium",
    })

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": body,
            },
        }],
    }

def _card_size(articles_chunk: list, total: int) -> int:
    """해당 기사 묶음으로 카드를 만들었을 때 UTF-8 바이트 크기."""
    card = build_teams_card(articles_chunk, total=total, part_no=1, part_total=1)
    return len(json.dumps(card, ensure_ascii=False).encode("utf-8"))

def build_teams_cards(tagged_articles: list) -> list:
    """
    기사 수 제한은 없음 - 대신 카드 하나가 Teams 게시 한도(MAX_CARD_BYTES)를
    넘지 않도록 여러 장으로 자동 분할. 반환: [card_payload, ...]
    """
    total = len(tagged_articles)
    if total == 0:
        return []

    chunks: list[list] = []
    cur: list = []
    for a in tagged_articles:
        trial = cur + [a]
        if _card_size(trial, total) > MAX_CARD_BYTES and cur:
            chunks.append(cur)
            cur = [a]
        else:
            cur = trial
    if cur:
        chunks.append(cur)

    part_total = len(chunks)
    return [
        build_teams_card(chunk, total=total, part_no=i, part_total=part_total)
        for i, chunk in enumerate(chunks, start=1)
    ]

def _article_signal_score(article: dict, keyword_scores: dict) -> int:
    """
    기사에 달린 키워드들의 최근 시그널 점수(빈도×매체수) 중 최댓값.
    날짜 매칭 없이 키워드 자체의 점수로 비교 (날짜 필드가 부정확한 기사 섞여도 안전).
    """
    kws = article.get("keywords", []) or []
    if not kws:
        return 0
    return max((keyword_scores.get(kw, 0) for kw in kws), default=0)

def send_teams_notification(articles: list, tagged_ids: dict, kw_agg: dict | None = None) -> bool:
    """
    articles   : collect() 실행 중 누적된 전체 기사 dict 리스트 (existing.values())
    tagged_ids : {article_id: [태그명, ...]} - 이번 실행에서 새로 자동 태깅된 기사만
    태그가 하나라도 붙은 기사는 개수 제한 없이 전부 전송하되, Teams 게시 한도를
    넘기지 않도록 여러 장의 카드로 나눠서 순차 전송.
    """
    if not TEAMS_WEBHOOK_URL:
        print("\n  [Teams] TEAMS_WEBHOOK_URL 미설정 — 알림 스킵")
        return False
    if not REQUESTS_AVAILABLE:
        print("\n  [Teams] requests 미설치 — 알림 스킵")
        return False
    if not tagged_ids:
        print("\n  [Teams] 오늘 자동 태깅된 기사 없음 — 알림 스킵")
        return False

    by_id = {a["id"]: a for a in articles}
    tagged_articles = []
    for aid, tags in tagged_ids.items():
        a = by_id.get(aid)
        if not a:
            continue
        tagged_articles.append({**a, "tags": tags})
    # 누적(3일치 합산)이 아니라 '오늘' 하루치 시그널 점수만 사용
    # → 매일 꾸준히 나오는 키워드가 누적치로 계속 1등을 차지하는 걸 방지
    today_str = datetime.now(timezone.utc).date().isoformat()
    keyword_scores = {
        kw: v["count"] * len(v["sources"])
        for (date_str, kw), v in (kw_agg or {}).items()
        if date_str == today_str
    }

    tagged_articles.sort(
        key=lambda a: (_article_signal_score(a, keyword_scores), a.get("date", "")),
        reverse=True,
    )

    MAX_ARTICLES_PER_RUN = 10
    if len(tagged_articles) > MAX_ARTICLES_PER_RUN:
        print(f"\n  [Teams] 태깅 {len(tagged_articles)}건 중 시그널 점수 상위 {MAX_ARTICLES_PER_RUN}건만 전송")
        tagged_articles = tagged_articles[:MAX_ARTICLES_PER_RUN]

    if not tagged_articles:
        print("\n  [Teams] 알림 대상 기사 매칭 실패 — 알림 스킵")
        return False

    cards = build_teams_cards(tagged_articles)
    ok_count = 0
    for i, card in enumerate(cards, start=1):
        try:
            resp = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=15)
            if resp.status_code in (200, 202):
                ok_count += 1
                print(f"\n  [Teams] 카드 {i}/{len(cards)} 전송 완료")
            else:
                print(f"\n  [Teams] 카드 {i}/{len(cards)} 전송 실패: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"\n  [Teams] 카드 {i}/{len(cards)} 전송 오류: {e}")

    print(f"\n  [Teams] 총 {len(tagged_articles)}건, 카드 {ok_count}/{len(cards)}장 전송 완료")
    return ok_count == len(cards)

# ─────────────────────────────────────────
# 시그널 키워드 일별 집계 (keyword_daily 테이블)
# ─────────────────────────────────────────

KEYWORD_AGG_DAYS_BACK = 3  # 늦게 들어오는 기사 대비, 최근 N일치를 매번 다시 집계해서 upsert

def aggregate_keyword_daily(articles: list, days_back: int = KEYWORD_AGG_DAYS_BACK) -> dict:
    """
    최근 days_back일치 기사에서 키워드를 (날짜, 키워드) 단위로 집계.
    score = frequency(빈도) × source_count(매체수) — 시그널 탭과 동일 공식.
    반환: {(date_str, keyword): {"cat":.., "count":.., "sources": set()}}
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()
    by_day_kw: dict = {}
    for a in articles:
        d = a.get("date", "")
        if len(d) < 10:
            continue
        try:
            art_date = datetime.fromisoformat(d.replace("Z", "+00:00")).date()
        except Exception:
            continue
        if art_date < cutoff_date:
            continue
        date_str = art_date.isoformat()
        kw_cats = a.get("kw_cats", {}) or {}
        for kw in a.get("keywords", []) or []:
            key = (date_str, kw)
            entry = by_day_kw.setdefault(key, {"cat": kw_cats.get(kw, ""), "count": 0, "sources": set()})
            entry["count"] += 1
            entry["sources"].add(a.get("source", ""))
    return by_day_kw

def supa_upsert_keyword_daily(agg: dict) -> int:
    """keyword_daily 테이블에 배치 upsert (date+keyword 충돌 시 덮어쓰기)."""
    if not agg or not REQUESTS_AVAILABLE or not SUPABASE_ANON_KEY:
        return 0
    token = supa_login()
    if not token:
        return 0

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    rows = []
    for (date_str, kw), v in agg.items():
        freq = v["count"]
        src_cnt = len(v["sources"])
        rows.append({
            "date": date_str,
            "keyword": kw,
            "cat": v["cat"],
            "frequency": freq,
            "source_count": src_cnt,
            "score": freq * src_cnt,
            "sources": sorted(v["sources"]),  # 매체 이름 목록 (기간별 재집계용)
        })

    saved = 0
    for i in range(0, len(rows), 200):
        batch = rows[i:i + 200]
        try:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/keyword_daily?on_conflict=date,keyword",
                headers=headers,
                json=batch,
                timeout=15,
            )
            if resp.status_code in (200, 201, 204):
                saved += len(batch)
            else:
                print(f"\n    !! keyword_daily 저장 실패: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"\n    !! keyword_daily 저장 오류: {e}")
    return saved


def gemini_analyze(title: str, raw_text: str, lang: str) -> dict:
    """Gemini Flash: 요약 + 키워드 + 해외 번역 + 자동 태그"""
    import json as _json
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 태그 정의 문자열 생성 (프롬프트에 주입)
        tag_def_str = "\n".join(
            f"- {tag}: {desc}" for tag, desc in TAG_DEFINITIONS.items()
        )

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

[자동 태그 - 아래 목록에서 해당하는 것만 골라라. 없으면 빈 배열.]
{tag_def_str}

{{
  "primary_category": "신제품·NPD|소비자·시장|식재료·원료|채널·유통|브랜드·기업|산업·정책",
  "summary": ["핵심 포인트1", "포인트2"],
  "keywords": [
    {{"word": "키워드", "cat": "food_cat|ingredient|trend|brand"}}
  ],
  "tags": ["해당 태그명1", "해당 태그명2"]
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

[Auto tags - pick only matching ones from the list below. Empty array if none match.]
{tag_def_str}

{{
  "title_ko": "자연스러운 한국어 제목 번역",
  "primary_category": "신제품·NPD|소비자·시장|식재료·원료|채널·유통|브랜드·기업|산업·정책",
  "summary": ["key point 1", "point 2"],
  "keywords": [
    {{"word": "keyword", "cat": "food_cat|ingredient|trend|brand"}}
  ],
  "tags": ["태그명1", "태그명2"]
}}"""

        # 최대 3회 재시도 (503 일시적 과부하 대응)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config={"temperature": 0.1, "max_output_tokens": 500}
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

# fallback 키워드 추출 시 단어 끝에 붙은 조사 제거용 (형태소 분석기 없이 근사치 처리)
_TRAILING_JOSA = (
    '이다', '이며', '에서', '으로', '까지', '부터', '한테', '에게',
    '이', '가', '은', '는', '을', '를', '의', '에', '로', '과', '와',
    '도', '만', '서', '나', '야', '랑', '께',
)

def _strip_josa(word: str) -> str:
    """단어 끝의 조사를 제거. 2글자 미만이 되면 원래 단어 유지."""
    for suf in _TRAILING_JOSA:
        if word.endswith(suf) and len(word) - len(suf) >= 2:
            return word[: -len(suf)]
    return word

def extract_keywords(title: str, summary: str) -> list[str]:
    text = title + " " + (summary or "")
    ko = [_strip_josa(w) for w in re.findall(r'[가-힣]{2,6}', text)]
    en = re.findall(r'[A-Z][A-Za-z]{2,}|[A-Z]{2,}', text)
    freq: dict[str, int] = {}
    for w in ko + en:
        if w not in KO_STOPWORDS and len(w) > 1:
            freq[w] = freq.get(w, 0) + 1
    for w in [_strip_josa(w) for w in re.findall(r'[가-힣]{2,6}', title)] + re.findall(r'[A-Z][A-Za-z]{2,}', title):
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
# 월별 아카이브 (news.json 30일 컷과 무관하게 매일 누적 저장)
# ─────────────────────────────────────────

def update_monthly_archives(articles: list) -> None:
    """
    기사를 발행월(date 필드 기준) 아카이브 파일에 매일 누적 병합.
    news.json이 30일 지난 기사를 걸러내기 '전에' 호출해야
    말일 스냅샷 방식(archive.yml 구버전)의 소실 문제가 생기지 않음.
    파일: data/archive/{YYYY}/news_{YYYY}_{MM}.json
    """
    by_month: dict = {}
    for a in articles:
        d = a.get("date", "")
        if len(d) < 7:
            continue
        month_key = d[:7]  # "YYYY-MM"
        by_month.setdefault(month_key, {})[a["id"]] = a

    for month_key, arts in by_month.items():
        year, month = month_key.split("-")
        arch_dir = os.path.join(DATA_DIR, "archive", year)
        os.makedirs(arch_dir, exist_ok=True)
        arch_file = os.path.join(arch_dir, f"news_{year}_{month}.json")

        existing_arch: dict = {}
        if os.path.exists(arch_file):
            try:
                with open(arch_file, encoding="utf-8") as f:
                    for a in json.load(f).get("articles", []):
                        existing_arch[a["id"]] = a
            except Exception as e:
                print(f"\n  !! 아카이브 로드 실패 ({arch_file}): {e}")

        existing_arch.update(arts)  # 신규/갱신분 병합 (기존 자료 유실 없음)

        merged = sorted(existing_arch.values(), key=lambda x: x.get("date", ""), reverse=True)
        with open(arch_file, "w", encoding="utf-8") as f:
            json.dump({"updated": datetime.now(timezone.utc).isoformat(),
                       "total": len(merged), "articles": merged},
                      f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────
# 한국경제 F&B (RSS 없음 → 정적 페이지 스크래핑)
# ─────────────────────────────────────────

class ScrapedEntry(dict):
    """feedparser 엔트리와 동일하게 .get()과 속성 접근(entry.title)을 모두 지원."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

def scrape_hankyung_fnb(pages: int = 1) -> list:
    """
    https://www.hankyung.com/distribution/fnb 정적 HTML 스크래핑.
    robots.txt 확인 결과 일반 봇(User-agent: *)에는 차단 없음 (SEO 봇만 차단).
    구조: <a href="/article/{id}"><h2/h3 class="news-tit">제목</h2/h3></a> ... <p class="txt-date">날짜</p>
    """
    if not REQUESTS_AVAILABLE:
        return []

    base = "https://www.hankyung.com/distribution/fnb"
    headers = {"User-Agent": feedparser.USER_AGENT}
    # F&B 목록은 <ul class="news-list">...</ul> 안에만 있음.
    # 컨테이너 밖(페이지 하단 "관련뉴스/인기뉴스" 위젯)에도 /article/ 링크가 있어서
    # 범위를 안 좁히면 F&B와 무관한 기사(연예/증시 등)까지 같이 잡힘.
    container_rx = re.compile(r'<ul[^>]*class="news-list"[^>]*>(.*?)</ul>', re.S | re.I)
    item_rx = re.compile(
        r'<a[^>]+href="(?P<href>(?:https?://www\.hankyung\.com)?/article/\d{4,}[^"]*)"[^>]*>(?P<inner>.*?)</a>',
        re.S | re.I,
    )
    date_rx = re.compile(r'(20\d{2}\.\d{1,2}\.\d{1,2}(?:\s+\d{1,2}:\d{2})?)')

    results, seen = [], set()
    for page in range(1, pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                break
            html = resp.text
        except Exception:
            break

        cm = container_rx.search(html)
        if not cm:
            continue
        html = cm.group(1)  # F&B 목록 컨테이너 내부로 검색 범위 제한

        for m in item_rx.finditer(html):
            href = m.group("href")
            if href.startswith("/"):
                href = "https://www.hankyung.com" + href
            if href in seen:
                continue

            title = re.sub(r"<[^>]+>", " ", m.group("inner"))
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            seen.add(href)

            # 같은 블록 근처에서 날짜 텍스트 탐색
            tail = html[m.end():m.end() + 300]
            dm = date_rx.search(tail)
            raw_date = dm.group(1) if dm else ""
            tstruct = None
            if raw_date:
                try:
                    fmt = "%Y.%m.%d %H:%M" if ":" in raw_date else "%Y.%m.%d"
                    tstruct = time.strptime(raw_date, fmt)
                except Exception:
                    tstruct = None

            results.append(ScrapedEntry({
                "title": title,
                "link": href,
                "summary": "",
                "published": raw_date,
                "published_parsed": tstruct,
            }))

    return results

def scrape_foodnuri(pages: int = 1) -> list:
    """
    농식품정보누리 - 농식품 뉴스 게시판(B0000277) 스크래핑.
    https://www.foodnuri.go.kr/portal/bbs/B0000277/list.do?menuNo=300049&pageIndex=N
    구조: <li class="col"><dl><dt><a href=".../view.do?nttId={id}...">제목</a></dt>
                              <dd><a ...><span class="txt">요약문</span></a>
                                  <div class="data_info_box">...<span class="date">...날짜...</span>
    """
    if not REQUESTS_AVAILABLE:
        return []

    base = "https://www.foodnuri.go.kr/portal/bbs/B0000277/list.do?menuNo=300049"
    headers = {"User-Agent": feedparser.USER_AGENT}
    item_rx = re.compile(
        r'<li class="col">.*?<dt>\s*<a href="(?P<href>[^"]*nttId=\d+[^"]*)">\s*(?P<title>.*?)\s*</a>\s*</dt>'
        r'(?P<rest>.*?)(?=<li class="col">|$)',
        re.S | re.I,
    )
    date_rx = re.compile(r'<span class="date">[^<]*<span[^>]*>[^<]*</span>\s*(\d{4}-\d{2}-\d{2})', re.S)
    summary_rx = re.compile(r'<span class="txt">\s*(.*?)\s*</span>', re.S)

    results, seen = [], set()
    for page in range(1, pages + 1):
        url = f"{base}&pageIndex={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                break
            html = resp.text
        except Exception:
            break

        for m in item_rx.finditer(html):
            href = m.group("href")
            if href.startswith("/"):
                href = "https://www.foodnuri.go.kr" + href
            if href in seen:
                continue
            seen.add(href)

            title = re.sub(r"\s+", " ", m.group("title")).strip()
            if not title:
                continue

            block = m.group("rest")
            dm = date_rx.search(block)
            raw_date = dm.group(1) if dm else ""
            tstruct = None
            if raw_date:
                try:
                    tstruct = time.strptime(raw_date, "%Y-%m-%d")
                except Exception:
                    tstruct = None

            sm = summary_rx.search(block)
            summary = re.sub(r"\s+", " ", sm.group(1)).strip() if sm else ""

            results.append(ScrapedEntry({
                "title": title,
                "link": href,
                "summary": summary,
                "published": raw_date,
                "published_parsed": tstruct,
            }))

    return results

def scrape_kati(pages: int = 1) -> list:
    """
    KATI 농식품수출정보 - 해외시장동향 게시판 스크래핑.
    https://www.kati.net/board/exportNewsList.do?menu_dept2=35&menu_dept3=71&page=N
    구조: <li><a href="./exportNewsView.do?board_seq={id}...">
              <span class="fs-15 ff-ngb">제목</span>
              <span class="option-area"><span><em>등록일</em>날짜</span>...
              </a>
              <span class="board-cont fs-13">요약문</span>
    """
    if not REQUESTS_AVAILABLE:
        return []

    base = "https://www.kati.net/board/exportNewsList.do?menu_dept2=35&menu_dept3=71"
    headers = {"User-Agent": feedparser.USER_AGENT}
    item_rx = re.compile(
        r'<a href="(?P<href>\./exportNewsView\.do\?board_seq=\d+[^"]*)">'
        r'(?P<inner>.*?)</a>\s*(?:<span class="board-cont[^"]*">(?P<summary>.*?)</span>)?',
        re.S | re.I,
    )
    title_rx = re.compile(r'<span class="fs-15 ff-ngb">\s*(.*?)\s*</span>', re.S)
    date_rx = re.compile(r'<em>등록일</em>\s*(\d{4}-\d{2}-\d{2})')

    results, seen = [], set()
    for page in range(1, pages + 1):
        url = f"{base}&page={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                break
            html = resp.text
        except Exception:
            break

        for m in item_rx.finditer(html):
            href_path = m.group("href").lstrip(".")
            href = "https://www.kati.net/board" + href_path
            if href in seen:
                continue
            seen.add(href)

            inner = m.group("inner")
            tm = title_rx.search(inner)
            title = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else ""
            if not title:
                continue

            dm = date_rx.search(inner)
            raw_date = dm.group(1) if dm else ""
            tstruct = None
            if raw_date:
                try:
                    tstruct = time.strptime(raw_date, "%Y-%m-%d")
                except Exception:
                    tstruct = None

            summary = ""
            if m.group("summary"):
                summary = re.sub(r"\s+", " ", strip_html(m.group("summary"))).strip()

            results.append(ScrapedEntry({
                "title": title,
                "link": href,
                "summary": summary,
                "published": raw_date,
                "published_parsed": tstruct,
            }))

    return results

def scrape_foodnavigator() -> list:
    """
    Food Navigator - 뉴스 사이트맵 XML 파싱.
    https://www.foodnavigator.com/arc/outboundfeeds/news-sitemap/
    RSS 미제공, 사이트맵(XML)에 제목·날짜·URL 포함.
    feedparser는 클라우드 IP 403 차단 → requests로 직접 파싱.
    """
    if not REQUESTS_AVAILABLE:
        return []

    url = "https://www.foodnavigator.com/arc/outboundfeeds/news-sitemap/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []
        xml = resp.text
    except Exception:
        return []

    url_block_rx = re.compile(r'<url>(.*?)</url>', re.S)
    loc_rx       = re.compile(r'<loc>(.*?)</loc>', re.S)
    title_rx     = re.compile(r'<news:title>(.*?)</news:title>', re.S)
    date_rx      = re.compile(r'<news:publication_date>(.*?)</news:publication_date>', re.S)
    cdata_rx     = re.compile(r'^<!\[CDATA\[(.*)\]\]>$', re.S)

    def _clean_title(raw: str) -> str:
        raw = raw.strip()
        m = cdata_rx.match(raw)
        if m:
            raw = m.group(1).strip()
        return html.unescape(raw).strip()

    results = []
    for block in url_block_rx.findall(xml):
        loc_m = loc_rx.search(block)
        if not loc_m:
            continue
        link = loc_m.group(1).strip()

        title_m = title_rx.search(block)
        title = _clean_title(title_m.group(1)) if title_m else ""
        if not title:
            continue

        date_m = date_rx.search(block)
        raw_date = date_m.group(1).strip() if date_m else ""
        tstruct = None
        if raw_date:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                try:
                    tstruct = time.strptime(raw_date[:19], fmt[:len(fmt)])
                    break
                except Exception:
                    continue

        results.append(ScrapedEntry({
            "title": title,
            "link": link,
            "summary": "",
            "published": raw_date,
            "published_parsed": tstruct,
        }))

    return results

def scrape_gs25(page_size: int = 10) -> list:
    """
    GS25(GS리테일) 보도자료 - JSON API.
    POST http://www.gsretail.com/board/boardList (modelName=corpNews)
    응답이 이중 인코딩(JSON 문자열)으로 오는 경우가 있어 필요 시 한 번 더 디코딩.
    상세 링크: .../news-report-view?pageNum=1&articleCode={articleCode}&newsCategory=ALL
    robots.txt에 Crawl-delay: 10초 명시 — 하루 1회 수집이라 자동으로 준수됨.
    """
    if not REQUESTS_AVAILABLE:
        return []

    url = "http://www.gsretail.com/board/boardList"
    headers = {"User-Agent": feedparser.USER_AGENT, "X-Requested-With": "XMLHttpRequest"}
    form = {"pageNum": "1", "pageSize": str(page_size), "modelName": "corpNews",
            "searchType": "", "searchWord": ""}

    try:
        resp = requests.post(url, data=form, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, str):
            data = json.loads(data)
    except Exception:
        return []

    items = data.get("results", []) if isinstance(data, dict) else []
    results = []
    for it in items:
        title = (it.get("subject") or "").strip()
        article_code = it.get("articleCode") or ""
        if not title or not article_code:
            continue
        link = ("http://www.gsretail.com/gsretail/ko/media/news-report-view"
                f"?pageNum=1&articleCode={article_code}&newsCategory=ALL")

        raw_date = (it.get("regiday") or "").strip()
        tstruct = None
        if raw_date:
            try:
                tstruct = time.strptime(raw_date, "%b %d, %Y %I:%M:%S %p")
            except Exception:
                tstruct = None

        results.append(ScrapedEntry({
            "title": title,
            "link": link,
            "summary": (it.get("summMemo") or "").strip(),
            "published": raw_date,
            "published_parsed": tstruct,
        }))

    return results

def scrape_cu(page_more: int = 10) -> list:
    """
    CU(BGF리테일) 보도자료.
    목록: POST /api/bgf-retail/press-release/ (id, title — 날짜는 없음)
    상세: GET /press/view/?id={id} (정적 HTML, 날짜 포함) — 항목당 추가 요청 1회 발생.
    """
    if not REQUESTS_AVAILABLE:
        return []

    headers = {"User-Agent": feedparser.USER_AGENT}
    list_url = "https://www.bgfretail.com/api/bgf-retail/press-release/"
    form = {"pageOffset": "0", "pageMore": str(page_more), "searchWord": "", "searchType": "0"}

    try:
        resp = requests.post(list_url, data=form, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    items = data.get("list", []) if isinstance(data, dict) else []
    date_rx = re.compile(r'(20\d{2}\.\d{1,2}\.\d{1,2})')

    results = []
    for it in items:
        cid = it.get("id")
        title = (it.get("title") or "").strip()
        if not cid or not title:
            continue
        link = f"https://www.bgfretail.com/press/view/?id={cid}"

        raw_date, tstruct = "", None
        try:
            dresp = requests.get(link, headers=headers, timeout=20)
            if dresp.status_code == 200:
                dm = date_rx.search(dresp.text)
                if dm:
                    raw_date = dm.group(1)
                    try:
                        tstruct = time.strptime(raw_date, "%Y.%m.%d")
                    except Exception:
                        tstruct = None
        except Exception:
            pass

        results.append(ScrapedEntry({
            "title": title,
            "link": link,
            "summary": "",
            "published": raw_date,
            "published_parsed": tstruct,
        }))

    return results

# 소스 src["scraper"] 값 → 실제 함수 매핑 (인자 없이 호출, 페이지수 등은 함수 내부 기본값 사용)
SCRAPERS = {
    "hankyung_fnb":  lambda: scrape_hankyung_fnb(pages=HANKYUNG_FNB_PAGES),
    "foodnuri":      lambda: scrape_foodnuri(pages=1),
    "kati":          lambda: scrape_kati(pages=1),
    "cu":            lambda: scrape_cu(page_more=10),
    "gs25":          lambda: scrape_gs25(page_size=10),
    "foodnavigator": lambda: scrape_foodnavigator(),
}

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

    # Supabase 봇 로그인 테스트
    if SUPABASE_ANON_KEY:
        token = supa_login()
        if token:
            print("  [Supabase] 봇 로그인 성공 ✓\n")
        else:
            print("  [Supabase] 봇 로그인 실패 — 자동 태깅 비활성\n")
    else:
        print("  [Supabase] SUPABASE_ANON_KEY 미설정 — 자동 태깅 비활성\n")

    new_total, errors = 0, []
    tagged_this_run: dict[str, list] = {}  # {article_id: [태그명,...]} - 이번 실행에서 새로 태깅된 기사

    sources_to_run = SOURCES[:TEST_SOURCE_LIMIT] if TEST_MODE else SOURCES
    per_feed_limit = TEST_MAX_PER_FEED if TEST_MODE else MAX_PER_FEED
    if TEST_MODE:
        print(f"  [TEST MODE] 소스 {len(sources_to_run)}개 · 소스당 최대 {per_feed_limit}건만 처리")
        print(f"  [TEST MODE] Supabase 저장 / Teams 알림 / news.json 저장 생략\n")

    for src in sources_to_run:
        name = src["name"]
        try:
            print(f"  [{name}] ...", end="", flush=True)

            if src.get("type") == "scrape":
                if not REQUESTS_AVAILABLE:
                    errors.append(f"{name}: requests 미설치")
                    print(" requests 미설치 (pip install requests)")
                    continue
                scraper_fn = SCRAPERS.get(src.get("scraper"))
                entries = scraper_fn() if scraper_fn else []
                if not entries:
                    errors.append(f"{name}: 스크래핑 결과 없음")
                    print(" 결과 없음")
                    continue
            else:
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
                entries = feed.entries

            added = 0
            for entry in entries[:per_feed_limit]:
                url = entry.get("link", "").strip()
                if not url:
                    continue
                aid = make_id(url)
                if aid in existing:
                    continue

                title    = strip_html(entry.get("title", "")).strip()
                raw_text = shorten(entry.get("summary", entry.get("description", "")))

                # food_filter 소스: F&B 무관 기사는 저장하지 않고 스킵
                if not passes_food_filter(src, title, raw_text):
                    continue

                # AI 분석 (요약 + 키워드 + 해외 번역)
                # 스크래핑 소스는 본문(raw_text)이 없으므로 제목이라도 넘겨서 분석
                ai_text = raw_text or title
                ai_result = {}
                if USE_AI and ai_text:
                    ai_result = gemini_analyze(title, ai_text, src["lang"])

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

                # 자동 태깅: 기사 내용 기반으로 Gemini가 판단한 태그를 봇으로 저장
                auto_tags = pick_auto_tags(ai_result)
                if auto_tags:
                    if TEST_MODE:
                        print(f"\n    >> [TEST] 자동태그 판정: {auto_tags} (저장 생략)")
                    else:
                        saved = supa_auto_tag(aid, auto_tags)
                        if saved > 0:
                            tagged_this_run[aid] = auto_tags
                        print(f"\n    >> 자동태그 저장: {auto_tags} → {saved}건")
                elif USE_AI and ai_result:
                    # Gemini 응답은 있는데 태그가 없는 경우 (디버그용)
                    raw_tags = ai_result.get("tags", "없음")
                    if raw_tags:
                        print(f"\n    >> 태그 필터 후 0건 (원본: {raw_tags})")

                added += 1

            new_total += added
            print(f" +{added}건")
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f" 오류 ({e})")

    # news.json 30일 컷 적용 '전에' 현재 살아있는 전체 기사를 월별 아카이브에 먼저 반영
    # (이렇게 해야 30일 창에서 빠지기 전에 아카이브에 이미 담겨있어 소실되지 않음)
    update_monthly_archives(list(existing.values()))

    if TEST_MODE:
        print(f"\n>> [TEST MODE] 완료 - 신규 발견 {new_total}건 (실제 저장/알림 없음)")
        if errors:
            print(f"-- 오류 {len(errors)}건:")
            for e in errors:
                print(f"   {e}")
        return

    # 시그널 키워드 일별 집계 → Supabase keyword_daily 테이블에 upsert (키워드 추이용)
    kw_agg = aggregate_keyword_daily(list(existing.values()))
    kw_saved = supa_upsert_keyword_daily(kw_agg)
    if kw_agg:
        print(f"\n  [Supabase] keyword_daily 갱신: {len(kw_agg)}건 (저장 {kw_saved}건)")

    # 오늘 자동 태깅된 기사 전체를 Teams로 전송 (시그널 점수 상위 10건, 수집 직후 1회)
    send_teams_notification(list(existing.values()), tagged_this_run, kw_agg)

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
