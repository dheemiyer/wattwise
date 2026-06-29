"""WattWise FastAPI app -- the consumer layer over real grid pricing.

Routes
------
GET  /            single-page UI
GET  /utilities   HTMX: utility <select> options for a given zip
POST /estimate    HTMX: the result card (price, score, best window, charts)
GET  /health      liveness probe
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import eia, logic
from .data.appliances import APPLIANCES, get_appliance
from .data.zip_lookup import covered_prefixes, get_utility, lookup_by_zip

load_dotenv()

_BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))

app = FastAPI(title="WattWise", description="When should I use electricity?")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "appliances": APPLIANCES,
            "covered": covered_prefixes(),
        },
    )


@app.get("/utilities", response_class=HTMLResponse)
def utilities(request: Request, zip: str = "") -> HTMLResponse:
    """Return <option> tags for the utilities serving this zip."""
    match = lookup_by_zip(zip)
    candidates = match["candidates"] if match else []
    return templates.TemplateResponse(
        request,
        "partials/utility_options.html",
        {"candidates": candidates},
    )


@app.post("/estimate", response_class=HTMLResponse)
def estimate(
    request: Request,
    zip: str = Form(""),
    utility: str = Form(""),
    appliance: str = Form(""),
    hours: float = Form(1.0),
) -> HTMLResponse:
    """Compute the result card for the given inputs (HTMX target)."""
    match = lookup_by_zip(zip)
    if match is None:
        return _error(
            request,
            "We don't cover that zip yet. Try a major metro "
            "(Dallas, Houston, SF, LA, NYC, Chicago, Atlanta, Denver, "
            "Phoenix, Minneapolis).",
        )

    util_key = utility or match["default_utility"]
    util = get_utility(util_key)
    if util is None:
        return _error(request, "Unknown utility provider selected.")

    appl = get_appliance(appliance) if appliance else None
    hours = max(0.25, min(float(hours or 1.0), 24.0))
    demand = eia.get_demand_curve(util["eia_region"])
    result = logic.compute_estimate(util, appl, hours, demand)

    return templates.TemplateResponse(
        request,
        "partials/result.html",
        {"r": result, "zip": zip},
    )


def _error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/error.html",
        {"message": message},
    )
