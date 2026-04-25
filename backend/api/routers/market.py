import logging
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()
CORE_MOVER_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "AVGO",
    "QCOM", "INTC", "MU", "PLTR", "COIN", "SMCI", "ARM", "CRM", "ORCL", "UBER",
]


def _obb():
    """Lazy import to avoid slow startup on every module load."""
    try:
        from openbb import obb
        return obb
    except Exception as e:
        logger.error(f"OpenBB import error: {e}")
        return None


def _call(fn, *args, **kwargs):
    """Call an OpenBB function and return results as a list of dicts."""
    try:
        result = fn(*args, **kwargs)
        if result is None:
            return []
        data = result.results if hasattr(result, "results") else result
        if data is None:
            return []
        if isinstance(data, list):
            return [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in data]
        if hasattr(data, "model_dump"):
            return [data.model_dump()]
        return [dict(data)]
    except Exception as e:
        logger.error(f"OpenBB error: {e}")
        return []


def _yf_ticker(symbol: str):
    import yfinance as yf
    return yf.Ticker(symbol.upper())


def _empty_openbb() -> bool:
    return _obb() is None


def _quote_from_yf(symbol: str) -> dict:
    t = _yf_ticker(symbol)
    info = t.info or {}
    fast = getattr(t, "fast_info", {}) or {}
    price = fast.get("lastPrice") or info.get("currentPrice") or info.get("regularMarketPrice")
    prev = fast.get("previousClose") or info.get("previousClose") or info.get("regularMarketPreviousClose")
    volume = fast.get("lastVolume") or info.get("volume") or info.get("regularMarketVolume")
    return _norm({
        "symbol": symbol.upper(),
        "name": info.get("longName") or info.get("shortName") or symbol.upper(),
        "price": price,
        "prev_close": prev,
        "volume": volume,
        "year_low": info.get("fiftyTwoWeekLow"),
        "year_high": info.get("fiftyTwoWeekHigh"),
    })


def _json_safe(v):
    if v is None:
        return None
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            pass
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(v)
    return v


def _consensus_from_yf(symbol: str) -> list[dict]:
    try:
        info = _yf_ticker(symbol).info or {}
        if not info:
            return []
        return [{
            "symbol": symbol.upper(),
            "recommendation": info.get("recommendationKey"),
            "recommendation_mean": _json_safe(info.get("recommendationMean")),
            "analyst_count": _json_safe(info.get("numberOfAnalystOpinions")),
            "current_price": _json_safe(
                info.get("currentPrice") or info.get("regularMarketPrice")
            ),
        }]
    except Exception as e:
        logger.error(f"Consensus fallback error: {e}")
        return []


def _targets_from_yf(symbol: str) -> list[dict]:
    try:
        info = _yf_ticker(symbol).info or {}
        if not info:
            return []
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        return [{
            "symbol": symbol.upper(),
            "current_price": _json_safe(current_price),
            "target_mean_price": _json_safe(info.get("targetMeanPrice")),
            "target_high_price": _json_safe(info.get("targetHighPrice")),
            "target_low_price": _json_safe(info.get("targetLowPrice")),
            "target_median_price": _json_safe(info.get("targetMedianPrice")),
            "analyst_count": _json_safe(info.get("numberOfAnalystOpinions")),
            "recommendation": info.get("recommendationKey"),
        }]
    except Exception as e:
        logger.error(f"Targets fallback error: {e}")
        return []


