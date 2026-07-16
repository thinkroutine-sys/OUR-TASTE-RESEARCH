#!/usr/bin/env python3
# backfill_keyword_daily.py
# 1회성 백필: 지금 news.json에 남아있는 전체 기간을 다시 집계해서
# keyword_daily 테이블에 매체 이름 목록(sources)까지 채워 넣는다.
#
# 주의: KEEP_DAYS(30일) 이전 데이터는 news.json에서 이미 빠져있어서
# 이 스크립트로는 못 채운다. 프로젝트가 KEEP_DAYS보다 오래되면
# 그 이전 기간은 원천적으로 백필 불가.

import json
import collect

with open("data/news.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

print(f"news.json 로드: {len(articles)}건")

dates = sorted({a.get("date", "")[:10] for a in articles if a.get("date")})
if dates:
    print(f"기사 날짜 범위: {dates[0]} ~ {dates[-1]}")

# news.json에 남아있는 전체 기간을 커버하도록 넉넉하게 40일치 재집계
agg = collect.aggregate_keyword_daily(articles, days_back=40)
print(f"재집계된 (날짜,키워드) 조합: {len(agg)}건")

saved = collect.supa_upsert_keyword_daily(agg)
print(f"Supabase 백필 완료: {saved}건 저장/갱신")
