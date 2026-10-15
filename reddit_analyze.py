#!/usr/bin/env python3
"""
直接分析 Reddit 帖子，填入 layer1_results
relevance: 规则判断
sentiment: FinBERT 本地模型
"""
import re
import sqlite3

# FinBERT 延迟加载（首次使用时初始化）
_finbert = None

def get_finbert():
    global _finbert
    if _finbert is None:
        from transformers import pipeline
        print("加载 FinBERT 模型（首次运行约下载 500MB）...")
        _finbert = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device=-1,
            truncation=True,
            max_length=512,
            batch_size=32,
        )
        print("FinBERT 加载完成\n")
    return _finbert

DB_PATH = "pokieticker.db"

# ── 公司名关键词（用于判断标题是否真正提到这家公司）──────────────────
COMPANY_NAMES = {
    "AAPL": ["apple", "iphone", "ipad", "macbook", "tim cook", "ios", "app store"],
    "MSFT": ["microsoft", "azure", "windows", "satya nadella", "office", "copilot", "xbox"],
    "NVDA": ["nvidia", "jensen huang", "geforce", "cuda", "h100", "h200", "blackwell", "gpu"],
    "AMZN": ["amazon", "aws", "andy jassy", "prime", "alexa", "whole foods"],
    "GOOGL": ["google", "alphabet", "youtube", "waymo", "gemini", "android", "deepmind", "sundar"],
    "GOOG":  ["google", "alphabet", "youtube", "waymo", "gemini", "android", "deepmind", "sundar"],
    "META":  ["meta platforms", "facebook", "instagram", "whatsapp", "zuckerberg", "oculus", "threads", "meta stock", "meta shares", "$meta"],
    "TSLA":  ["tesla", "elon musk", "cybertruck", "model 3", "model y", "model s", "gigafactory", "supercharger"],
    "AVGO":  ["broadcom", "avgo"],
    "ORCL":  ["oracle", "larry ellison"],
    "NFLX":  ["netflix", "streaming"],
    "AMD":   ["amd", "advanced micro", "lisa su", "radeon", "ryzen", "epyc"],
    "INTC":  ["intel", "pat gelsinger", "core ultra"],
    "QCOM":  ["qualcomm", "snapdragon"],
    "MU":    ["micron", "dram", "nand", "memory chip"],
    "ANET":  ["arista networks", "arista"],
    "SMCI":  ["super micro", "supermicro"],
    "TSM":   ["tsmc", "taiwan semiconductor"],
    "ASML":  ["asml", "euv", "extreme ultraviolet"],
    "ARM":   ["arm holdings", "arm chip", "arm architecture"],
    "LRCX":  ["lam research"],
    "AMAT":  ["applied materials"],
    "TXN":   ["texas instruments"],
    "CSCO":  ["cisco", "cisco systems"],
    "IBM":   ["ibm", "international business machines"],
    "NOW":   ["servicenow"],
    "CRM":   ["salesforce"],
    "SNOW":  ["snowflake"],
    "WDAY":  ["workday"],
    "ADBE":  ["adobe"],
    "MRVL":  ["marvell"],
    "BABA":  ["alibaba", "taobao", "tmall", "ant group", "alipay"],
    "JD":    ["jd.com", "jd logistics"],
    "BIDU":  ["baidu"],
    "NTES":  ["netease"],
    "BILI":  ["bilibili"],
    "SE":    ["sea limited", "shopee", "garena"],
    "MELI":  ["mercadolibre"],
    "NIO":   ["nio", "nio stock", "nio shares"],
    "LI":    ["li auto"],
    "XPEV":  ["xpeng"],
    "BYDDY": ["byd"],
    "NVO":   ["novo nordisk", "ozempic", "wegovy", "semaglutide"],
    "LLY":   ["eli lilly", "lilly", "mounjaro", "zepbound"],
    "UNH":   ["unitedhealth", "united health"],
    "JNJ":   ["johnson & johnson", "j&j", "janssen"],
    "MRNA":  ["moderna"],
    "WMT":   ["walmart", "wal-mart"],
    "COST":  ["costco"],
    "TGT":   ["target corp", "target store", "target corporation"],
    "MCD":   ["mcdonald's", "mcdonalds"],
    "SBUX":  ["starbucks"],
    "NKE":   ["nike"],
    "KO":    ["coca-cola", "coca cola"],
    "CMG":   ["chipotle"],
    "HD":    ["home depot"],
    "EBAY":  ["ebay"],
    "UBER":  ["uber"],
    "ABNB":  ["airbnb"],
    "SQ":    ["block inc", "cash app", "square payments"],
    "HOOD":  ["robinhood"],
    "COIN":  ["coinbase"],
    "MARA":  ["marathon digital"],
    "GME":   ["gamestop", "game stop"],
    "AMC":   ["amc entertainment", "amc theaters"],
    "RIVN":  ["rivian"],
    "LCID":  ["lucid motors", "lucid air"],
    "STLA":  ["stellantis"],
    "F":     ["ford motor", "ford f-150", "ford ev"],
    "GM":    ["general motors"],
    "TM":    ["toyota"],
    "BA":    ["boeing"],
    "CVX":   ["chevron"],
    "XOM":   ["exxonmobil", "exxon mobil", "exxon"],
    "OXY":   ["occidental petroleum", "occidental"],
    "MS":    ["morgan stanley"],
    "GS":    ["goldman sachs", "goldman"],
    "BAC":   ["bank of america", "bofa"],
    "WFC":   ["wells fargo"],
    "C":     ["citigroup", "citi"],
    "BLK":   ["blackrock"],
    "V":     ["visa"],
    "MA":    ["mastercard"],
    "DIS":   ["disney", "walt disney"],
    "WBD":   ["warner bros", "warner brothers"],
    "VZ":    ["verizon"],
    "T":     ["at&t"],
    "CRWD":  ["crowdstrike"],
    "SOUN":  ["soundhound"],
    "ZM":    ["zoom video", "zoom calls"],
    "ROKU":  ["roku"],
    "FB":    ["facebook", "meta platforms", "zuckerberg", "instagram", "whatsapp"],
    "GLD":   ["gold etf", "spdr gold", "gold trust"],
    "XLE":   ["energy etf", "xle", "energy sector"],
    "XLU":   ["utilities etf", "xlu"],
    "XLY":   ["consumer etf", "xly"],
    "USO":   ["oil etf", "uso"],
    "FXI":   ["china etf", "fxi"],
    "GS":    ["goldman sachs", "goldman"],
}

