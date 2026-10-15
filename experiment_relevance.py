#!/usr/bin/env python3
"""
实验脚本：用 Claude Haiku 判断 Reddit 帖子对某个 ticker 的相关性
只问两件事：r（相关性）+ s（情感）
目的：肉眼验证准确度，决定是否纳入正式 pipeline
"""

import json
import os
import re
import anthropic
from collections import defaultdict

# ─── Ticker 关键词 ────────────────────────────────────────────
TICKER_KEYWORDS = {
    "AAPL":  ["apple", "aapl", "tim cook", "iphone", "ipad", "macbook"],
    "TSLA":  ["tesla", "tsla", "elon musk", "cybertruck", "model 3", "model y"],
    "NVDA":  ["nvidia", "nvda", "jensen huang", "h100", "h200", "gpu", "cuda"],
    "MSFT":  ["microsoft", "msft", "satya nadella", "azure", "copilot"],
    "GOOGL": ["google", "alphabet", "googl", "gemini", "youtube", "waymo"],
    "AMZN":  ["amazon", "amzn", "andy jassy", "aws", "prime"],
    "META":  ["meta platforms", "meta", "facebook", "zuckerberg", "instagram"],
    "AMD":   ["amd", "lisa su", "radeon", "ryzen", "epyc"],
}

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")

# 从 .env 读取（如果环境变量没有）
if not API_KEY:
    env_path = os.path.join(DATA_DIR, ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("ANTHROPIC_API_KEY="):
                API_KEY = line.strip().split("=", 1)[1]


def collect_candidates() -> list[dict]:
    """扫描所有 JSON，提取通过预过滤 + ticker 匹配的 (post, ticker) 对"""
    candidates = []
    for fname in os.listdir(DATA_DIR):
        if not fname.endswith(".json"):
            continue
        posts = json.load(open(os.path.join(DATA_DIR, fname)))
        for p in posts:
            # 预过滤
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
                        "post_id":   p["id"],
                        "title":     p["title"],
                        "selftext":  selftext[:400],   # 截断
                        "score":     p["score"],
                        "subreddit": p["subreddit"],
                    })
    return candidates


def build_prompt(ticker: str, posts: list[dict]) -> str:
    lines = []
    for i, p in enumerate(posts):
        lines.append(f"[{i}] {p['title']}")
        if p["selftext"].strip():
            lines.append(f"  > {p['selftext'][:200]}")
    return f"""For each Reddit post, judge if it's specifically about {ticker} stock (not just a passing mention).

{chr(10).join(lines)}

Return JSON array only:
[{{"i":0,"r":"y"|"n","s":"+"|"-"|"0"}}]
r: "y" = post is genuinely discussing {ticker}, "n" = just a passing mention or unrelated
s: "+" positive, "-" negative, "0" neutral (only if r="y", else "0")
JSON:"""


def run_experiment():
    candidates = collect_candidates()
    print(f"找到 {len(candidates)} 对 (post, ticker) 候选\n")

    # 按 ticker 分组
    by_ticker: dict = defaultdict(list)
    for c in candidates:
        by_ticker[c["ticker"]].append(c)

    client = anthropic.Anthropic(api_key=API_KEY)
    all_results = []

    for ticker, posts in by_ticker.items():
        print(f"━━━ {ticker} ({len(posts)} 条) ━━━")
        prompt = build_prompt(ticker, posts)

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text

        # 解析 JSON
        start = text.find("[")
        end   = text.rfind("]") + 1
        try:
            items = json.loads(text[start:end]) if start >= 0 else []
        except json.JSONDecodeError:
            print(f"  [!] JSON 解析失败: {text}")
            continue

        results_map = {item["i"]: item for item in items}

        for i, post in enumerate(posts):
            result = results_map.get(i, {})
            r = result.get("r", "?")
            s = result.get("s", "0")
            sentiment_str = {"+" : "正面 ▲", "-": "负面 ▼", "0": "中立 ─"}.get(s, s)
            relevance_str = "✅ 相关" if r == "y" else "❌ 路人甲"

            print(f"\n  [{i}] r/{ post['subreddit'] } | score={post['score']}")
            print(f"  标题: {post['title']}")
            print(f"  正文: {post['selftext'][:120]}...")
            print(f"  → Haiku: {relevance_str}  {sentiment_str if r == 'y' else ''}")

            all_results.append({**post, "relevance": r, "sentiment": s})

        print()

    # 汇总
    relevant   = [r for r in all_results if r["relevance"] == "y"]
    irrelevant = [r for r in all_results if r["relevance"] == "n"]
    print(f"\n{'='*50}")
    print(f"总计: {len(all_results)} 对")
    print(f"  相关  (r=y): {len(relevant)}")
    print(f"  路人甲(r=n): {len(irrelevant)}")
    print(f"\n相关率: {len(relevant)*100//len(all_results)}%")

    return all_results


if __name__ == "__main__":
    run_experiment()
