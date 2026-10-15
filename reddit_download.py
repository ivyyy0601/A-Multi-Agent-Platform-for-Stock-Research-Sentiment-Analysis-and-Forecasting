#!/usr/bin/env python3
"""
从 Arctic Shift API 下载 Reddit posts，保存为 JSONL 文件
每个 subreddit 一个文件，中断后可以续跑（跳过已存在的文件）
"""

import json
import os
import time
import requests

AFTER      = "2025-06-01"
BEFORE     = "2026-03-21"
LIMIT      = 100
OUT_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_URL   = "https://arctic-shift.photon-reddit.com/api/posts/search"

SUBREDDITS = [
    "stocks", "investing", "options", "StockMarket", "Equities",
    "ValueInvesting", "StockAnalysis", "InvestmentClub", "RealDayTrading", "Daytrading",
    "swingtrading", "Trading", "Stock_Picks", "TradeIdeas", "AlgoTrading",
    "Quant", "WallStreet", "Finance", "MarketAnalysis", "EconMonitor",
]


def download_subreddit(subreddit: str) -> int:
    out_path = os.path.join(OUT_DIR, f"r_{subreddit}_posts.jsonl")

    # 已存在则跳过
    if os.path.exists(out_path):
        count = sum(1 for _ in open(out_path))
        print(f"  已存在，跳过（{count} 条）")
        return count

    params = {"subreddit": subreddit, "after": AFTER,
              "before": BEFORE, "limit": LIMIT, "sort": "asc"}
    total = 0

    with open(out_path, "w", encoding="utf-8") as f:
        page = 1
        while True:
            try:
                resp = requests.get(BASE_URL, params=params, timeout=30)
                resp.raise_for_status()
                posts = resp.json().get("data", [])
            except Exception as e:
                print(f"  [!] 第{page}页失败: {e}")
                break

            if not posts:
                break

            for p in posts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

            total += len(posts)
            print(f"  page {page}: +{len(posts)} (共 {total})", end="\r")

            if len(posts) < LIMIT:
                break

            params["after"] = str(int(posts[-1]["created_utc"]) + 1)
            page += 1
            time.sleep(0.4)

    print(f"  完成: {total} 条 → {os.path.basename(out_path)}")
    return total


def main():
    summary = {}
    for sub in SUBREDDITS:
        print(f"\n[r/{sub}]")
        count = download_subreddit(sub)
        summary[sub] = count

    print(f"\n{'='*50}")
    grand = 0
    for sub, n in summary.items():
        print(f"  r/{sub:<20} {n:>6} posts")
        grand += n
    print(f"  {'TOTAL':<22} {grand:>6} posts")
    print(f"\n文件保存在: {OUT_DIR}/")


if __name__ == "__main__":
    main()
