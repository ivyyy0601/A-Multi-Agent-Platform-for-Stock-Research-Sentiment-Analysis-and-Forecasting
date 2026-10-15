#!/usr/bin/env python3
"""
Reddit 完整导入管道：
  1. 读取 JSONL 文件（Arctic Shift 下载）
  2. 写入 news_raw
  3. Ticker 关键词匹配 → news_ticker
  4. Layer0 规则过滤 → layer0_results

用法：
  python3 reddit_pipeline.py                        # 读 JSONL_DIR 下所有 .jsonl 文件
  python3 reddit_pipeline.py path/to/file.jsonl     # 指定单个文件
"""

import json
import re
import sqlite3
import sys
import os
from datetime import datetime, timezone

# ─── 配置 ────────────────────────────────────────────────────
# JSONL 文件所在目录（把下载的文件都放这里）
JSONL_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pokieticker.db")

# ─── Ticker 关键词（从 tickers 表扩展）────────────────────────
# $SYMBOL 格式对所有 ticker 通用
# 额外添加公司名/常见别名（只对高辨识度的 ticker）
TICKER_EXTRA: dict[str, list[str]] = {
    "AAPL":  ["apple", "iphone", "ipad", "macbook", "tim cook", "apple watch"],
    "AMZN":  ["amazon", "andy jassy", "aws", "prime video"],
    "GOOGL": ["google", "alphabet", "youtube", "waymo", "deepmind", "gemini"],
    "GOOG":  ["google", "alphabet"],
    "META":  ["meta platforms", "facebook", "instagram", "zuckerberg", "whatsapp", "threads"],
    "MSFT":  ["microsoft", "satya nadella", "azure", "copilot", "windows", "xbox"],
    "NVDA":  ["nvidia", "jensen huang", "geforce", "cuda", "blackwell", "h100", "h200"],
    "TSLA":  ["tesla", "elon musk", "cybertruck", "model 3", "model y", "model s", "gigafactory"],
    "AMD":   ["advanced micro devices", "lisa su", "radeon", "ryzen", "epyc"],
    "INTC":  ["intel", "pat gelsinger"],
    "TSM":   ["tsmc", "taiwan semiconductor"],
    "AVGO":  ["broadcom"],
    "QCOM":  ["qualcomm"],
    "ASML":  ["asml"],
    "AMAT":  ["applied materials"],
    "MU":    ["micron"],
    "BABA":  ["alibaba", "taobao", "tmall", "ant group", "alipay"],
    "BIDU":  ["baidu"],
    "NIO":   ["nio"],
    "XPEV":  ["xpeng"],
    "LI":    ["li auto"],
    "NFLX":  ["netflix"],
    "DIS":   ["disney", "disney+"],
    "SBUX":  ["starbucks"],
    "MCD":   ["mcdonald"],
    "KO":    ["coca-cola", "coca cola"],
    "NKE":   ["nike"],
    "WMT":   ["walmart"],
    "COST":  ["costco"],
    "TGT":   ["target"],
    "COIN":  ["coinbase"],
    "HOOD":  ["robinhood"],
    "GME":   ["gamestop"],
    "AMC":   ["amc entertainment"],
    "UBER":  ["uber"],
    "BA":    ["boeing"],
    "GS":    ["goldman sachs"],
    "MS":    ["morgan stanley"],
    "JPM":   ["jpmorgan", "jp morgan"],
    "BAC":   ["bank of america"],
    "WFC":   ["wells fargo"],
    "V":     ["visa"],
    "MA":    ["mastercard"],
    "XOM":   ["exxon", "exxonmobil"],
    "CVX":   ["chevron"],
    "GLD":   ["gold etf", "spdr gold"],
    "SMCI":  ["super micro", "supermicro"],
    "CRWD":  ["crowdstrike"],
    "NOW":   ["servicenow"],
    "CRM":   ["salesforce"],
    "SNOW":  ["snowflake"],
    "ORCL":  ["oracle"],
    "IBM":   ["ibm"],
    "CSCO":  ["cisco"],
    "TXN":   ["texas instruments"],
    "LLY":   ["eli lilly", "lilly"],
    "JNJ":   ["johnson & johnson", "johnson and johnson"],
    "MRNA":  ["moderna"],
    "UNH":   ["unitedhealth"],
    "RIVN":  ["rivian"],
    "LCID":  ["lucid motors", "lucid group"],
    "F":     ["ford motor", "ford f-150"],
    "GM":    ["general motors"],
    "STLA":  ["stellantis"],
    "TM":    ["toyota"],
    "BYDDY": ["byd"],
    "NVO":   ["novo nordisk", "ozempic", "wegovy"],
    "ROKU":  ["roku"],
    "MELI":  ["mercadolibre", "mercado libre"],
    "SE":    ["sea limited", "shopee"],
    "JD":    ["jd.com"],
    "BILI":  ["bilibili"],
    "NTES":  ["netease"],
    "DELL":  ["dell"],
    "ARM":   ["arm holdings"],
    "ANET":  ["arista networks"],
    "MRVL":  ["marvell"],
    "WDAY":  ["workday"],
    "ADBE":  ["adobe"],
    "ZM":    ["zoom"],
    "CMG":   ["chipotle"],
    "SOUN":  ["soundhound"],
    "MARA":  ["mara holdings"],
    "AI":    ["c3.ai"],
    "LRCX":  ["lam research"],
    "HD":    ["home depot"],
    "OXY":   ["occidental petroleum"],
    "T":     ["at&t"],
    "VZ":    ["verizon"],
    "WBD":   ["warner bros", "warner brothers"],
    "CRWV":  ["coreweave"],
}


