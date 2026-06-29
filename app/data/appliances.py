"""Hardcoded appliance wattage database.

Kept deliberately simple (YAGNI): a flat dict of typical real-world draws.
`watts` are steady-state running watts; `default_hours` is a sensible
default runtime so the UI can pre-fill something useful.
"""

APPLIANCES: dict[str, dict] = {
    "ev_charger": {
        "label": "EV Charger (Level 2)",
        "watts": 7200,
        "default_hours": 4.0,
        "icon": "",
    },
    "ac": {
        "label": "Air Conditioner (central)",
        "watts": 3500,
        "default_hours": 3.0,
        "icon": "",
    },
    "dryer": {
        "label": "Clothes Dryer",
        "watts": 3000,
        "default_hours": 1.0,
        "icon": "",
    },
    "water_heater": {
        "label": "Water Heater",
        "watts": 4500,
        "default_hours": 2.0,
        "icon": "",
    },
    "oven": {
        "label": "Electric Oven",
        "watts": 2400,
        "default_hours": 1.0,
        "icon": "",
    },
    "dishwasher": {
        "label": "Dishwasher",
        "watts": 1800,
        "default_hours": 1.5,
        "icon": "",
    },
    "pool_pump": {
        "label": "Pool Pump",
        "watts": 1500,
        "default_hours": 6.0,
        "icon": "",
    },
    "space_heater": {
        "label": "Space Heater",
        "watts": 1500,
        "default_hours": 4.0,
        "icon": "",
    },
    "washer": {
        "label": "Washing Machine",
        "watts": 500,
        "default_hours": 1.0,
        "icon": "",
    },
    "lights": {
        "label": "LED Lights (whole home)",
        "watts": 200,
        "default_hours": 5.0,
        "icon": "",
    },
}


def get_appliance(key: str) -> dict | None:
    """Return appliance config or None if unknown."""
    return APPLIANCES.get(key)
