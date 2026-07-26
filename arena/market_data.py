"""Market data: daily prices via Yahoo Finance's public chart API, Stooq CSV as fallback.

Both sources are keyless. All fetches for one cycle go through a MarketData
instance which caches per ticker, so each symbol is fetched at most once.
"""

import csv
import io
import logging
import time

import requests

log = logging.getLogger(__name__)

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=3mo&interval=1d"
STOOQ_URL = "https://stooq.com/q/d/l/?s={ticker}.us&i=d"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) llm-arena/0.1"}


class Quote:
    """Latest price plus recent-return context for one ticker."""

    def __init__(self, ticker: str, closes: list[float]):
        if not closes:
            raise ValueError(f"no price history for {ticker}")
        self.ticker = ticker
        self.closes = closes
        self.price = closes[-1]

    def pct_change(self, days: int) -> float | None:
        if len(self.closes) <= days:
            return None
        prev = self.closes[-1 - days]
        if not prev:
            return None
        return (self.closes[-1] / prev - 1.0) * 100.0

    def summary(self) -> dict:
        def r(v):
            return round(v, 2) if v is not None else None

        return {
            "price": round(self.price, 2),
            "chg_1d_pct": r(self.pct_change(1)),
            "chg_5d_pct": r(self.pct_change(5)),
            "chg_1mo_pct": r(self.pct_change(21)),
        }


class MarketData:
    """Fetches and caches quotes. Subclass / replace `fetch` for tests."""

    def __init__(self, session: requests.Session | None = None, throttle_s: float = 0.4):
        self._session = session or requests.Session()
        self._cache: dict[str, Quote | None] = {}
        self._throttle_s = throttle_s

    def get(self, ticker: str) -> Quote | None:
        ticker = ticker.upper().strip()
        if ticker not in self._cache:
            self._cache[ticker] = self.fetch(ticker)
            time.sleep(self._throttle_s)
        return self._cache[ticker]

    def snapshot(self, tickers: list[str]) -> dict[str, dict]:
        out = {}
        for t in tickers:
            q = self.get(t)
            if q is not None:
                out[t.upper()] = q.summary()
        return out

    def fetch(self, ticker: str) -> Quote | None:
        for fn in (self._fetch_yahoo, self._fetch_stooq):
            try:
                closes = fn(ticker)
                if closes:
                    return Quote(ticker, closes)
            except Exception as e:  # noqa: BLE001 - fall through to next source
                log.warning("%s fetch via %s failed: %s", ticker, fn.__name__, e)
        log.error("no price available for %s from any source", ticker)
        return None

    def _fetch_yahoo(self, ticker: str) -> list[float]:
        resp = self._session.get(YAHOO_URL.format(ticker=ticker), headers=HEADERS, timeout=20)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        return [c for c in closes if c is not None]

    def _fetch_stooq(self, ticker: str) -> list[float]:
        resp = self._session.get(STOOQ_URL.format(ticker=ticker.lower()), headers=HEADERS, timeout=20)
        resp.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        closes = [float(r["Close"]) for r in rows if r.get("Close") not in (None, "", "N/D")]
        return closes[-66:]


class FixtureMarketData(MarketData):
    """Offline price source for tests and --dry-run: {ticker: [closes...]}."""

    def __init__(self, prices: dict[str, list[float]]):
        super().__init__(throttle_s=0.0)
        self._prices = {k.upper(): v for k, v in prices.items()}

    def fetch(self, ticker: str) -> Quote | None:
        closes = self._prices.get(ticker.upper())
        return Quote(ticker, closes) if closes else None
