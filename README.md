# WattWise

A dead-simple consumer layer over real grid electricity pricing. Enter your
zip, your utility, and (optionally) what you want to run -- WattWise tells you
the **grid-adjusted price per kWh right now**, whether now is a good or bad
time, and the **cheapest window in the next 24 hours**.

## Features
- **Broad coverage** -- 45 utilities across ~409 US zip-code prefixes
- Time-of-use + flat base tariffs resolved from your zip
- **Dynamic, grid-aware pricing**: base tariff x a live grid-stress multiplier
- **Day-ahead forecast curve** driven by EIA's real demand forecast
- Green/Yellow/Red "is now a good time?" score with a plain-English *why*
- **Physics-aware appliance model** -- duty cycles + motor startup surge, so an
  AC's effective kWh reflects that the compressor only runs part of the time
- Cheapest consecutive N-hour window finder
- **Cost Simulator** -- drag a slider across all 24 start hours to see exactly
  what a run would cost at each, with live savings and a bar chart
- 24h chart: grid-adjusted price (bars), day-ahead forecast (dashed), demand (line)

## Honest data model (read this -- it's the interview answer)
EIA's free API gives hourly grid **demand** + a **day-ahead demand forecast**
by region -- **not** a retail price. And retail tariffs are *static by design*
(a TOU plan's peak rate is fixed contractually). So WattWise is explicit about
what's measured vs modeled:

- **Base price** = the utility's published tariff (real, contractual).
- **Grid-stress multiplier** = derived from **live EIA demand** (real, measured),
  mapped to a conservative +/-~30% band -- modeling real-time-pricing behavior.
- **Effective (dynamic) price** = base x multiplier. Clearly labeled *modeled*,
  never presented as a literal billed rate.
- **Forecast price** = the same model applied to EIA's day-ahead forecast.

Without an API key (or on any network failure) it falls back to a realistic
synthesized curve and labels the source `mock` so the UI never lies.

## Architecture
```
app/
  main.py            FastAPI routes (page + HTMX endpoints)
  eia.py             EIA-930 client: live demand + day-ahead forecast, proxy-aware
  grid.py            dynamic pricing model (stress multiplier, forecast, explain)
  cache.py           SQLite TTL cache (no user data stored)
  logic.py           base tariff, dynamic curve, best-window, scoring, simulator
  data/appliances.py wattage + duty-cycle + startup-surge energy model
  data/zip_lookup.py curated zip -> utility -> rate structure (45 utilities)
  templates/         HTMX + Tailwind single-page UI, Chart.js charts
```

## Run it
```bash
git clone <your-repo-url> wattwise
cd wattwise

# Option A -- uv (fast)
uv venv
uv pip install -r requirements.txt

# Option B -- plain pip
python -m venv .venv
.venv\Scripts\activate        # Windows  (use: source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

cp .env.example .env            # then paste your free EIA key (optional)
uvicorn app.main:app --reload --port 8050
```
Open http://localhost:8050

### Behind a corporate proxy
Set `EIA_PROXY` (or standard `HTTPS_PROXY`) in `.env` so EIA calls route
through it -- required where `api.eia.gov` isn't directly reachable:
```
EIA_PROXY=http://sysproxy.wal-mart.com:8080
```

## Test
```bash
python -m pytest tests/ -q     # 18 tests, all pure logic -- fast
```

## Get an EIA API key (free, instant)
https://www.eia.gov/opendata/register.php -- paste into `.env` as `EIA_API_KEY`.
Without it, the app runs on a realistic modeled grid curve.

## Roadmap
- Swap curated zip lookup for the live OpenEI utility-rate DB
- Real-time wholesale LMP where ISOs expose it (ComEd RTP, ERCOT, CAISO)
- /metrics endpoint (cache hit-rate, latency) + push alerts