def build_ticker_map(symbols: list[str]) -> dict[str, list[str]]:
    """为每个 symbol 构建匹配关键词列表"""
    mapping = {}
    for sym in symbols:
        kws = [f"${sym.lower()}"]          # $NVDA 格式（最可靠）
        kws.extend(TICKER_EXTRA.get(sym, []))
        mapping[sym] = kws
    return mapping


# ─── 读取 JSONL ───────────────────────────────────────────────
def load_jsonl(path: str) -> list[dict]:
    posts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                posts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return posts


def find_jsonl_files() -> list[str]:
    """找到所有待处理的 JSONL 文件"""
    if len(sys.argv) > 1:
        return [sys.argv[1]]
    files = [
        os.path.join(JSONL_DIR, f)
        for f in os.listdir(JSONL_DIR)
        if f.endswith(".jsonl")
    ]
    return sorted(files)


# ─── Layer 0 规则 ─────────────────────────────────────────────
LIST_RE1 = re.compile(r"^\d+\s+(best|top|worst|biggest|largest|most|highest|lowest)\b", re.I)
LIST_RE2 = re.compile(r"\b(top|best|worst)\s+\d+\b", re.I)


def layer0_check(title: str, selftext: str, matched_symbols: list[str]) -> tuple[bool, str]:
    desc = selftext.strip()

    if not desc:
        return False, "empty_description"

    if len(desc) < 30:
        return False, "description_too_short"

    if LIST_RE1.search(title) or LIST_RE2.search(title):
        return False, "list_article"

    # 提到的 ticker 超过 10 个且目标 ticker 不在标题中
    # （这条在写入时按 symbol 各自判断）
    return True, "passed"


# ─── 主流程 ───────────────────────────────────────────────────
def ts_to_iso(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def process_post(p: dict, ticker_map: dict, conn: sqlite3.Connection, stats: dict):
    selftext = p.get("selftext", "")
    if selftext in ("[removed]", "[deleted]", ""):
        return
    if p.get("score", 0) < 2:
        return

    title    = p.get("title", "")
    text_low = (title + " " + selftext).lower()
    nid      = "reddit_" + p["id"]

    matched = [sym for sym, kws in ticker_map.items()
               if any(k in text_low for k in kws)]
    if not matched:
        return

    # news_raw
    conn.execute(
        """INSERT OR IGNORE INTO news_raw
           (id, title, description, publisher, author, published_utc, article_url)
           VALUES (?,?,?,?,?,?,?)""",
        (nid, title, selftext[:2000],
         f"Reddit r/{p.get('subreddit','')}",
         p.get("author", ""),
         ts_to_iso(p["created_utc"]),
         "https://reddit.com" + p.get("permalink", "")),
    )
    stats["posts"] += 1

    for sym in matched:
        conn.execute(
            "INSERT OR IGNORE INTO news_ticker (news_id, symbol) VALUES (?,?)",
            (nid, sym)
        )
        stats["links"] += 1

        passed, reason = layer0_check(title, selftext, matched)
        if len(matched) > 10 and sym.upper() not in title.upper():
            passed, reason = False, "too_many_tickers"

        conn.execute(
            """INSERT OR IGNORE INTO layer0_results
               (news_id, symbol, passed, reason) VALUES (?,?,?,?)""",
            (nid, sym, 1 if passed else 0, reason)
        )
        if passed:
            stats["passed"] += 1
        else:
            stats["filtered"] += 1


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    symbols    = [r[0] for r in conn.execute("SELECT symbol FROM tickers").fetchall()]
    ticker_map = build_ticker_map(symbols)
    print(f"使用 {len(symbols)} 个 ticker")

    files = find_jsonl_files()
    if not files:
        print(f"没有找到 JSONL 文件，请把文件放到：{JSONL_DIR}")
        conn.close()
        return

    print(f"找到 {len(files)} 个文件\n")

    total = {"posts": 0, "links": 0, "passed": 0, "filtered": 0}

    for fpath in files:
        fname = os.path.basename(fpath)
        posts = load_jsonl(fpath)
        stats = {"posts": 0, "links": 0, "passed": 0, "filtered": 0}

        for p in posts:
            process_post(p, ticker_map, conn, stats)

        conn.commit()
        print(f"[{fname}]")
        print(f"  原始帖子: {len(posts)}  新增: {stats['posts']}  ticker关联: {stats['links']}  passed: {stats['passed']}  filtered: {stats['filtered']}")

        for k in total:
            total[k] += stats[k]

    conn.close()

    print(f"\n{'='*50}")
    print(f"news_raw 新增:       {total['posts']}")
    print(f"news_ticker 关联:    {total['links']}")
    print(f"layer0 passed:       {total['passed']}")
    print(f"layer0 filtered:     {total['filtered']}")
    if total["links"] > 0:
        print(f"通过率:              {total['passed']*100//total['links']}%")


if __name__ == "__main__":
    run()