def _overview_from_yf(kind: str) -> list[dict]:
    import yfinance as yf
    rows: list[dict] = []
    hist = yf.download(
        tickers=" ".join(CORE_MOVER_SYMBOLS),
        period="5d",
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    for sym in CORE_MOVER_SYMBOLS:
        try:
            df = hist[sym] if sym in hist.columns.get_level_values(0) else None
            if df is None or len(df.dropna()) < 2:
                continue
            df = df.dropna()
            last = df.iloc[-1]
            prev = df.iloc[-2]
            price = float(last["Close"])
            prev_close = float(prev["Close"])
            volume = float(last.get("Volume", 0) or 0)
            change = price - prev_close
            pct = (change / prev_close * 100) if prev_close else 0
            rows.append({
                "symbol": sym,
                "price": round(price, 4),
                "prev_close": round(prev_close, 4),
                "change": round(change, 4),
                "change_percent": round(pct, 4),
                "volume": int(volume),
            })
        except Exception as e:
            logger.warning(f"yfinance overview fallback failed for {sym}: {e}")
    if kind == "gainers":
        rows.sort(key=lambda r: r.get("change_percent") or 0, reverse=True)
    elif kind == "losers":
        rows.sort(key=lambda r: r.get("change_percent") or 0)
    elif kind == "active":
        rows.sort(key=lambda r: r.get("volume") or 0, reverse=True)
    return rows[:10]


def _market_news_from_yf(limit: int = 20) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for sym in ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "SPY"):
        try:
            news_items = _yf_ticker(sym).news or []
            for item in news_items:
                url = item.get("link") or item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                pub_ts = item.get("providerPublishTime")
                published = None
                if pub_ts:
                    try:
                        published = date.fromtimestamp(pub_ts).isoformat()
                    except Exception:
                        published = None
                out.append({
                    "title": item.get("title"),
                    "url": url,
                    "source": item.get("publisher"),
                    "published_utc": published,
                    "symbol": sym,
                })
                if len(out) >= limit:
                    return out
        except Exception as e:
            logger.warning(f"yfinance news fallback failed for {sym}: {e}")
    return out[:limit]


def _market_news_from_db(limit: int = 20) -> list[dict]:
    from backend.database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT
            n.title,
            n.article_url,
            COALESCE(n.publisher, n.author),
            n.published_utc,
            na.symbol
        FROM news_raw n
        JOIN news_aligned na
          ON na.news_id = n.id
        LEFT JOIN layer1_results lr
          ON lr.news_id = n.id
         AND lr.symbol = na.symbol
        WHERE lower(COALESCE(lr.relevance, 'relevant')) = 'relevant'
        GROUP BY n.id, na.symbol
        ORDER BY n.published_utc DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "title": r[0],
            "url": r[1],
            "source": r[2],
            "published_utc": r[3],
            "symbol": r[4],
        }
        for r in rows
    ]


def _history_from_yf(symbol: str, period: str = "1y") -> list[dict]:
    t = _yf_ticker(symbol)
    df = t.history(period=period, auto_adjust=False)
    if df is None or df.empty:
        return []
    rows = []
    for idx, row in df.reset_index().iterrows():
        dt = row.get("Date")
        rows.append({
            "date": str(getattr(dt, "date", lambda: dt)()),
            "open": None if row.get("Open") is None else float(row["Open"]),
            "high": None if row.get("High") is None else float(row["High"]),
            "low": None if row.get("Low") is None else float(row["Low"]),
            "close": None if row.get("Close") is None else float(row["Close"]),
            "volume": None if row.get("Volume") is None else float(row["Volume"]),
        })
    return rows


def _history_from_db(symbol: str, period: str = "1y") -> list[dict]:
    from backend.database import get_conn
    days_map = {"1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730, "5y": 1825}
    days = days_map.get(period, 365)
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT date, open, high, low, close, volume
        FROM ohlc
        WHERE symbol = ?
          AND date >= date('now', ?)
        ORDER BY date
        """,
        (symbol.upper(), f"-{days} day"),
    ).fetchall()
    conn.close()
    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
        for r in rows
    ]


def _stock_news_from_db(symbol: str, limit: int = 20) -> list[dict]:
    from backend.database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT n.title, n.url, n.source, n.published_utc
        FROM news_raw n
        JOIN news_aligned na
          ON na.news_id = n.id
        LEFT JOIN layer1_results lr
          ON lr.news_id = n.id
         AND lr.symbol = na.symbol
        WHERE na.symbol = ?
          AND lower(COALESCE(lr.relevance, 'relevant')) = 'relevant'
        GROUP BY n.id
        ORDER BY n.published_utc DESC
        LIMIT ?
        """,
        (symbol.upper(), limit),
    ).fetchall()
    conn.close()
    return [
        {
            "title": r[0],
            "url": r[1],
            "source": r[2],
            "published_utc": r[3],
            "symbol": symbol.upper(),
        }
        for r in rows
    ]


# ── Market Overview ──────────────────────────────────────────────────

