"""Curated zip-prefix -> utility -> rate structure lookup.

Real OpenEI integration is a future swap-in. For now this covers a broad swath
of US metros/states with representative rate structures so the app delivers
value immediately. Resolution is by 3-digit zip prefix (ZCTA-ish), which is
plenty for region/utility selection.

Rate structures
---------------
- "tou"  : time-of-use. `periods` is a list of (start_hour, end_hour, $/kWh)
           covering 0-24 with no gaps. Hours are local clock hours.
- "flat" : single price all day via `flat_rate`.

`eia_region` is the EIA-930 balancing-authority/region code used to pull live
grid demand + day-ahead forecast as the grid-stress signal for dynamic pricing.
"""

# --- Utility definitions (the source of truth for base pricing) -------------
# Helper-free, explicit data. Rates are representative 2024-ish residential.
UTILITIES: dict[str, dict] = {
    # ----- Texas (ERCOT) -----
    "oncor": {"name": "Oncor (Dallas-Fort Worth)", "eia_region": "ERCO", "structure": "tou",
              "periods": [(0, 6, 0.08), (6, 14, 0.14), (14, 20, 0.24), (20, 24, 0.12)]},
    "centerpoint": {"name": "CenterPoint (Houston)", "eia_region": "ERCO", "structure": "tou",
                    "periods": [(0, 6, 0.09), (6, 15, 0.15), (15, 21, 0.26), (21, 24, 0.13)]},
    "austin_energy": {"name": "Austin Energy", "eia_region": "ERCO", "structure": "tou",
                      "periods": [(0, 6, 0.07), (6, 14, 0.13), (14, 20, 0.22), (20, 24, 0.11)]},
    "cps_energy": {"name": "CPS Energy (San Antonio)", "eia_region": "ERCO", "structure": "flat",
                   "flat_rate": 0.12},
    # ----- California (CAISO / LADWP) -----
    "pge": {"name": "Pacific Gas & Electric (PG&E)", "eia_region": "CISO", "structure": "tou",
            "periods": [(0, 15, 0.30), (15, 16, 0.40), (16, 21, 0.52), (21, 24, 0.40)]},
    "sce": {"name": "Southern California Edison", "eia_region": "CISO", "structure": "tou",
            "periods": [(0, 16, 0.28), (16, 21, 0.48), (21, 24, 0.34)]},
    "sdge": {"name": "San Diego Gas & Electric", "eia_region": "CISO", "structure": "tou",
             "periods": [(0, 6, 0.32), (6, 16, 0.40), (16, 21, 0.62), (21, 24, 0.44)]},
    "ladwp": {"name": "LA Dept of Water & Power", "eia_region": "LDWP", "structure": "tou",
              "periods": [(0, 13, 0.22), (13, 17, 0.30), (17, 22, 0.38), (22, 24, 0.24)]},
    "smud": {"name": "SMUD (Sacramento)", "eia_region": "CISO", "structure": "tou",
             "periods": [(0, 12, 0.14), (12, 17, 0.18), (17, 20, 0.34), (20, 24, 0.18)]},
    # ----- Northeast (NYISO / ISO-NE / PJM) -----
    "coned": {"name": "Con Edison (NYC)", "eia_region": "NYIS", "structure": "tou",
              "periods": [(0, 8, 0.18), (8, 12, 0.26), (12, 20, 0.34), (20, 24, 0.22)]},
    "national_grid_ny": {"name": "National Grid (Upstate NY)", "eia_region": "NYIS", "structure": "flat",
                         "flat_rate": 0.17},
    "pseg_li": {"name": "PSEG Long Island", "eia_region": "NYIS", "structure": "tou",
                "periods": [(0, 10, 0.16), (10, 16, 0.22), (16, 22, 0.30), (22, 24, 0.18)]},
    "eversource": {"name": "Eversource (MA/CT)", "eia_region": "ISNE", "structure": "flat",
                   "flat_rate": 0.28},
    "national_grid_ma": {"name": "National Grid (Massachusetts)", "eia_region": "ISNE", "structure": "flat",
                         "flat_rate": 0.27},
    "pseg_nj": {"name": "PSE&G (New Jersey)", "eia_region": "PJM", "structure": "flat",
                "flat_rate": 0.17},
    "pepco": {"name": "Pepco (Washington DC)", "eia_region": "PJM", "structure": "tou",
              "periods": [(0, 8, 0.12), (8, 16, 0.15), (16, 21, 0.22), (21, 24, 0.14)]},
    "bge": {"name": "BGE (Baltimore)", "eia_region": "PJM", "structure": "tou",
            "periods": [(0, 7, 0.11), (7, 17, 0.15), (17, 21, 0.21), (21, 24, 0.13)]},
    "ppl": {"name": "PPL Electric (Pennsylvania)", "eia_region": "PJM", "structure": "flat",
            "flat_rate": 0.16},
    "dominion": {"name": "Dominion Energy (Virginia)", "eia_region": "PJM", "structure": "flat",
                 "flat_rate": 0.14},
    # ----- Midwest (PJM / MISO / SPP) -----
    "comed": {"name": "ComEd (Chicago)", "eia_region": "PJM", "structure": "flat", "flat_rate": 0.16},
    "ameren": {"name": "Ameren (Missouri/Illinois)", "eia_region": "MISO", "structure": "flat",
               "flat_rate": 0.14},
    "dte": {"name": "DTE Energy (Detroit)", "eia_region": "MISO", "structure": "tou",
            "periods": [(0, 11, 0.15), (11, 19, 0.21), (19, 24, 0.16)]},
    "consumers_energy": {"name": "Consumers Energy (Michigan)", "eia_region": "MISO", "structure": "tou",
                         "periods": [(0, 7, 0.14), (7, 15, 0.18), (15, 20, 0.24), (20, 24, 0.16)]},
    "we_energies": {"name": "We Energies (Wisconsin)", "eia_region": "MISO", "structure": "flat",
                    "flat_rate": 0.17},
    "xcel_mn": {"name": "Xcel Energy (Minnesota)", "eia_region": "MISO", "structure": "flat",
                "flat_rate": 0.15},
    "evergy": {"name": "Evergy (Kansas City)", "eia_region": "SWPP", "structure": "tou",
               "periods": [(0, 13, 0.11), (13, 20, 0.24), (20, 24, 0.14)]},
    "oge": {"name": "OG&E (Oklahoma)", "eia_region": "SWPP", "structure": "flat", "flat_rate": 0.12},
    # ----- Southeast (SOCO / TVA / Florida) -----
    "georgia_power": {"name": "Georgia Power", "eia_region": "SOCO", "structure": "flat", "flat_rate": 0.14},
    "alabama_power": {"name": "Alabama Power", "eia_region": "SOCO", "structure": "flat", "flat_rate": 0.15},
    "fpl": {"name": "Florida Power & Light", "eia_region": "FPL", "structure": "flat", "flat_rate": 0.14},
    "duke_fl": {"name": "Duke Energy Florida", "eia_region": "FPC", "structure": "flat", "flat_rate": 0.15},
    "duke_nc": {"name": "Duke Energy (Carolinas)", "eia_region": "DUK", "structure": "flat", "flat_rate": 0.13},
    "tva": {"name": "TVA / Local Co-op (Tennessee)", "eia_region": "TVA", "structure": "flat", "flat_rate": 0.12},
    "entergy": {"name": "Entergy (Louisiana/Arkansas)", "eia_region": "MISO", "structure": "flat",
                "flat_rate": 0.12},
    # ----- Mountain West / Southwest -----
    "xcel_co": {"name": "Xcel Energy (Colorado)", "eia_region": "PSCO", "structure": "tou",
                "periods": [(0, 13, 0.13), (13, 19, 0.28), (19, 24, 0.18)]},
    "srp": {"name": "Salt River Project (Phoenix)", "eia_region": "AZPS", "structure": "tou",
            "periods": [(0, 14, 0.11), (14, 20, 0.29), (20, 24, 0.14)]},
    "aps": {"name": "Arizona Public Service", "eia_region": "AZPS", "structure": "tou",
            "periods": [(0, 15, 0.12), (15, 20, 0.30), (20, 24, 0.15)]},
    "nv_energy": {"name": "NV Energy (Las Vegas/Reno)", "eia_region": "NEVP", "structure": "tou",
                  "periods": [(0, 13, 0.12), (13, 19, 0.26), (19, 24, 0.15)]},
    "pnm": {"name": "PNM (New Mexico)", "eia_region": "PNM", "structure": "flat", "flat_rate": 0.14},
    "rocky_mountain": {"name": "Rocky Mountain Power (Utah)", "eia_region": "PACE", "structure": "tou",
                       "periods": [(0, 8, 0.10), (8, 15, 0.12), (15, 22, 0.20), (22, 24, 0.11)]},
    "idaho_power": {"name": "Idaho Power", "eia_region": "IPCO", "structure": "flat", "flat_rate": 0.11},
    # ----- Pacific Northwest -----
    "seattle_city_light": {"name": "Seattle City Light", "eia_region": "SCL", "structure": "flat",
                           "flat_rate": 0.12},
    "puget_sound": {"name": "Puget Sound Energy", "eia_region": "BPAT", "structure": "flat", "flat_rate": 0.13},
    "portland_ge": {"name": "Portland General Electric", "eia_region": "PACW", "structure": "tou",
                    "periods": [(0, 6, 0.11), (6, 15, 0.15), (15, 20, 0.23), (20, 24, 0.14)]},
    # ----- Non-contiguous -----
    "hawaiian_electric": {"name": "Hawaiian Electric", "eia_region": "HECO", "structure": "flat",
                          "flat_rate": 0.42},
}

