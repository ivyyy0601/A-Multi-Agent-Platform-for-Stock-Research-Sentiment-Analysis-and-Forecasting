#!/usr/bin/env python3
"""
Arctic Shift Reddit Scraper
抓取指定 subreddit 在指定时间范围内的 posts
"""

import requests
import json
import time
import os

# ─── 配置 ────────────────────────────────────────────────────
SUBREDDITS = [
    "stocks", "investing", "options", "StockMarket", "Equities",
    "ValueInvesting", "StockAnalysis", "InvestmentClub", "RealDayTrading", "Daytrading",
    "swingtrading", "Trading", "Stock_Picks", "TradeIdeas", "AlgoTrading",
    "Quant", "WallStreet", "Finance", "MarketAnalysis", "EconMonitor",
]

AFTER      = "2023-11-06"
BEFORE     = "2025-05-31"
LIMIT      = 100
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reddit_data")

BASE_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
# ─────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

KEEP_FIELDS = {
    "id", "author", "title", "selftext", "score", "url",
    "created_utc", "subreddit", "num_comments", "upvote_ratio",
    "link_flair_text", "permalink", "name",
}


def slim(post: dict) -> dict:
    return {k: v for k, v in post.items() if k in KEEP_FIELDS}


def fetch_posts(subreddit: str, after: str, before: str) -> list[dict]:
    all_posts: list[dict] = []
    params = {
        "subreddit": subreddit,
        "after":     after,
        "before":    before,
        "limit":     LIMIT,
        "sort":      "asc",
    }

    page = 1
    while True:
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  [!] 请求失败 (page {page}): {e}")
            break

        posts = data.get("data", [])
        if not posts:
            break

        all_posts.extend(slim(p) for p in posts)
        print(f"  page {page}: +{len(posts)} posts (total {len(all_posts)})")

        if len(posts) < LIMIT:
            break

        last_ts = posts[-1]["created_utc"]
        params["after"] = str(int(last_ts) + 1)
        page += 1
        time.sleep(0.5)

    return all_posts


def main():
    summary: dict[str, int] = {}

    for sub in SUBREDDITS:
        print(f"\n[{sub}] 抓取 {AFTER} ~ {BEFORE} ...")
        posts = fetch_posts(sub, AFTER, BEFORE)
        summary[sub] = len(posts)

        if posts:
            out_path = os.path.join(OUTPUT_DIR, f"{sub}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(posts, f, ensure_ascii=False, indent=2)
            print(f"  -> 已保存 {len(posts)} 条到 {out_path}")
        else:
            print(f"  -> 无数据")

    print("\n\n=== 抓取汇总 ===")
    total = 0
    for sub, cnt in summary.items():
        print(f"  r/{sub:<20} {cnt:>5} posts")
        total += cnt
    print(f"  {'TOTAL':<22} {total:>5} posts")
    print(f"\n数据保存在: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