def _norm(r: dict) -> dict:
    """Always recompute change/change_percent from prev_close when available."""
    prev  = r.get("prev_close") or 0
    price = r.get("price") or r.get("last_price") or r.get("bid") or prev
    if prev:
        chg_pct = round((price - prev) / prev * 100, 4)
        chg     = round(price - prev, 4)
    else:
        chg_pct = r.get("change_percent")
        chg     = r.get("change")
    return {**r, "price": price, "change": chg, "change_percent": chg_pct}


@router.get("/indices")
def get_indices():
    rows = _call(lambda: _obb().equity.price.quote("SPY,QQQ,DIA", provider="yfinance"))
    if rows:
        return [_norm(r) for r in rows]
    return [_quote_from_yf(sym) for sym in ("SPY", "QQQ", "DIA")]


@router.get("/gainers")
def get_gainers():
    rows = _call(lambda: _obb().equity.discovery.gainers(provider="yfinance"))
    return rows or _overview_from_yf("gainers")


@router.get("/losers")
def get_losers():
    rows = _call(lambda: _obb().equity.discovery.losers(provider="yfinance"))
    return rows or _overview_from_yf("losers")


@router.get("/active")
def get_active():
    rows = _call(lambda: _obb().equity.discovery.active(provider="yfinance"))
    return rows or _overview_from_yf("active")


@router.get("/news")
def get_market_news(limit: int = 20):
    # No free world news provider — aggregate company news from major stocks
    symbols = "AAPL,MSFT,NVDA,TSLA,AMZN,GOOGL,META,SPY"
    rows = _call(lambda: _obb().news.company(symbols, provider="yfinance", limit=limit))
    return rows or _market_news_from_yf(limit=limit) or _market_news_from_db(limit=limit)


# ── Stock Detail ─────────────────────────────────────────────────────

@router.get("/stock/{symbol}/quote")
def get_quote(symbol: str):
    rows = _call(lambda: _obb().equity.price.quote(symbol.upper(), provider="yfinance"))
    if rows:
        return [_norm(r) for r in rows]
    return [_quote_from_yf(symbol)]