# --- Zip prefix -> list of candidate utility keys (first = default) ---------
ZIP_PREFIX_TO_UTILITIES: dict[str, list[str]] = {
    # New England
    "010": ["national_grid_ma"], "011": ["national_grid_ma"], "012": ["national_grid_ma"],
    "013": ["national_grid_ma"], "014": ["eversource"], "015": ["national_grid_ma"],
    "016": ["national_grid_ma"], "017": ["eversource"], "018": ["national_grid_ma"],
    "019": ["national_grid_ma"], "020": ["eversource"], "021": ["eversource"],
    "022": ["eversource"], "023": ["national_grid_ma"], "024": ["national_grid_ma"],
    "025": ["eversource"], "026": ["eversource"], "027": ["national_grid_ma"],
    "060": ["eversource"], "061": ["eversource"], "062": ["eversource"], "063": ["eversource"],
    "064": ["eversource"], "065": ["eversource"], "066": ["eversource"], "067": ["eversource"],
    # New York
    "100": ["coned"], "101": ["coned"], "102": ["coned"], "103": ["coned"], "104": ["coned"],
    "110": ["pseg_li"], "111": ["coned", "pseg_li"], "112": ["coned"], "113": ["coned"],
    "114": ["coned"], "115": ["pseg_li"], "116": ["pseg_li"], "117": ["pseg_li"],
    "118": ["pseg_li"], "119": ["pseg_li"],
    "120": ["national_grid_ny"], "121": ["national_grid_ny"], "122": ["national_grid_ny"],
    "130": ["national_grid_ny"], "131": ["national_grid_ny"], "132": ["national_grid_ny"],
    "140": ["national_grid_ny"], "141": ["national_grid_ny"], "142": ["national_grid_ny"],
    "143": ["national_grid_ny"], "144": ["national_grid_ny"], "146": ["national_grid_ny"],
    # New Jersey
    "070": ["pseg_nj"], "071": ["pseg_nj"], "072": ["pseg_nj"], "073": ["pseg_nj"],
    "074": ["pseg_nj"], "075": ["pseg_nj"], "076": ["pseg_nj"], "077": ["pseg_nj"],
    "078": ["pseg_nj"], "079": ["pseg_nj"], "080": ["pseg_nj"], "081": ["pseg_nj"],
    "085": ["pseg_nj"], "086": ["pseg_nj"], "087": ["pseg_nj"], "088": ["pseg_nj"],
    # Pennsylvania / Delaware
    "150": ["ppl"], "151": ["ppl"], "152": ["ppl"], "170": ["ppl"], "171": ["ppl"],
    "180": ["ppl"], "181": ["ppl"], "189": ["ppl"], "190": ["ppl"], "191": ["ppl"],
    "194": ["ppl"], "196": ["ppl"], "197": ["pseg_nj"], "198": ["pseg_nj"],
    # DC / Maryland / Virginia
    "200": ["pepco"], "201": ["dominion"], "202": ["pepco"], "203": ["pepco"], "204": ["pepco"],
    "206": ["bge"], "207": ["bge"], "208": ["pepco"], "209": ["pepco"],
    "210": ["bge"], "211": ["bge"], "212": ["bge"], "214": ["bge"], "217": ["bge"],
    "220": ["dominion"], "221": ["dominion"], "222": ["dominion"], "223": ["dominion"],
    "230": ["dominion"], "231": ["dominion"], "232": ["dominion"], "233": ["dominion"],
    "234": ["dominion"], "235": ["dominion"],
    # Carolinas
    "270": ["duke_nc"], "271": ["duke_nc"], "272": ["duke_nc"], "273": ["duke_nc"],
    "274": ["duke_nc"], "275": ["duke_nc"], "276": ["duke_nc"], "280": ["duke_nc"],
    "281": ["duke_nc"], "282": ["duke_nc"], "290": ["duke_nc"], "291": ["duke_nc"],
    "292": ["duke_nc"], "294": ["duke_nc"],
    # Georgia / Alabama
    "300": ["georgia_power"], "301": ["georgia_power"], "302": ["georgia_power"],
    "303": ["georgia_power"], "304": ["georgia_power"], "305": ["georgia_power"],
    "306": ["georgia_power"], "308": ["georgia_power"], "310": ["georgia_power"],
    "350": ["alabama_power"], "351": ["alabama_power"], "352": ["alabama_power"],
    "354": ["alabama_power"], "360": ["alabama_power"], "361": ["alabama_power"],
    "362": ["alabama_power"], "363": ["alabama_power"], "365": ["alabama_power"],
    # Florida
    "320": ["duke_fl"], "321": ["duke_fl"], "322": ["duke_fl"], "327": ["duke_fl"],
    "328": ["duke_fl"], "329": ["duke_fl"], "330": ["fpl"], "331": ["fpl"], "332": ["fpl"],
    "333": ["fpl"], "334": ["fpl"], "335": ["fpl"], "336": ["duke_fl"], "337": ["duke_fl"],
    "338": ["duke_fl"], "339": ["fpl"], "341": ["fpl"], "342": ["fpl"], "346": ["duke_fl"],
    "347": ["duke_fl"], "349": ["fpl"],
    # Tennessee
    "370": ["tva"], "371": ["tva"], "372": ["tva"], "373": ["tva"], "374": ["tva"],
    "376": ["tva"], "377": ["tva"], "378": ["tva"], "379": ["tva"], "380": ["tva"],
    "381": ["tva"], "382": ["tva"], "383": ["tva"], "384": ["tva"],
    # Louisiana / Arkansas / Mississippi
    "700": ["entergy"], "701": ["entergy"], "703": ["entergy"], "704": ["entergy"],
    "705": ["entergy"], "706": ["entergy"], "707": ["entergy"], "708": ["entergy"],
    "710": ["entergy"], "711": ["entergy"], "712": ["entergy"], "716": ["entergy"],
    "717": ["entergy"], "718": ["entergy"], "719": ["entergy"], "720": ["entergy"],
    "721": ["entergy"], "722": ["entergy"],
    # Texas (ERCOT)
    "750": ["oncor"], "751": ["oncor"], "752": ["oncor"], "753": ["oncor"], "754": ["oncor"],
    "756": ["oncor"], "757": ["oncor"], "759": ["oncor"], "760": ["oncor"], "761": ["oncor"],
    "762": ["oncor"], "763": ["oncor"], "765": ["oncor"], "766": ["centerpoint"],
    "770": ["centerpoint"], "771": ["centerpoint"], "772": ["centerpoint"], "773": ["centerpoint"],
    "774": ["centerpoint"], "775": ["centerpoint"], "776": ["centerpoint"], "777": ["centerpoint"],
    "778": ["austin_energy"], "780": ["cps_energy"], "781": ["cps_energy"], "782": ["cps_energy"],
    "786": ["austin_energy"], "787": ["austin_energy"], "788": ["cps_energy"],
    # Oklahoma / Kansas / Missouri
    "730": ["oge"], "731": ["oge"], "740": ["oge"], "741": ["oge"],
    "660": ["evergy"], "661": ["evergy"], "662": ["evergy"], "664": ["evergy"], "666": ["evergy"],
    "670": ["evergy"], "672": ["evergy"], "640": ["ameren"], "641": ["evergy"],
    "630": ["ameren"], "631": ["ameren"], "633": ["ameren"], "650": ["ameren"], "656": ["ameren"],
    # Illinois / Wisconsin / Minnesota
    "600": ["comed"], "601": ["comed"], "602": ["comed"], "603": ["comed"], "604": ["comed"],
    "605": ["comed"], "606": ["comed"], "607": ["comed"], "608": ["ameren"], "609": ["ameren"],
    "610": ["ameren"], "611": ["ameren"], "612": ["ameren"], "617": ["ameren"], "620": ["ameren"],
    "530": ["we_energies"], "531": ["we_energies"], "532": ["we_energies"], "534": ["we_energies"],
    "535": ["we_energies"], "537": ["we_energies"], "539": ["we_energies"],
    "540": ["we_energies"], "541": ["we_energies"], "549": ["we_energies"],
    "550": ["xcel_mn"], "551": ["xcel_mn"], "553": ["xcel_mn"], "554": ["xcel_mn"],
    "559": ["xcel_mn"], "560": ["xcel_mn"], "565": ["xcel_mn"], "566": ["xcel_mn"],
    # Michigan
    "480": ["dte"], "481": ["dte"], "482": ["dte"], "483": ["dte"], "484": ["consumers_energy"],
    "485": ["consumers_energy"], "486": ["consumers_energy"], "487": ["consumers_energy"],
    "488": ["consumers_energy"], "489": ["consumers_energy"], "490": ["consumers_energy"],
    "491": ["consumers_energy"], "492": ["consumers_energy"], "493": ["consumers_energy"],
    "494": ["consumers_energy"], "495": ["consumers_energy"], "496": ["consumers_energy"],
    # Colorado
    "800": ["xcel_co"], "801": ["xcel_co"], "802": ["xcel_co"], "803": ["xcel_co"],
    "804": ["xcel_co"], "805": ["xcel_co"], "806": ["xcel_co"], "808": ["xcel_co"],
    "809": ["xcel_co"], "810": ["xcel_co"], "816": ["xcel_co"],
    # New Mexico
    "870": ["pnm"], "871": ["pnm"], "873": ["pnm"], "875": ["pnm"], "877": ["pnm"],
    # Arizona
    "850": ["srp"], "851": ["aps"], "852": ["srp"], "853": ["srp"], "855": ["aps"],
    "856": ["aps"], "857": ["aps"], "859": ["aps"], "860": ["aps"], "863": ["aps"],
    # Nevada / Utah / Idaho
    "889": ["nv_energy"], "890": ["nv_energy"], "891": ["nv_energy"], "893": ["nv_energy"],
    "894": ["nv_energy"], "895": ["nv_energy"], "897": ["nv_energy"], "898": ["nv_energy"],
    "840": ["rocky_mountain"], "841": ["rocky_mountain"], "842": ["rocky_mountain"],
    "843": ["rocky_mountain"], "844": ["rocky_mountain"], "846": ["rocky_mountain"],
    "847": ["rocky_mountain"], "836": ["idaho_power"], "837": ["idaho_power"], "838": ["idaho_power"],
    # California
    "900": ["sce", "ladwp"], "901": ["sce", "ladwp"], "902": ["sce"], "903": ["sce"],
    "904": ["sce", "ladwp"], "905": ["sce"], "906": ["sce"], "907": ["sce"], "908": ["sce"],
    "910": ["sce"], "911": ["sce"], "912": ["sce"], "913": ["sce"], "914": ["sce"],
    "915": ["sce"], "916": ["sce"], "917": ["sce"], "918": ["sce"], "919": ["sdge"],
    "920": ["sdge"], "921": ["sdge"], "922": ["sce"], "923": ["sce"], "924": ["sce"],
    "925": ["pge"], "926": ["sce"], "927": ["sce"], "928": ["sce"],
    "930": ["sce"], "931": ["sce"], "932": ["sce"], "933": ["sce"], "934": ["sce"],
    "935": ["sce"], "936": ["pge"], "937": ["pge"], "938": ["pge"], "939": ["pge"],
    "940": ["pge"], "941": ["pge"], "942": ["smud"], "943": ["pge"], "944": ["pge"],
    "945": ["pge"], "946": ["pge"], "947": ["pge"], "948": ["pge"], "949": ["pge"],
    "950": ["pge"], "951": ["pge"], "952": ["pge"], "953": ["pge"], "954": ["pge"],
    "956": ["smud"], "957": ["smud"], "958": ["smud"], "959": ["smud"], "960": ["pge"],
    # Oregon / Washington
    "970": ["portland_ge"], "971": ["portland_ge"], "972": ["portland_ge"], "973": ["portland_ge"],
    "974": ["portland_ge"], "975": ["portland_ge"], "977": ["portland_ge"],
    "980": ["puget_sound"], "981": ["seattle_city_light"], "982": ["puget_sound"],
    "983": ["puget_sound"], "984": ["puget_sound"], "985": ["puget_sound"], "988": ["puget_sound"],
    "990": ["puget_sound"], "992": ["puget_sound"],
    # Hawaii
    "967": ["hawaiian_electric"], "968": ["hawaiian_electric"],
}