# ── 情感词汇 ─────────────────────────────────────────────────────────
BULL_WORDS = [
    "bull", "bullish", "buy", "buying", "bought", "long", "calls", "call option",
    "moon", "rocket", "🚀", "surge", "rally", "gain", "gains", "profit", "profits",
    "beat", "beats", "beat earnings", "strong", "growth", "upside", "undervalued",
    "dip", "cheap", "opportunity", "squeeze", "breakout", "all time high", "ath",
    "outperform", "upgrade", "raise", "higher", "up ", "uptrend", "green",
    "positive", "optimistic", "confident", "holding", "hold", "hodl",
]
BEAR_WORDS = [
    "bear", "bearish", "sell", "selling", "sold", "short", "puts", "put option",
    "crash", "dump", "🩸", "📉", "loss", "losses", "miss", "misses", "missed earnings",
    "weak", "decline", "downside", "overvalued", "avoid", "drop", "falling", "fall",
    "underperform", "downgrade", "cut", "lower", "down ", "downtrend", "red",
    "negative", "worried", "concern", "risk", "lawsuit", "investigation", "layoff",
    "layoffs", "recession", "inflation", "debt",
]

# ── 技术讨论型 subreddit（低相关，除非标题明确提公司）────────────────
TECH_SUBS = {
    "Reddit r/algotrading", "Reddit r/quant", "Reddit r/econmonitor",
    "Reddit r/AlgoTrading", "Reddit r/Quant",
}

# ── 假阳性词（这些词出现时，即使匹配到公司名也要小心）────────────────
META_FALSE = ["meta labeling", "metatrader", "meta trader", "meta post", "meta thread"]
COIN_FALSE  = ["bitcoin", "btc", "eth", "ethereum", "crypto bot", "binance", "altcoin", "meme coin"]
F_FALSE     = ["futures", "forex", "f-string", "f test"]


def title_mentions(title_lower: str, symbol: str) -> bool:
    """标题是否明确提到这家公司"""
    names = COMPANY_NAMES.get(symbol, [])
    ticker_pattern = r'\b' + re.escape(symbol.lower()) + r'\b'
    if re.search(ticker_pattern, title_lower):
        return True
    return any(n in title_lower for n in names)


def body_mentions(body_lower: str, symbol: str) -> bool:
    """正文是否提到这家公司"""
    names = COMPANY_NAMES.get(symbol, [])
    ticker_pattern = r'\$' + re.escape(symbol.lower())
    if re.search(ticker_pattern, body_lower):
        return True
    return any(n in body_lower for n in names)


def is_false_positive(title_lower: str, body_lower: str, symbol: str) -> bool:
    """检查常见假阳性"""
    text = title_lower + " " + body_lower
    if symbol == "META":
        return any(fp in text for fp in META_FALSE)
    if symbol == "COIN":
        # COIN 只在明确提到 Coinbase 时才相关
        return "coinbase" not in text
    if symbol == "F":
        return any(fp in text for fp in F_FALSE)
    return False


def get_sentiment_batch(texts: list[str]) -> list[str]:
    """批量用 FinBERT 判断情感，返回 positive/negative/neutral 列表"""
    finbert = get_finbert()
    results = finbert(texts, truncation=True, max_length=512)
    label_map = {"positive": "positive", "negative": "negative", "neutral": "neutral"}
    return [label_map.get(r["label"].lower(), "neutral") for r in results]


