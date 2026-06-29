# WattWise

A dead-simple consumer layer over real grid electricity pricing. Enter your
zip, your utility, and (optionally) what you want to run -- WattWise tells you
the price per kWh **right now**, whether now is a good or bad time, and the
**cheapest window in the next 24 hours**.

## Why it's different
- Utility apps show last month's bill. This shows **right now + next 24h**.
- Grid dashboards (ERCOT, PJM) are built for traders. This is built for humans.
- Marries **zip-level utility rate structures** with **live grid demand**.

## Features
- Zip -> utility -> rate-structure resolution (10 major US metros)
- Time-of-use + flat rate pricing, $/kWh right now
- Green/Yellow/Red "is now a good time?" score
- Cheapest consecutive N-hour window finder
- Appliance cost calculator (kW x hours x $/kWh)
- **Cost Simulator** -- drag a slider across all 24 start hours to see exactly
  what a run would cost when started at each hour, with live savings-vs-cheapest
  and a cost-by-start-hour bar chart
- 24h price curve with live EIA grid-demand overlay (mock fallback, keyless)

## Architecture
```
app/
  main.py            FastAPI routes (page + HTMX endpoints)
  eia.py             EIA-930 demand client + mock fallback + caching
  cache.py           SQLite TTL cache (no user data stored)
  logic.py           cost calc, best-window algorithm, green/yellow/red score
  data/appliances.py hardcoded wattage database
  data/zip_lookup.py curated zip -> utility -> rate structure
  templates/         HTMX + Tailwind single-page UI, Chart.js price curve
```

### Pricing model (honest note)
EIA's free API gives hourly grid **demand/forecast** by region, not retail
price. So your **bill price** comes from your utility's published **time-of-use
rate schedule** (deterministic -- what you actually pay), and **live EIA
demand** is shown as a "grid stress" overlay. More honest than pretending EIA
returns a retail price.

## Run it
```bash
uv venv
uv pip install fastapi "uvicorn[standard]" jinja2 httpx python-dotenv
cp .env.example .env        # then paste your EIA key (optional)
uvicorn app.main:app --reload --port 8050
```
Open http://localhost:8050

## Test
```bash
python -m pytest tests/ -q     # or: uv run pytest
```

## Get an EIA API key (free, instant)
https://www.eia.gov/opendata/register.php -- paste into `.env` as `EIA_API_KEY`.
Without it, the app runs on a realistic modeled demand curve.

## Roadmap
- Swap curated zip lookup for live OpenEI utility-rate DB
- More utilities / rate plans, real-time LMP where available
- Push alerts ("cheap window starts in 30 min")