@router.get("/stock/{symbol}/historical")
def get_historical(symbol: str, period: str = "1y"):
    days_map = {"1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730, "5y": 1825}
    days = days_map.get(period, 365)
    end   = date.today()
    start = end - timedelta(days=days)
    rows = _call(lambda: _obb().equity.price.historical(
        symbol.upper(), start_date=str(start), end_date=str(end), provider="yfinance"
    ))
    return rows or _history_from_yf(symbol, period=period) or _history_from_db(symbol, period=period)


@router.get("/stock/{symbol}/profile")
def get_profile(symbol: str):
    rows = _call(lambda: _obb().equity.profile(symbol.upper(), provider="yfinance"))
    if rows:
        return rows
    try:
        info = _yf_ticker(symbol).info or {}
        return [{
            "symbol": symbol.upper(),
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "website": info.get("website"),
            "description": info.get("longBusinessSummary"),
            "employees": info.get("fullTimeEmployees"),
        }]
    except Exception as e:
        logger.error(f"Profile fallback error: {e}")
        return []


@router.get("/stock/{symbol}/metrics")
def get_metrics(symbol: str):
    try:
        import yfinance as yf
        info = yf.Ticker(symbol.upper()).info or {}
        dy  = info.get("dividendYield")           # pct form (0.42 = 0.42%)
        dy5 = info.get("fiveYearAvgDividendYield") # pct form (0.52 = 0.52%)
        return [{
            "symbol": symbol.upper(),
            # Valuation
            "market_cap":              info.get("marketCap"),
            "pe_ratio":                info.get("trailingPE"),
            "forward_pe":              info.get("forwardPE"),
            "peg_ratio_ttm":           info.get("trailingPegRatio"),
            "price_to_book":           info.get("priceToBook"),
            "price_to_sales_ratio":    info.get("priceToSalesTrailing12Months"),
            "enterprise_value":        info.get("enterpriseValue"),
            "enterprise_to_ebitda":    info.get("enterpriseToEbitda"),
            "enterprise_to_revenue":   info.get("enterpriseToRevenue"),
            # Profitability (decimal form: 0.47 = 47%)
            "gross_margin":            info.get("grossMargins"),
            "operating_margin":        info.get("operatingMargins"),
            "ebitda_margin":           info.get("ebitdaMargins"),
            "profit_margin":           info.get("profitMargins"),
            "return_on_assets":        info.get("returnOnAssets"),
            "return_on_equity":        info.get("returnOnEquity"),
            "eps":                     info.get("trailingEps"),
            "forward_eps":             info.get("forwardEps"),
            # Growth (decimal form: 0.18 = 18%)
            "earnings_growth":         info.get("earningsGrowth"),
            "revenue_growth":          info.get("revenueGrowth"),
            "beta":                    info.get("beta"),
            # Financial Health
            "debt_to_equity":          info.get("debtToEquity"),
            "quick_ratio":             info.get("quickRatio"),
            "current_ratio":           info.get("currentRatio"),
            "total_debt":              info.get("totalDebt"),
            "cash_and_cash_equivalents": info.get("totalCash"),
            "free_cash_flow":          info.get("freeCashflow"),
            # Dividend — normalize pct→decimal so fmtPct works uniformly
            "dividend_yield":          dy  / 100 if dy  is not None else None,
            "dividend_yield_5y_avg":   dy5 / 100 if dy5 is not None else None,
            "payout_ratio":            info.get("payoutRatio"),
            "dividend_per_share":      info.get("dividendRate"),
        }]
    except Exception as e:
        logger.error(f"Metrics yf.info error: {e}")
        raise HTTPException(500, str(e))


@router.get("/stock/{symbol}/peers")
def get_peers(symbol: str):
    try:
        import yfinance as yf
        import math
        sym = symbol.upper()

        # Step 1: get sector/industry of target
        target_info = yf.Ticker(sym).info or {}
        sector   = target_info.get("sector")
        industry = target_info.get("industry")
        mktcap   = target_info.get("marketCap") or 0

        # Step 2: find peers via finviz screener (same sector, similar mktcap range)
        SECTOR_MAP = {
            "Technology":             "technology",
            "Healthcare":             "healthcare",
            "Financial Services":     "financial",
            "Consumer Cyclical":      "consumer_cyclical",
            "Consumer Defensive":     "consumer_defensive",
            "Communication Services": "communication_services",
            "Industrials":            "industrials",
            "Basic Materials":        "materials",
            "Real Estate":            "real_estate",
            "Utilities":              "utilities",
            "Energy":                 "energy",
        }
        peer_syms: list[str] = []
        try:
            import os, requests
            fmp_key = os.getenv("FMP_API_KEY", "")
            resp = requests.get(
                f"https://financialmodelingprep.com/stable/stock-peers?symbol={sym}&apikey={fmp_key}",
                timeout=10,
            )
            data = resp.json()
            # Response: [{"symbol": "GOOGL", "companyName": "...", "price": ..., "mktCap": ...}, ...]
            if isinstance(data, list) and data and "symbol" in data[0]:
                peer_syms = [r["symbol"] for r in data if r.get("symbol") and r["symbol"] != sym][:9]
        except Exception as e:
            logger.warning(f"FMP peers failed: {e}")

        # Fallback to finviz screener if FMP returned nothing
        if not peer_syms:
            try:
                fv_sector = SECTOR_MAP.get(sector, "") if sector else ""
                screener_rows = _call(lambda: _obb().equity.screener(
                    provider="finviz",
                    sector=fv_sector if fv_sector else None,
                    limit=100,
                ))
                industry_matches = [r for r in screener_rows if r.get("industry") == industry and r.get("symbol") != sym]
                candidates = industry_matches if len(industry_matches) >= 3 else screener_rows
                if mktcap:
                    candidates.sort(key=lambda r: abs((r.get("market_cap") or 0) - mktcap))
                for r in candidates:
                    s = r.get("symbol", "")
                    if s and s != sym:
                        peer_syms.append(s)
                    if len(peer_syms) >= 9:
                        break
            except Exception as e:
                logger.warning(f"Peers screener fallback failed: {e}")

        all_syms = [sym] + peer_syms

        # Step 3: fetch metrics for each
        rows = []
        for s in all_syms:
            try:
                info = yf.Ticker(s).info or {} if s != sym else target_info
                mc = info.get("marketCap")
                rows.append({
                    "symbol":           s,
                    "name":             info.get("longName") or info.get("shortName"),
                    "price":            info.get("currentPrice") or info.get("regularMarketPrice"),
                    "market_cap":       mc,
                    "pe_ratio":         info.get("trailingPE"),
                    "forward_pe":       info.get("forwardPE"),
                    "price_to_book":    info.get("priceToBook"),
                    "profit_margin":    info.get("profitMargins"),
                    "revenue_growth":   info.get("revenueGrowth"),
                    "return_on_equity": info.get("returnOnEquity"),
                    "debt_to_equity":   info.get("debtToEquity"),
                    "sector":           info.get("sector"),
                    "industry":         info.get("industry"),
                    "is_target":        s == sym,
                })
            except Exception:
                pass

        # Sort peers by mktcap proximity to target
        target_row = next((r for r in rows if r["is_target"]), None)
        peers_only = [r for r in rows if not r["is_target"]]
        if mktcap:
            peers_only.sort(key=lambda r: abs((r["market_cap"] or 0) - mktcap))
        return ([target_row] if target_row else []) + peers_only[:9]

    except Exception as e:
        logger.error(f"Peers error: {e}")
        raise HTTPException(500, str(e))


@router.get("/stock/{symbol}/income")
def get_income(symbol: str, period: str = "annual"):
    rows = _call(lambda: _obb().equity.fundamental.income(symbol.upper(), period=period, provider="yfinance"))
    if rows:
        return rows
    try:
        t = _yf_ticker(symbol)
        df = t.financials if period == "annual" else t.quarterly_financials
        if df is None or df.empty:
            return []
        out = []
        for col in df.columns:
            rec = {"date": str(col.date() if hasattr(col, "date") else col)}
            for idx, val in df[col].items():
                rec[str(idx)] = _json_safe(val)
            out.append(rec)
        return out
    except Exception as e:
        logger.error(f"Income fallback error: {e}")
        return []


@router.get("/stock/{symbol}/balance")
def get_balance(symbol: str, period: str = "annual"):
    rows = _call(lambda: _obb().equity.fundamental.balance(symbol.upper(), period=period, provider="yfinance"))
    if rows:
        return rows
    try:
        t = _yf_ticker(symbol)
        df = t.balance_sheet if period == "annual" else t.quarterly_balance_sheet
        if df is None or df.empty:
            return []
        out = []
        for col in df.columns:
            rec = {"date": str(col.date() if hasattr(col, "date") else col)}
            for idx, val in df[col].items():
                rec[str(idx)] = _json_safe(val)
            out.append(rec)
        return out
    except Exception as e:
        logger.error(f"Balance fallback error: {e}")
        return []


@router.get("/stock/{symbol}/cash")
def get_cash(symbol: str, period: str = "annual"):
    rows = _call(lambda: _obb().equity.fundamental.cash(symbol.upper(), period=period, provider="yfinance"))
    if rows:
        return rows
    try:
        t = _yf_ticker(symbol)
        df = t.cashflow if period == "annual" else t.quarterly_cashflow
        if df is None or df.empty:
            return []
        out = []
        for col in df.columns:
            rec = {"date": str(col.date() if hasattr(col, "date") else col)}
            for idx, val in df[col].items():
                rec[str(idx)] = _json_safe(val)
            out.append(rec)
        return out
    except Exception as e:
        logger.error(f"Cash fallback error: {e}")
        return []


@router.get("/stock/{symbol}/consensus")
def get_consensus(symbol: str):
    rows = _call(lambda: _obb().equity.estimates.consensus(symbol.upper(), provider="yfinance"))
    return rows or _consensus_from_yf(symbol)


@router.get("/stock/{symbol}/targets")
def get_targets(symbol: str):
    rows = _call(lambda: _obb().equity.estimates.price_target(symbol.upper(), provider="finviz"))
    return rows or _targets_from_yf(symbol)


@router.get("/stock/{symbol}/institutional")
def get_institutional(symbol: str):
    try:
        import yfinance as yf
        import math
        ticker = yf.Ticker(symbol.upper())

        results = []

        # Major holders summary — index = label, "Value" column = value
        mh = ticker.major_holders
        if mh is not None and not mh.empty:
            for idx, row in mh.iterrows():
                v = row.iloc[0]
                if hasattr(v, 'item'): v = v.item()
                results.append({"type": "summary", "label": str(idx), "value": v})

        # Top institutional holders
        ih = ticker.institutional_holders
        if ih is not None and not ih.empty:
            for _, row in ih.head(15).iterrows():
                rec = {}
                for k, v in row.items():
                    if hasattr(v, 'item'): v = v.item()
                    if hasattr(v, 'isoformat'): v = v.isoformat()
                    if isinstance(v, float) and math.isnan(v): v = None
                    rec[str(k)] = v
                rec["type"] = "holder"
                results.append(rec)

        return results
    except Exception as e:
        logger.error(f"Institutional error: {e}")
        return []


@router.get("/stock/{symbol}/filings")
def get_filings(symbol: str):
    try:
        import requests, re
        headers = {"User-Agent": "IvyTrader research@ivytrader.com"}
        sym = symbol.upper()

        # Step 1: get CIK from ticker
        r = requests.get(
            f"https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK={sym}&type=&dateb=&owner=include&count=1&search_text=&action=getcompany&output=atom",
            headers=headers, timeout=10,
        )
        cik_match = re.search(r"CIK=(\d+)", r.text)
        if not cik_match:
            return []
        cik_str = cik_match.group(1).zfill(10)
        cik_int = int(cik_match.group(1))

        # Step 2: get recent filings from EDGAR submissions API
        sub = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik_str}.json",
            headers=headers, timeout=10,
        )
        recent = sub.json().get("filings", {}).get("recent", {})
        forms   = recent.get("form", [])
        dates   = recent.get("filingDate", [])
        docs    = recent.get("primaryDocument", [])
        accs    = recent.get("accessionNumber", [])
        descs   = recent.get("primaryDocDescription", [])

        KEEP = {"10-K", "10-Q", "8-K", "DEF 14A", "13F-HR", "SC 13G", "SC 13D"}
        rows = []
        for form, date, doc, acc, desc in zip(forms, dates, docs, accs, descs):
            if form not in KEEP:
                continue
            acc_clean = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
            rows.append({
                "type":  form,
                "title": desc or form,
                "date":  date,
                "url":   url,
            })
            if len(rows) >= 40:
                break
        return rows
    except Exception as e:
        logger.error(f"Filings error: {e}")
        raise HTTPException(500, str(e))


