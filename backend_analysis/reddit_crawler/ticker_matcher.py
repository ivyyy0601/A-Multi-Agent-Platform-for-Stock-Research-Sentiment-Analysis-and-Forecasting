"""
Match Reddit post text to ticker symbols using aliases.
"""
import re
from typing import List, Optional

# Ticker aliases: maps ticker → list of keywords to look for in post text
TICKER_ALIASES = {
    "AAPL": ["aapl", "apple", "iphone", "ipad", "macbook", "tim cook", "app store"],
    "MSFT": ["msft", "microsoft", "azure", "office 365", "xbox", "copilot", "satya nadella"],
    "NVDA": ["nvda", "nvidia", "cuda", "geforce", "jensen huang", "blackwell", "h100", "rtx"],
    "GOOGL": ["googl", "goog", "google", "alphabet", "gemini", "waymo", "sundar pichai", "youtube"],
    "AMZN": ["amzn", "amazon", "aws", "prime", "jeff bezos", "andy jassy"],
    "META": ["meta", "facebook", "instagram", "whatsapp", "zuckerberg", "zuck", "threads", "oculus"],
    "TSLA": ["tsla", "tesla", "elon", "musk", "cybertruck", "model 3", "model y", "model s", "supercharger"],
    "AVGO": ["avgo", "broadcom"],
    "AMD": ["amd", "advanced micro", "ryzen", "radeon", "lisa su", "epyc"],
    "MU": ["mu", "micron", "dram", "nand flash"],
    "TSM": ["tsm", "tsmc", "taiwan semiconductor"],
    "ASML": ["asml", "euv", "lithography"],
    "INTC": ["intc", "intel", "pat gelsinger"],
    "QCOM": ["qcom", "qualcomm", "snapdragon"],
    "AMAT": ["amat", "applied materials"],
    "LRCX": ["lrcx", "lam research"],
    "ADI": ["adi", "analog devices"],
    "NXPI": ["nxpi", "nxp semiconductors"],
    "ARM": ["arm holdings", "arm chip"],
    "TXN": ["txn", "texas instruments"],
    "ORCL": ["orcl", "oracle", "larry ellison"],
    "CRM": ["crm", "salesforce", "marc benioff"],
    "NOW": ["servicenow", "now platform"],
    "ADBE": ["adbe", "adobe", "photoshop", "illustrator", "figma"],
    "PLTR": ["pltr", "palantir", "alex karp"],
    "PANW": ["panw", "palo alto networks"],
    "CRWD": ["crwd", "crowdstrike"],
    "SNOW": ["snow", "snowflake"],
    "MDB": ["mdb", "mongodb"],
    "SHOP": ["shop", "shopify"],
    "JPM": ["jpm", "jpmorgan", "jp morgan", "jamie dimon"],
    "BAC": ["bac", "bank of america", "bofa"],
    "GS": ["gs", "goldman sachs"],
    "MS": ["morgan stanley"],
    "WFC": ["wfc", "wells fargo"],
    "C": ["citigroup", "citi bank"],
    "V": ["visa inc", "visa card"],
    "MA": ["mastercard"],
    "PYPL": ["pypl", "paypal"],
    "AXP": ["axp", "american express", "amex"],
    "BRK.B": ["berkshire", "warren buffett", "brk"],
    "SQ": ["block inc", "square payments", "cash app"],
    "SOFI": ["sofi technologies"],
    "BLK": ["blk", "blackrock", "larry fink"],
    "CME": ["cme group"],
    "ICE": ["intercontinental exchange"],
    "SCHW": ["schw", "charles schwab"],
    "LLY": ["lly", "eli lilly", "mounjaro", "zepbound", "ozempic competitor"],
    "NVO": ["nvo", "novo nordisk", "ozempic", "wegovy", "semaglutide"],
    "JNJ": ["jnj", "johnson & johnson", "johnson johnson"],
    "PFE": ["pfe", "pfizer"],
    "MRK": ["mrk", "merck", "keytruda"],
    "ABBV": ["abbv", "abbvie", "humira", "skyrizi"],
    "BMY": ["bmy", "bristol myers", "bristol-myers"],
    "UNH": ["unh", "unitedhealth", "united health"],
    "ISRG": ["isrg", "intuitive surgical", "da vinci"],
    "TMO": ["tmo", "thermo fisher"],
    "DHR": ["dhr", "danaher"],
    "MDT": ["mdt", "medtronic"],
    "ABT": ["abt", "abbott"],
    "WMT": ["wmt", "walmart", "wal-mart"],
    "COST": ["cost", "costco"],
    "HD": ["home depot"],
    "TGT": ["tgt", "target store"],
    "LOW": ["lowes", "lowe's"],
    "NKE": ["nke", "nike"],
    "MCD": ["mcd", "mcdonald", "big mac"],
    "KO": ["coca-cola", "coke"],
    "PEP": ["pep", "pepsi", "pepsico"],
    "SBUX": ["sbux", "starbucks"],
    "LULU": ["lulu", "lululemon"],
    "BKNG": ["bkng", "booking holdings", "booking.com", "priceline"],
    "ABNB": ["abnb", "airbnb"],
    "UBER": ["uber"],
    "DASH": ["doordash", "door dash"],
    "XOM": ["xom", "exxon", "exxonmobil"],
    "CVX": ["cvx", "chevron"],
    "COP": ["conocophillips"],
    "SLB": ["slb", "schlumberger"],
    "OXY": ["oxy", "occidental petroleum"],
    "GE": ["ge aerospace", "general electric"],
    "CAT": ["cat", "caterpillar"],
    "BA": ["boeing"],
    "LMT": ["lmt", "lockheed martin"],
    "HON": ["honeywell"],
    "DE": ["john deere", "deere"],
    "UPS": ["ups", "united parcel"],
    "FDX": ["fdx", "fedex"],
    "F": ["ford motor", "ford f-150"],
    "GM": ["general motors"],
    "VZ": ["verizon"],
    "T": ["at&t"],
    "NFLX": ["nflx", "netflix"],
    "DIS": ["disney", "marvel", "pixar", "espn", "hulu"],
    "CMCSA": ["cmcsa", "comcast", "nbcuniversal"],
    "AMT": ["american tower"],
    "PLD": ["prologis"],
    "EQIX": ["equinix"],
    "MRVL": ["marvell technology"],
    "KLAC": ["kla corporation"],
    "SNPS": ["synopsys"],
    "CDNS": ["cadence design"],
    "MPWR": ["monolithic power"],
    "ON": ["onsemi", "on semiconductor"],
    "ZS": ["zscaler"],
    "DDOG": ["datadog"],
    "NET": ["cloudflare"],
    "HUBS": ["hubspot"],
    "GTLB": ["gitlab"],
    "OKTA": ["okta"],
    "TTD": ["the trade desk"],
    "COIN": ["coinbase"],
    "HOOD": ["robinhood"],
    "IBKR": ["interactive brokers"],
    "NDAQ": ["nasdaq inc"],
    "REGN": ["regeneron"],
    "VRTX": ["vertex pharmaceuticals"],
    "GILD": ["gilead"],
    "BIIB": ["biogen"],
    "MRNA": ["moderna", "mrna vaccine"],
    "BSX": ["boston scientific"],
    "EW": ["edwards lifesciences"],
    "ZBH": ["zimmer biomet"],
    "PTON": ["peloton"],
    "ETSY": ["etsy"],
    "CHWY": ["chewy"],
    "DKNG": ["draftkings"],
    "RTX": ["rtx", "raytheon"],
    "NOC": ["northrop grumman"],
    "LHX": ["l3harris"],
    "TDG": ["transdigm"],
    "GD": ["general dynamics"],
    "MMM": ["3m company"],
    "EMR": ["emerson electric"],
    "PH": ["parker hannifin"],
    "PSX": ["phillips 66"],
    "MPC": ["marathon petroleum"],
    "VLO": ["valero energy"],
    "WMB": ["williams companies"],
    "KMI": ["kinder morgan"],
    "CCI": ["crown castle"],
    "SBAC": ["sba communications"],
    "DLR": ["digital realty"],
    "O": ["realty income"],
    "SPG": ["simon property"],
    "RBLX": ["roblox"],
    "SNAP": ["snapchat", "snap inc"],
    "PINS": ["pinterest"],
    "ROKU": ["roku"],
    "ZM": ["zoom video"],
    "LYFT": ["lyft"],
    "RIVN": ["rivian"],
    "INTU": ["intuit", "turbotax", "quickbooks"],
    "VEEV": ["veeva systems"],
    "IDXX": ["idexx laboratories"],
    "ANSS": ["ansys"],
    "MNDY": ["monday.com"],
    "BILL": ["bill.com"],
    "SMAR": ["smartsheet"],
    "DOCN": ["digitalocean"],
    "USB": ["us bancorp", "us bank"],
    "PNC": ["pnc financial"],
    "TFC": ["truist financial"],
    "RF": ["regions financial"],
    "FITB": ["fifth third"],
    "KEY": ["keycorp"],
    "HBAN": ["huntington bancshares"],
    "HCA": ["hca healthcare"],
    "CVS": ["cvs health", "cvs pharmacy"],
    "CI": ["cigna"],
    "HUM": ["humana"],
    "MCK": ["mckesson"],
    "IQV": ["iqvia"],
    "ILMN": ["illumina"],
    "CMG": ["chipotle"],
    "YUM": ["yum brands", "kfc", "taco bell", "pizza hut"],
    "DPZ": ["domino's", "dominos"],
    "QSR": ["restaurant brands", "burger king", "tim hortons"],
    "LIN": ["linde"],
    "APD": ["air products"],
    "SHW": ["sherwin-williams"],
    "ECL": ["ecolab"],
    "NEM": ["newmont"],
    "FCX": ["freeport-mcmoran", "freeport mcmoran"],
    "HAL": ["halliburton"],
    "BKR": ["baker hughes"],
    "DVN": ["devon energy"],
    "MRO": ["marathon oil"],
    "FANG": ["diamondback energy"],
    "CNC": ["centene"],
    "MOH": ["molina healthcare"],
    "WBA": ["walgreens"],
    "CAG": ["conagra"],
    "K": ["kellanova", "kellogg"],
    "GIS": ["general mills"],
    "CPB": ["campbell soup"],
    "MKC": ["mccormick"],
}

