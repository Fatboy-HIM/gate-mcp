"""Read-only MCP server wrapping Gate.io PUBLIC USDT-futures market data.

No API keys, no trading, no account endpoints. Only public GET requests.
Run:  python server.py            (listens on 0.0.0.0:$PORT, default 8000, path /mcp)
Env:  GATE_BASE_URL  default https://api.gateio.ws/api/v4
      PORT           default 8000
      AUTH_TOKEN     optional; if set, clients must send  Authorization: Bearer <token>
"""
import os
import time
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

BASE = os.environ.get("GATE_BASE_URL", "https://api.gateio.ws/api/v4").rstrip("/")
SETTLE = "usdt"
INTERVAL_SECONDS = {
    "10s": 10, "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "8h": 28800, "1d": 86400, "7d": 604800,
}

mcp = FastMCP(
    "gate-futures-public",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)


def _get(path: str, params: dict | None = None):
    r = httpx.get(
        f"{BASE}{path}",
        params=params,
        headers={"Accept": "application/json", "User-Agent": "gate-public-mcp/1.0"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@mcp.tool()
def get_candles(contract: str, interval: str = "4h", limit: int = 200,
                closed_only: bool = True) -> dict:
    """Candles for a Gate USDT perpetual, OLDEST-first, UTC bar-open times.

    contract: e.g. BTC_USDT, ETH_USDT, SOL_USDT, LINK_USDT, ADA_USDT, ONDO_USDT.
    interval: 10s,1m,5m,15m,30m,1h,4h,8h,1d,7d.   limit: 1-2000.
    closed_only: drop the still-forming newest bar (default true).
    Fields: open_utc, o, h, l, c, volume_contracts, volume_usd (quote volume).
    """
    if interval not in INTERVAL_SECONDS:
        return {"error": f"interval must be one of {sorted(INTERVAL_SECONDS)}"}
    limit = max(1, min(int(limit), 2000))
    # ask for one extra so dropping the live bar still leaves `limit` bars
    raw = _get(f"/futures/{SETTLE}/candlesticks",
               {"contract": contract, "interval": interval, "limit": min(limit + 1, 2000)})
    raw.sort(key=lambda x: int(x["t"]))
    step = INTERVAL_SECONDS[interval]
    now = int(time.time())
    bars, dropped = [], 0
    for x in raw:
        t = int(x["t"])
        if closed_only and t + step > now:
            dropped += 1
            continue
        bars.append({
            "open_utc": _iso(t), "o": x["o"], "h": x["h"], "l": x["l"], "c": x["c"],
            "volume_contracts": x.get("v"), "volume_usd": x.get("sum"),
        })
    bars = bars[-limit:]
    gaps = sum(
        1 for a, b in zip(bars, bars[1:])
        if (datetime.strptime(b["open_utc"], "%Y-%m-%dT%H:%M:%SZ")
            - datetime.strptime(a["open_utc"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() != step
    )
    return {"venue": "Gate USDT perp", "contract": contract, "interval": interval,
            "count": len(bars), "live_bar_dropped": dropped, "continuity_gaps": gaps,
            "server_time_utc": _iso(now), "candles": bars}


@mcp.tool()
def get_ticker(contract: str) -> dict:
    """Last price, mark price, index price, best bid/ask, 24h quote volume (USD), funding rate."""
    d = _get(f"/futures/{SETTLE}/tickers", {"contract": contract})
    t = d[0] if isinstance(d, list) and d else d
    if isinstance(t, dict) and t.get("volume_24h_quote"):
        t["volume_24h_usd_gate"] = float(t["volume_24h_quote"])  # USDT-quoted, Gate venue only
        if t.get("highest_bid") and t.get("lowest_ask"):
            b, a = float(t["highest_bid"]), float(t["lowest_ask"])
            t["spread_pct"] = round((a - b) / ((a + b) / 2) * 100, 4)
    return t


@mcp.tool()
def get_order_book(contract: str, depth: int = 20) -> dict:
    """Order book snapshot plus computed best bid/ask, mid and spread percent."""
    d = _get(f"/futures/{SETTLE}/order_book", {"contract": contract, "limit": max(1, min(depth, 50))})
    bid = float(d["bids"][0]["p"]) if d.get("bids") else None
    ask = float(d["asks"][0]["p"]) if d.get("asks") else None
    out = {"contract": contract, "best_bid": bid, "best_ask": ask,
           "bids": d.get("bids"), "asks": d.get("asks")}
    if bid and ask:
        mid = (bid + ask) / 2
        out.update(mid=mid, spread_pct=round((ask - bid) / mid * 100, 4))
    return out


@mcp.tool()
def get_contract(contract: str) -> dict:
    """Contract details: tick size, contract multiplier, funding interval, leverage limits, open interest."""
    return _get(f"/futures/{SETTLE}/contracts/{contract}")


@mcp.tool()
def get_funding_rate_history(contract: str, limit: int = 20) -> list:
    """Recent funding-rate history (newest first)."""
    return _get(f"/futures/{SETTLE}/funding_rate", {"contract": contract, "limit": max(1, min(limit, 100))})


if __name__ == "__main__":
    token = os.environ.get("AUTH_TOKEN")
    if token:
        import uvicorn
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import PlainTextResponse

        class Bearer(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.headers.get("authorization") != f"Bearer {token}":
                    return PlainTextResponse("unauthorized", status_code=401)
                return await call_next(request)

        app = mcp.streamable_http_app()
        app.add_middleware(Bearer)
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
    else:
        mcp.run(transport="streamable-http")