@router.get("/filing-text")
def get_filing_text(url: str):
    """Proxy + strip HTML from an SEC EDGAR document URL, return plain text."""
    import requests, re
    from urllib.parse import urlparse, urljoin

    # Validate it's an SEC EDGAR URL
    parsed = urlparse(url)
    if parsed.netloc not in ("www.sec.gov", "sec.gov"):
        raise HTTPException(400, "Only SEC EDGAR URLs are allowed")

    # SEC requires a specific User-Agent format
    headers = {
        "User-Agent": "IvyTrader research@ivytrader.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    def strip_html(html: str) -> str:
        # 1. Remove the iXBRL header block entirely (contains raw XBRL metadata, not readable)
        text = re.sub(r'<ix:header[^>]*>.*?</ix:header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 2. Remove style/script blocks
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # 3. If there's a <body> tag, use only that section
        body_match = re.search(r'<body[^>]*>(.*?)</body>', text, flags=re.DOTALL | re.IGNORECASE)
        if body_match:
            text = body_match.group(1)
        # 4. Strip iXBRL namespace open tags but preserve their text content
        text = re.sub(r'<ix:\w+[^>]*/>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?ix:\w+[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?xbrli:\w+[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?link:\w+[^>]*>', '', text, flags=re.IGNORECASE)
        # 5. Convert block elements to newlines before stripping
        text = re.sub(r'<(?:br|p|div|tr|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<(?:td|th)[^>]*>', ' | ', text, flags=re.IGNORECASE)
        # 6. Strip remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # 7. Decode HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))) if int(m.group(1)) < 0x110000 else '', text)
        text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)) if int(m.group(1), 16) < 0x110000 else '', text)
        # 8. Collapse whitespace / blank lines
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\n[ \t]+', '\n', text)
        text = re.sub(r' \| \n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    try:
        # First try: fetch the document directly
        r = requests.get(url, headers=headers, timeout=25)
        fetch_error = None if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception as e:
        r = None
        fetch_error = str(e)

    # If direct fetch failed, try the full-submission .txt from EDGAR archive
    text = ""
    source_url = url
    if r is None or r.status_code != 200:
        # Derive the full-submission text URL:
        # .../edgar/data/{cik}/{acc_nodash}/{doc}.htm → .../edgar/data/{cik}/{acc_nodash}.txt
        m = re.match(r'(https://www\.sec\.gov/Archives/edgar/data/\d+/(\d+))/', url)
        if m:
            txt_url = f"https://www.sec.gov/Archives/edgar/data/{m.group(0).split('/')[-2]}/{m.group(2)}.txt"
            try:
                r2 = requests.get(txt_url, headers=headers, timeout=25)
                if r2.status_code == 200:
                    r = r2
                    source_url = txt_url
                    fetch_error = None
            except Exception:
                pass

    if r is None or r.status_code != 200:
        error_msg = fetch_error or f"HTTP {r.status_code if r else 'no response'}"
        logger.error(f"Filing fetch failed for {url}: {error_msg}")
        raise HTTPException(502, f"无法获取文件：{error_msg}")

    content_type = r.headers.get("content-type", "")
    is_html = "html" in content_type or url.endswith((".htm", ".html"))

    if is_html:
        r.encoding = r.apparent_encoding or "utf-8"
        text = strip_html(r.text)
    else:
        r.encoding = r.apparent_encoding or "utf-8"
        raw = r.text
        # Full submission .txt files have a header block — skip it if present
        doc_start = raw.find("<DOCUMENT>")
        if doc_start != -1:
            # Extract just the first document's text section
            text_start = raw.find("<TEXT>", doc_start)
            text_end   = raw.find("</TEXT>", doc_start)
            if text_start != -1 and text_end != -1:
                inner = raw[text_start + 6 : text_end]
                text = strip_html(inner) if "<html" in inner.lower() else inner.strip()
            else:
                text = raw[doc_start:doc_start + 120000].strip()
        else:
            text = raw.strip()

    if not text:
        raise HTTPException(502, "文件内容为空或格式无法解析")

    truncated = len(text) > 80000
    text = text[:80000]
    return {"text": text, "truncated": truncated, "url": source_url}


@router.get("/stock/{symbol}/insiders")
def get_insiders(symbol: str):
    rows = _call(lambda: _obb().equity.ownership.insider_trading(symbol.upper(), provider="sec"))
    if rows:
        return rows
    try:
        t = _yf_ticker(symbol)
        df = getattr(t, "insider_transactions", None)
        if df is None or df.empty:
            return []
        return df.head(20).where(df.notna(), None).to_dict(orient="records")
    except Exception as e:
        logger.error(f"Insiders fallback error: {e}")
        return []


@router.get("/stock/{symbol}/news")
def get_stock_news(symbol: str, limit: int = 20):
    rows = _call(lambda: _obb().news.company(symbol.upper(), provider="yfinance", limit=limit))
    if rows:
        return rows
    try:
        out = []
        for item in (_yf_ticker(symbol).news or [])[:limit]:
            content = item.get("content") if isinstance(item, dict) else None
            out.append({
                "title": item.get("title") or (content or {}).get("title"),
                "url": item.get("link") or item.get("url") or (content or {}).get("canonicalUrl", {}).get("url"),
                "source": item.get("publisher") or ((content or {}).get("provider") or {}).get("displayName"),
                "published_utc": item.get("providerPublishTime") or (content or {}).get("pubDate"),
                "symbol": symbol.upper(),
            })
        out = [r for r in out if r.get("title") or r.get("url")]
        return out or _stock_news_from_db(symbol, limit=limit)
    except Exception as e:
        logger.error(f"Stock news fallback error: {e}")
        return _stock_news_from_db(symbol, limit=limit)


@router.get("/stock/{symbol}/options")
def get_options(symbol: str, expiration: Optional[str] = None, option_type: str = "call"):
    try:
        if _obb() is not None:
            kwargs: dict = {"provider": "cboe"}
            if expiration:
                kwargs["expiration"] = expiration
            r = _obb().derivatives.options.chains(symbol.upper(), **kwargs)
            df = r.results.dataframe
            df = df[df["option_type"] == option_type].copy()
            if expiration:
                df = df[df["expiration"].astype(str) == expiration]
            else:
                exps = sorted(df["expiration"].unique())
                if exps:
                    df = df[df["expiration"] == exps[0]]
            df = df.sort_values("strike").head(50)
            records = []
            for _, row in df.iterrows():
                rec = {}
                for k, v in row.items():
                    import math
                    if isinstance(v, float) and math.isnan(v):
                        rec[k] = None
                    elif hasattr(v, 'isoformat'):
                        rec[k] = v.isoformat()
                    else:
                        rec[k] = v
                records.append(rec)
            return records

        t = _yf_ticker(symbol)
        exps = list(getattr(t, "options", []) or [])
        if not exps:
            return []
        exp = expiration if expiration in exps else exps[0]
        chain = t.option_chain(exp)
        df = chain.calls if option_type == "call" else chain.puts
        if df is None or df.empty:
            return []
        df = df.head(50).copy()
        df["expiration"] = exp
        return df.where(df.notna(), None).to_dict(orient="records")
    except Exception as e:
        logger.error(f"Options error: {e}")
        return []


# ── Screener ─────────────────────────────────────────────────────────

@router.get("/screener")
def get_screener(
    sector:     Optional[str]   = None,
    mktcap_min: Optional[float] = None,
    mktcap_max: Optional[float] = None,
    price_min:  Optional[float] = None,
    price_max:  Optional[float] = None,
    volume_min: Optional[int]   = None,
    beta_min:   Optional[float] = None,
    beta_max:   Optional[float] = None,
    limit: int = Query(100, le=500),
):
    SECTOR_MAP = {
        "Technology":             "technology",
        "Healthcare":             "healthcare",
        "Financial Services":     "financial",
        "Financial":              "financial",
        "Consumer Cyclical":      "consumer_cyclical",
        "Consumer Defensive":     "consumer_defensive",
        "Communication Services": "communication_services",
        "Industrials":            "industrials",
        "Energy":                 "energy",
        "Basic Materials":        "materials",
        "Real Estate":            "real_estate",
        "Utilities":              "utilities",
    }
    kwargs: dict = {"provider": "finviz", "limit": limit}
    if sector:     kwargs["sector"]     = SECTOR_MAP.get(sector, sector)
    if mktcap_min: kwargs["mktcap_min"] = mktcap_min
    if mktcap_max: kwargs["mktcap_max"] = mktcap_max
    if price_min:  kwargs["price_min"]  = price_min
    if price_max:  kwargs["price_max"]  = price_max
    if volume_min: kwargs["volume_min"] = volume_min
    if beta_min:   kwargs["beta_min"]   = beta_min
    if beta_max:   kwargs["beta_max"]   = beta_max
    rows = _call(lambda: _obb().equity.screener(**kwargs))
    return rows


# ── Calendar ─────────────────────────────────────────────────────────

@router.get("/calendar/earnings")
def get_earnings(start_date: Optional[str] = None, end_date: Optional[str] = None):
    start_date = start_date or str(date.today())
    end_date   = end_date   or str(date.today() + timedelta(days=14))
    return _call(lambda: _obb().equity.calendar.earnings(start_date=start_date, end_date=end_date, provider="nasdaq"))


@router.get("/calendar/ipo")
def get_ipo(start_date: Optional[str] = None, end_date: Optional[str] = None):
    start_date = start_date or str(date.today())
    end_date   = end_date   or str(date.today() + timedelta(days=30))
    return _call(lambda: _obb().equity.calendar.ipo(start_date=start_date, end_date=end_date, provider="nasdaq"))


@router.get("/calendar/dividends")
def get_dividends(start_date: Optional[str] = None, end_date: Optional[str] = None):
    start_date = start_date or str(date.today())
    end_date   = end_date   or str(date.today() + timedelta(days=14))
    return _call(lambda: _obb().equity.calendar.dividend(start_date=start_date, end_date=end_date, provider="nasdaq"))
