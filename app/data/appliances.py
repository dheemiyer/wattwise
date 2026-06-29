"""Appliance energy model.

Beyond a single wattage number, real appliances don't draw their rated power
continuously:

- ``watts``            : rated (nameplate) running power in watts.
- ``duty_cycle``       : fraction of wall-clock time the appliance actually
                         draws power. Thermostatic / cycling loads (AC, fridge,
                         oven, water heater) cycle on and off; resistive or
                         continuous loads (EV charger, lights) run near 1.0.
- ``startup_surge_kwh``: one-time energy bump from motor inrush at start-up
                         (compressors/pumps). Small but non-zero -- modeling it
                         is what separates a toy calc from a real one.
- ``default_hours``    : a sensible default runtime to pre-fill the UI.

Effective energy for a run is therefore::

    kWh = (watts / 1000) * hours * duty_cycle  +  startup_surge_kwh

which is materially different from the naive ``watts * hours`` for cycling
loads (e.g. an AC at duty 0.6 uses ~40% less than the nameplate would suggest).
"""

APPLIANCES: dict[str, dict] = {
    "ev_charger": {
        "label": "EV Charger (Level 2)",
        "watts": 7200,
        "duty_cycle": 1.0,
        "startup_surge_kwh": 0.0,
        "default_hours": 4.0,
    },
    "ac": {
        "label": "Air Conditioner (central)",
        "watts": 3500,
        "duty_cycle": 0.6,  # compressor cycles with the thermostat
        "startup_surge_kwh": 0.05,  # compressor inrush per start
        "default_hours": 3.0,
    },
    "dryer": {
        "label": "Clothes Dryer",
        "watts": 3000,
        "duty_cycle": 0.9,
        "startup_surge_kwh": 0.0,
        "default_hours": 1.0,
    },
    "water_heater": {
        "label": "Water Heater",
        "watts": 4500,
        "duty_cycle": 0.45,  # heats in bursts to hold setpoint
        "startup_surge_kwh": 0.0,
        "default_hours": 2.0,
    },
    "oven": {
        "label": "Electric Oven",
        "watts": 2400,
        "duty_cycle": 0.65,  # element cycles to hold temperature
        "startup_surge_kwh": 0.0,
        "default_hours": 1.0,
    },
    "dishwasher": {
        "label": "Dishwasher",
        "watts": 1800,
        "duty_cycle": 0.5,  # only heats water/dry in bursts
        "startup_surge_kwh": 0.0,
        "default_hours": 1.5,
    },
    "pool_pump": {
        "label": "Pool Pump",
        "watts": 1500,
        "duty_cycle": 1.0,
        "startup_surge_kwh": 0.02,
        "default_hours": 6.0,
    },
    "space_heater": {
        "label": "Space Heater",
        "watts": 1500,
        "duty_cycle": 0.7,  # thermostatic
        "startup_surge_kwh": 0.0,
        "default_hours": 4.0,
    },
    "fridge": {
        "label": "Refrigerator",
        "watts": 150,
        "duty_cycle": 0.35,  # compressor runs ~1/3 of the time
        "startup_surge_kwh": 0.01,
        "default_hours": 24.0,
    },
    "washer": {
        "label": "Washing Machine",
        "watts": 500,
        "duty_cycle": 0.4,
        "startup_surge_kwh": 0.0,
        "default_hours": 1.0,
    },
    "lights": {
        "label": "LED Lights (whole home)",
        "watts": 200,
        "duty_cycle": 1.0,
        "startup_surge_kwh": 0.0,
        "default_hours": 5.0,
    },
}


def get_appliance(key: str) -> dict | None:
    """Return appliance config or None if unknown."""
    return APPLIANCES.get(key)


def run_energy_kwh(appliance: dict, hours: float) -> float:
    """Effective kWh for a run, accounting for duty cycle and startup surge."""
    duty = float(appliance.get("duty_cycle", 1.0))
    surge = float(appliance.get("startup_surge_kwh", 0.0))
    running = (appliance["watts"] / 1000.0) * hours * duty
    return round(running + surge, 4)