# Tickers that are very short / common words — require $ prefix to avoid false positives
STRICT_TICKERS = {"C", "F", "T", "K", "O", "ON", "V", "MA", "GS", "MS", "BA", "DE", "HD", "LOW"}


def find_tickers_in_text(text: str) -> List[str]:
    """
    Scan text and return list of matching tickers.
    Checks for $TICKER pattern first, then aliases.
    """
    if not text:
        return []
    text_lower = text.lower()
    matched = set()

    # 1. $TICKER pattern (most reliable)
    dollar_tickers = re.findall(r'\$([A-Z]{1,5}(?:\.[A-Z])?)', text.upper())
    for t in dollar_tickers:
        if t in TICKER_ALIASES:
            matched.add(t)

    # 2. Alias matching
    for ticker, aliases in TICKER_ALIASES.items():
        if ticker in STRICT_TICKERS:
            # Only match via $TICKER for ambiguous symbols
            continue
        for alias in aliases:
            if alias in text_lower:
                matched.add(ticker)
                break

    return list(matched)


def best_ticker_for_post(title: str, text: str = "") -> Optional[str]:
    """Return the single most likely ticker for a post (highest alias match count)."""
    combined = f"{title} {text}"
    tickers = find_tickers_in_text(combined)
    if not tickers:
        return None
    if len(tickers) == 1:
        return tickers[0]
    # If multiple, prefer the one with most alias hits
    scores = {}
    combined_lower = combined.lower()
    for t in tickers:
        scores[t] = sum(1 for alias in TICKER_ALIASES.get(t, []) if alias in combined_lower)
    return max(scores, key=scores.get)
