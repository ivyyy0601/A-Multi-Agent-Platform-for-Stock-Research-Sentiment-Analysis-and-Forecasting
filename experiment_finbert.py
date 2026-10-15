#!/usr/bin/env python3
"""
实验：用 FinBERT 本地跑情感分析
对比我手动判断的结果，看准不准
"""

import json
import os
from collections import defaultdict
from transformers import pipeline

# ─── Ticker 关键词（改严版）────────────────────────────────────
# 只用明确的公司名/ticker符号，去掉宽泛词（gpu、meta、google动词）
TICKER_KEYWORDS = {
    "AAPL":  ["$aapl", "apple inc", "apple stock", "apple share", "tim cook", "iphone", "ipad", "macbook", "apple watch"],
    "TSLA":  ["$tsla", "tesla", "elon musk", "cybertruck", "model 3", "model y", "model s"],
    "NVDA":  ["$nvda", "nvidia", "jensen huang", "blackwell", "h100", "h200", "rubin gpu", "nvda"],
    "MSFT":  ["$msft", "microsoft", "satya nadella", "azure", "windows"],
    "GOOGL": ["$googl", "$goog", "alphabet", "google stock", "google share", "google stitch", "waymo", "deepmind"],
    "AMZN":  ["$amzn", "amazon stock", "amazon share", "andy jassy", "aws", "amazon web"],
    "META":  ["$meta", "meta platforms", "facebook stock", "zuckerberg", "instagram", "meta stock"],
    "AMD":   ["$amd", "amd stock", "lisa su", "radeon", "ryzen", "epyc"],
}

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def collect_candidates():
    candidates = []
    for fname in os.listdir(DATA_DIR):
        if not fname.endswith(".json"):
            continue
        posts = json.load(open(os.path.join(DATA_DIR, fname)))
        for p in posts:
            selftext = p.get("selftext", "")
            if selftext in ("[removed]", "[deleted]", ""):
                continue
            if p.get("score", 0) < 2:
                continue
            text = p["title"] + " " + selftext
            if len(text) < 50:
                continue

            text_lower = text.lower()
            for ticker, kws in TICKER_KEYWORDS.items():
                if any(k in text_lower for k in kws):
                    candidates.append({
                        "ticker":    ticker,
                        "title":     p["title"],
                        "selftext":  selftext[:400],
                        "score":     p["score"],
                        "subreddit": p["subreddit"],
                    })
    return candidates


def main():
    print("加载 FinBERT 模型（首次运行会下载约 500MB）...")
    finbert = pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        device=-1,           # CPU
        truncation=True,
        max_length=512,
    )
    print("模型加载完成\n")

    candidates = collect_candidates()
    print(f"改严关键词后候选: {len(candidates)} 对\n")

    by_ticker = defaultdict(list)
    for c in candidates:
        by_ticker[c["ticker"]].append(c)

    label_map = {"positive": "正面 ▲", "negative": "负面 ▼", "neutral": "中立 ─"}

    for ticker, posts in by_ticker.items():
        print(f"━━━ {ticker} ({len(posts)}条) ━━━")
        for p in posts:
            # FinBERT 输入：标题 + 正文前300字
            input_text = p["title"] + ". " + p["selftext"][:300]
            result = finbert(input_text)[0]
            label = result["label"].lower()
            score = result["score"]

            print(f"\n  r/{p['subreddit']} | score={p['score']}")
            print(f"  标题: {p['title']}")
            print(f"  正文: {p['selftext'][:150]}...")
            print(f"  → FinBERT: {label_map[label]} (置信度 {score:.2f})")
        print()


if __name__ == "__main__":
    main()
