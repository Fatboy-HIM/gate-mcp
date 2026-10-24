# Gate public futures MCP server (read-only)

Public market data only: candles, ticker, order book, contract info, funding history.
No API keys, no account or trading endpoints.

## Run locally
    pip install -r requirements.txt
    python server.py            # http://localhost:8000/mcp

## Deploy (needs a public HTTPS URL)
Any small host works (Render, Fly.io, Railway, a VPS behind Caddy/nginx).
- Start command: `python server.py`
- Env: `PORT` (host usually sets it), optional `GATE_BASE_URL` (default https://api.gateio.ws/api/v4;
  use https://fx-api.gateio.ws/api/v4 if that is the host your network can reach).
- Run it from a region where Gate's API is reachable (some regions are blocked).

Quick tunnel for testing from your own PC: `cloudflared tunnel --url http://localhost:8000`

## Add to Claude
claude.ai -> Settings -> Connectors -> Add custom connector -> URL `https://<your-host>/mcp`.
Custom connectors may be limited by plan or org admin settings.

Optional: set `AUTH_TOKEN` to require `Authorization: Bearer <token>`. Note claude.ai custom
connectors authenticate via OAuth or none, so a bearer token may not work from the connector UI;
the data is public anyway. Do not put secrets in this server.

## Tools
get_candles(contract, interval="4h", limit=200, closed_only=True) - oldest-first, drops live bar, reports continuity gaps
get_ticker(contract) | get_order_book(contract, depth) (adds spread_pct) | get_contract(contract) | get_funding_rate_history(contract, limit)

Contracts: BTC_USDT, ETH_USDT, SOL_USDT, LINK_USDT, ADA_USDT, ONDO_USDT (confirm each exists on Gate futures).