def lookup_by_zip(zip_code: str) -> dict | None:
    """Resolve a 5-digit zip to region + candidate utilities.

    Returns a dict with `prefix`, `default_utility` (key), and `candidates`
    (list of {key, name}). Returns None if the prefix isn't covered.
    """
    zip_code = (zip_code or "").strip()
    if len(zip_code) < 3 or not zip_code[:3].isdigit():
        return None
    prefix = zip_code[:3]
    keys = ZIP_PREFIX_TO_UTILITIES.get(prefix)
    if not keys:
        return None
    return {
        "prefix": prefix,
        "default_utility": keys[0],
        "candidates": [{"key": k, "name": UTILITIES[k]["name"]} for k in keys],
    }


def get_utility(key: str) -> dict | None:
    """Return a utility config (with its key injected) or None."""
    util = UTILITIES.get(key)
    if util is None:
        return None
    return {"key": key, **util}


def covered_prefixes() -> list[str]:
    """All supported zip prefixes (for the 'where do we work' hint)."""
    return sorted(ZIP_PREFIX_TO_UTILITIES.keys())


def coverage_summary() -> dict:
    """Counts for the UI / metrics: how many utilities and zip prefixes."""
    return {"utilities": len(UTILITIES), "zip_prefixes": len(ZIP_PREFIX_TO_UTILITIES)}
