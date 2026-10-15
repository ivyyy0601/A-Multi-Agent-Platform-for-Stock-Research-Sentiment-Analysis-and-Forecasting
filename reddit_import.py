#!/usr/bin/env python3
"""
把 Reddit JSON 数据导入 pokieticker.db
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "reddit_data")
DB_PATH  = os.path.join(ROOT_DIR, "pokieticker.db")

TICKER_KEYWORDS = {
  "AAPL":  ["Apple", "AAPL", "Apple Inc"],
  "MSFT":  ["Microsoft", "MSFT", "Microsoft Corp"],
  "NVDA":  ["Nvidia", "NVDA", "NVIDIA"],
  "AMZN":  ["Amazon", "AMZN", "Amazon.com"],
  "GOOGL": ["Google", "GOOGL", "Alphabet", "Google LLC"],
  "GOOG":  ["Google", "GOOG", "Alphabet"],
  "META":  ["Meta", "META", "Facebook", "Meta Platforms"],
  "TSLA":  ["Tesla", "TSLA", "Tesla Inc"],
  "AVGO":  ["Broadcom", "AVGO", "Broadcom Inc"],
  "ORCL":  ["Oracle", "ORCL", "Oracle Corp"],
  "NFLX":  ["Netflix", "NFLX", "Netflix Inc"],
  "AMD":   ["AMD", "Advanced Micro Devices"],
  "INTC":  ["Intel", "INTC", "Intel Corp"],
  "QCOM":  ["Qualcomm", "QCOM", "QUALCOMM"],
  "MU":    ["Micron", "MU", "Micron Technology"],
  "ANET":  ["Arista", "ANET", "Arista Networks"],
  "SMCI":  ["Super Micro", "SMCI", "SuperMicro", "Supermicro"],
  "TSM":   ["TSMC", "TSM", "Taiwan Semiconductor"],
  "ASML":  ["ASML"],
  "ARM":   ["ARM", "Arm Holdings"],
  "LRCX":  ["Lam Research", "LRCX"],
  "AMAT":  ["Applied Materials", "AMAT"],
  "TXN":   ["Texas Instruments", "TXN"],
  "CSCO":  ["Cisco", "CSCO", "Cisco Systems"],
  "IBM":   ["IBM", "International Business Machines"],
  "NOW":   ["ServiceNow"],
  "CRM":   ["Salesforce", "CRM"],
  "SNOW":  ["Snowflake", "SNOW"],
  "WDAY":  ["Workday", "WDAY"],
  "ADBE":  ["Adobe", "ADBE", "Adobe Inc"],
  "MRVL":  ["Marvell", "MRVL", "Marvell Technology"],
  "AI":    ["C3.ai"],
  "BABA":  ["Alibaba", "BABA", "Alibaba Group"],
  "JD":    ["JD.com", "JD"],
  "BIDU":  ["Baidu", "BIDU"],
  "NTES":  ["NetEase", "NTES"],
  "BILI":  ["Bilibili"],
  "SE":    ["Sea Limited", "Shopee"],
  "MELI":  ["MercadoLibre", "MELI"],
  "NIO":   ["NIO", "Nio Inc"],
  "LI":    ["Li Auto"],
  "XPEV":  ["XPeng", "XPEV"],
  "BYDDY": ["BYD", "BYDDY"],
  "NVO":   ["Novo Nordisk", "NVO"],
  "LLY":   ["Eli Lilly", "LLY", "Lilly"],
  "UNH":   ["UnitedHealth", "UNH", "United Health"],
  "JNJ":   ["Johnson & Johnson", "JNJ", "J&J"],
  "MRNA":  ["Moderna", "MRNA"],
  "WMT":   ["Walmart", "WMT", "Wal-Mart"],
  "COST":  ["Costco"],
  "TGT":   ["Target Corp", "Target store", "Target Corporation"],
  "MCD":   ["McDonald's", "MCD", "McDonalds"],
  "SBUX":  ["Starbucks", "SBUX"],
  "NKE":   ["Nike", "NKE", "Nike Inc"],
  "KO":    ["Coca-Cola", "Coca Cola", "Coca Cola stock"],
  "CMG":   ["Chipotle", "CMG"],
  "HD":    ["Home Depot", "HD"],
  "EBAY":  ["eBay", "EBAY"],
  "UBER":  ["Uber", "UBER", "Uber Technologies"],
  "ABNB":  ["Airbnb", "ABNB"],
  "SQ":    ["Block Inc", "Cash App", "Square payments"],
  "HOOD":  ["Robinhood", "HOOD"],
  "COIN":  ["Coinbase", "COIN"],
  "MARA":  ["Marathon Digital", "MARA"],
  "GME":   ["GameStop", "GME"],
  "AMC":   ["AMC", "AMC Entertainment"],
  "RIVN":  ["Rivian", "RIVN"],
  "LCID":  ["Lucid", "LCID", "Lucid Motors"],
  "STLA":  ["Stellantis", "STLA"],
  "F":     ["Ford", "Ford Motor"],
  "GM":    ["GM", "General Motors"],
  "TM":    ["Toyota", "TM", "Toyota Motor"],
  "BA":    ["Boeing", "Boeing Co"],
  "CVX":   ["Chevron", "CVX"],
  "XOM":   ["ExxonMobil", "XOM", "Exxon", "Mobil"],
  "OXY":   ["Occidental", "OXY", "Occidental Petroleum"],
  "MS":    ["Morgan Stanley"],
  "GS":    ["Goldman Sachs", "Goldman"],
  "BAC":   ["Bank of America", "BAC", "BofA"],
  "WFC":   ["Wells Fargo", "WFC"],
  "C":     ["Citigroup", "Citi"],
  "BLK":   ["BlackRock", "BLK"],
  "V":     ["Visa", "Visa Inc"],
  "MA":    ["Mastercard"],
  "DIS":   ["Disney", "DIS", "Walt Disney"],
  "WBD":   ["Warner Bros", "WBD", "Warner Brothers"],
  "VZ":    ["Verizon", "VZ"],
  "T":     ["AT&T"],
  "CRWD":  ["CrowdStrike", "CRWD"],
  "SOUN":  ["SoundHound"],
  "ZM":    ["Zoom", "ZM", "Zoom Video"],
  "ROKU":  ["Roku", "ROKU"],
  "IDCC":  ["InterDigital", "IDCC"],
  "FXI":   ["FXI", "China ETF"],
  "GLD":   ["GLD", "Gold ETF", "SPDR Gold"],
  "USO":   ["USO", "Oil ETF"],
  "XLE":   ["XLE", "Energy ETF"],
  "XLU":   ["XLU", "Utilities ETF"],
  "XLY":   ["XLY", "Consumer ETF"],
  "FB":    ["Facebook", "FB", "Meta"],
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ts_to_iso(unix_ts) -> str:
    return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_candidates() -> list[dict]:
    """预过滤 + ticker匹配，返回 (post, ticker) 候选列表"""
    candidates = []
    seen_post_ids = set()

    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        posts = json.load(open(os.path.join(DATA_DIR, fname)))
        for p in posts:
            selftext = p.get("selftext", "")
            # 预过滤
            if selftext in ("[removed]", "[deleted]"):
                selftext = ""
            if p.get("score", 0) < 2:
                continue
            if len(p["title"]) < 20:
                continue

            text_lower = (p["title"] + " " + selftext).lower()
            matched_tickers = []
            for ticker, kws in TICKER_KEYWORDS.items():
                def _match(k):
                    kl = k.lower()
                    if len(kl) <= 3:
                        # 短关键词要求词边界，避免误匹配
                        return bool(re.search(r'\b' + re.escape(kl) + r'\b', text_lower))
                    return kl in text_lower
                if any(_match(k) for k in kws):
                    matched_tickers.append(ticker)

            if not matched_tickers:
                continue

            post_id = "reddit_" + p["id"]
            seen_post_ids.add(post_id)
            candidates.append({
                "post_id":         post_id,
                "title":           p["title"],
                "selftext":        selftext,
                "author":          p.get("author", ""),
                "score":           p.get("score", 0),
                "subreddit":       p["subreddit"],
                "url":             "https://reddit.com" + p.get("permalink", ""),
                "published_utc":   ts_to_iso(p["created_utc"]),
                "num_comments":    p.get("num_comments", 0),
                "matched_tickers": matched_tickers,
            })

    return candidates


def import_to_db(candidates: list[dict]) -> dict:
    conn = get_conn()
    stats = {"posts": 0, "ticker_links": 0, "skipped": 0}

    for c in candidates:
        # 1. 插入 news_raw
        existing = conn.execute(
            "SELECT id FROM news_raw WHERE id = ?", (c["post_id"],)
        ).fetchone()

        if existing:
            stats["skipped"] += 1
        else:
            conn.execute(
                """INSERT INTO news_raw
                   (id, title, description, publisher, author, published_utc, article_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    c["post_id"],
                    c["title"],
                    c["selftext"][:2000],           # description = 正文
                    f"Reddit r/{c['subreddit']}",   # publisher
                    c["author"],
                    c["published_utc"],
                    c["url"],
                ),
            )
            stats["posts"] += 1

        # 2. 插入 news_ticker + layer0_results（每个匹配的 ticker）
        for ticker in c["matched_tickers"]:
            conn.execute(
                "INSERT OR IGNORE INTO news_ticker (news_id, symbol) VALUES (?, ?)",
                (c["post_id"], ticker),
            )
            conn.execute(
                """INSERT OR IGNORE INTO layer0_results
                   (news_id, symbol, passed, reason) VALUES (?, ?, 1, 'reddit_import')""",
                (c["post_id"], ticker),
            )
            stats["ticker_links"] += 1

    conn.commit()
    conn.close()
    return stats


