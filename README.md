# WattWise

Find the cheapest and cleanest time to use electricity. Enter your zip code,
pick your utility, and (optionally) what you want to run. WattWise shows the
current price per kWh, the grid's carbon intensity, and the best window over
the next 24 hours.

Stack: FastAPI + HTMX + Tailwind + Chart.js. No accounts, no database of user
data, no build step.

## What it does

- Resolves your zip to a utility and its rate plan (45 utilities, ~409 zip prefixes)
- Shows a grid-aware price: the utility's published rate adjusted by live grid demand
- Computes grid carbon intensity from EIA's real hourly fuel mix
- Finds the cheapest N-hour window, with a "cost vs carbon" optimizer slider
- Models appliances realistically (duty cycles + motor startup, not just watts x hours)
- Plots the next 24h: price, day-ahead forecast, and grid demand

## A note on the data

EIA's free API gives hourly grid demand, a day-ahead demand forecast, and
generation by fuel type, but not a retail price (and retail tariffs are fixed
by the utility anyway). So the prices here combine two things:

- the utility's published rate plan (the real, contractual part), and
- a multiplier derived from live grid demand (a model of real-time pricing).

The effective price is labeled as modeled, never as a literal bill. Carbon
intensity is computed directly from the live fuel mix. Without an API key the
app falls back to a synthesized curve and labels the source `mock`.

## Run it

```bash
git clone https://github.com/dheemiyer/wattwise.git
cd wattwise
uv venv
uv pip install -r requirements.txt        # or: pip install -r requirements.txt
cp .env.example .env                       # add your EIA key (optional)
uvicorn app.main:app --reload --port 8050
```

Open http://localhost:8050.

Get a free EIA key at https://www.eia.gov/opendata/register.php and put it in
`.env` as `EIA_API_KEY`. Behind a corporate proxy, also set
`EIA_PROXY=http://host:port` so the EIA calls can get out.

## Tests

```bash
python -m pytest tests/ -q
```

## Deploy (Render free tier)

The repo includes a `render.yaml` blueprint. On https://render.com, sign in
with GitHub, create a new Blueprint from this repo, and add `EIA_API_KEY` as
an environment variable in the dashboard. Render builds from
`requirements.txt` and starts uvicorn on its `$PORT`. Free instances sleep
when idle, so the first request after a pause can take a bit to wake.

## Layout

```
app/
  main.py             FastAPI routes
  eia.py              EIA client: demand, forecast, fuel mix (proxy-aware)
  grid.py             dynamic pricing model
  carbon.py           carbon intensity + cost/carbon optimizer
  logic.py            pricing math, windows, scoring, simulator
  cache.py            SQLite TTL cache
  data/appliances.py  appliance energy model
  data/zip_lookup.py  zip -> utility -> rate plan
  templates/          HTMX + Tailwind UI
```

## Ideas / todo

- Swap the curated zip lookup for the OpenEI utility-rate database
- Use real-time wholesale prices where ISOs publish them (ComEd, ERCOT, CAISO)
- Add a /metrics endpoint and price-drop alerts

## License

MIT. See [LICENSE](LICENSE).
