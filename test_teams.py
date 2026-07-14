#!/usr/bin/env python3
# test_teams.py - Teams 웹훅 연결 테스트
# 실제 뉴스 수집 없이, 더미 기사 2건으로 카드가 채널에 도착하는지만 확인

import collect

dummy_articles = [
    {
        "id": "test-1",
        "title": "[테스트] 발효 감칠맛 소재, 글로벌 식품업계 주목받는 이유",
        "url": "https://our-taste-research.vercel.app",
        "source": "식품음료신문",
        "date": "2026-07-14T07:00:00+00:00",
        "summary": ["천연 발효 조미료 시장이 확대되며 우마미 소재에 대한 관심이 높아지고 있다."],
        "tags": ["연두", "콘텐츠"],
    },
    {
        "id": "test-2",
        "title": "[테스트] 밀키트 시장, 1인 가구 겨냥 프리미엄화 가속",
        "url": "https://our-taste-research.vercel.app",
        "source": "Food Dive",
        "date": "2026-07-14T06:40:00+00:00",
        "summary": "HMR 시장이 단순 편의성을 넘어 프리미엄 라인업으로 재편되는 흐름을 다룬 기사",
        "tags": ["간편식"],
    },
]

articles = dummy_articles
tagged_ids = {a["id"]: a["tags"] for a in dummy_articles}

ok = collect.send_teams_notification(articles, tagged_ids)
print("\n결과:", "성공" if ok else "실패 - 위 로그 확인")