def verify_db():
    """检查写入结果"""
    conn = get_conn()

    total = conn.execute(
        "SELECT COUNT(*) FROM news_raw WHERE id LIKE 'reddit_%'"
    ).fetchone()[0]

    by_ticker = conn.execute(
        """SELECT symbol, COUNT(*) as cnt
           FROM news_ticker nt
           JOIN news_raw nr ON nt.news_id = nr.id
           WHERE nr.id LIKE 'reddit_%'
           GROUP BY symbol ORDER BY cnt DESC"""
    ).fetchall()

    sample = conn.execute(
        """SELECT nr.id, nr.title, nr.publisher, nr.published_utc, nt.symbol
           FROM news_raw nr
           JOIN news_ticker nt ON nr.id = nt.news_id
           WHERE nr.id LIKE 'reddit_%'
           LIMIT 5"""
    ).fetchall()

    conn.close()

    print(f"\n{'='*50}")
    print(f"数据库里 Reddit 帖子总数: {total}")
    print(f"\n按 ticker 分布:")
    for row in by_ticker:
        print(f"  {row['symbol']:<8} {row['cnt']} 条")

    print(f"\n样本数据 (前5条):")
    for r in sample:
        print(f"  [{r['symbol']}] {r['publisher']} | {r['published_utc'][:10]}")
        print(f"  {r['title'][:70]}")
        print()


def main():
    print("扫描 Reddit JSON 文件...")
    candidates = load_candidates()

    total_posts   = len(set(c["post_id"] for c in candidates))
    total_links   = len(candidates)
    print(f"预过滤后: {total_posts} 篇帖子，{total_links} 对 (post, ticker)")

    print("\n写入数据库...")
    stats = import_to_db(candidates)
    print(f"  新增帖子:       {stats['posts']}")
    print(f"  ticker 关联数:  {stats['ticker_links']}")
    print(f"  已存在跳过:     {stats['skipped']}")

    verify_db()


if __name__ == "__main__":
    main()