def get_sentiment(title: str, body: str) -> str:
    """单条情感分析（兼容旧接口，内部用FinBERT）"""
    text = (title + ". " + body[:300]).strip()
    return get_sentiment_batch([text])[0]


def get_key_discussion(title: str, body: str, symbol: str) -> str:
    """取标题作为10字摘要"""
    t = title.strip()
    return t[:120] if t else ""


def get_growth_reason(title: str, body: str) -> str:
    text = (title + " " + body[:300]).lower()
    for w in BULL_WORDS:
        if w in text:
            # 找含这个词的短语
            idx = text.find(w)
            snippet = text[max(0, idx-20):idx+40].strip()
            return snippet[:80]
    return ""


def get_decrease_reason(title: str, body: str) -> str:
    text = (title + " " + body[:300]).lower()
    for w in BEAR_WORDS:
        if w in text:
            idx = text.find(w)
            snippet = text[max(0, idx-20):idx+40].strip()
            return snippet[:80]
    return ""


def analyze(row: dict) -> dict:
    symbol    = row["symbol"]
    title     = row["title"] or ""
    body      = row["description"] or ""
    publisher = row["publisher"] or ""

    title_l = title.lower()
    body_l  = body.lower()

    in_title = title_mentions(title_l, symbol)
    in_body  = body_mentions(body_l, symbol)
    is_tech  = publisher in TECH_SUBS
    false_pos = is_false_positive(title_l, body_l, symbol)

    # ── 相关性判断 ──
    if false_pos:
        relevant = False
    elif in_title:
        relevant = True
    elif is_tech:
        relevant = False          # 技术型 sub 且标题没提公司 → 无关
    elif in_body:
        relevant = True
    else:
        relevant = False

    if not relevant:
        return {
            "news_id": row["id"], "symbol": symbol,
            "relevance": "irrelevant", "sentiment": "neutral",
            "key_discussion": "", "reason_growth": "", "reason_decrease": "",
        }

    sentiment = get_sentiment(title, body)
    key       = get_key_discussion(title, body, symbol)
    growth    = get_growth_reason(title, body) if sentiment in ("positive", "neutral") else ""
    decrease  = get_decrease_reason(title, body) if sentiment in ("negative", "neutral") else ""

    return {
        "news_id": row["id"], "symbol": symbol,
        "relevance": "relevant", "sentiment": sentiment,
        "key_discussion": key, "reason_growth": growth, "reason_decrease": decrease,
    }


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT nr.id, nr.title, nr.description, nt.symbol, nr.publisher
        FROM news_raw nr
        JOIN news_ticker nt ON nr.id = nt.news_id
        LEFT JOIN layer1_results l ON l.news_id = nr.id AND l.symbol = nt.symbol
        WHERE nr.id LIKE 'reddit_%'
        AND l.news_id IS NULL
    """).fetchall()

    total     = len(rows)
    relevant  = 0
    processed = 0

    print(f"开始分析 {total} 对 (post, ticker)...")

    BATCH = 500
    for i in range(0, total, BATCH):
        chunk = rows[i:i+BATCH]

        # 先用规则判断 relevance
        partial = [analyze(dict(r)) for r in chunk]

        # 对 relevant 的条目批量跑 FinBERT
        rel_indices = [j for j, r in enumerate(partial) if r["relevance"] == "relevant"]
        if rel_indices:
            texts = []
            for j in rel_indices:
                row = dict(chunk[j])
                t = (row["title"] or "").strip()
                b = (row["description"] or "")[:300].strip()
                texts.append(f"{t}. {b}" if b else t)
            sentiments = get_sentiment_batch(texts)
            for j, sent in zip(rel_indices, sentiments):
                partial[j]["sentiment"] = sent
                # 更新 reason 字段
                row = dict(chunk[j])
                t = row["title"] or ""
                b = row["description"] or ""
                if sent == "positive":
                    partial[j]["reason_growth"]   = get_growth_reason(t, b)
                    partial[j]["reason_decrease"]  = ""
                elif sent == "negative":
                    partial[j]["reason_growth"]   = ""
                    partial[j]["reason_decrease"]  = get_decrease_reason(t, b)
                else:
                    partial[j]["reason_growth"]   = get_growth_reason(t, b)
                    partial[j]["reason_decrease"]  = get_decrease_reason(t, b)

        conn.executemany("""
            INSERT OR REPLACE INTO layer1_results
            (news_id, symbol, relevance, key_discussion, sentiment, reason_growth, reason_decrease)
            VALUES (:news_id, :symbol, :relevance, :key_discussion, :sentiment, :reason_growth, :reason_decrease)
        """, partial)
        conn.commit()

        processed += len(chunk)
        relevant  += sum(1 for r in partial if r["relevance"] == "relevant")
        print(f"  [{processed}/{total}] relevant 累计: {relevant}")

    print(f"\n完成！")
    print(f"  总处理: {processed}")
    print(f"  relevant: {relevant} ({relevant/processed*100:.1f}%)")
    print(f"  irrelevant: {processed-relevant}")
    conn.close()


if __name__ == "__main__":
    main()
