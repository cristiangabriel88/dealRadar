"""Central configuration for OLX Deal Finder.

Every tunable lives here so thresholds, the brand list, the city table and the
request-politeness settings can be adjusted without hunting through the code.
See the "Tuning" section of the README for guidance on the outlier thresholds.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Outlier-detection thresholds
# --------------------------------------------------------------------------- #

# A listing is flagged as a deal only when BOTH conditions hold:
#   1. its modified z-score is <= MOD_Z_THRESHOLD  (statistical outlier on the low side)
#   2. it is at least MIN_PERCENT_BELOW below the group median (meaningful discount)
MOD_Z_THRESHOLD: float = -1.5
MIN_PERCENT_BELOW: float = 0.25  # 25% below the group median

# A group must have at least this many samples before we trust its median
# enough to flag deals against it. Small groups are reported but not flagged.
MIN_SAMPLES: int = 5
# Looser sample requirement for the strict brand+model mode (true models are
# rarer in a single city, so we accept smaller — and noisier — groups).
STRICT_MIN_SAMPLES: int = 3

# Deals are ALWAYS judged against same brand+model comparables, regardless of the
# grouping mode used for the breakdown. A listing is only flagged when its exact
# brand+model appears in at least this many listings (including itself) — without
# enough comparable listings there is no trustworthy second-hand market value, so
# a lone cheap listing of a one-off model (e.g. a single "Cube Touring SL" with no
# other Cube Touring SL to compare to) is never flagged, even if it looks cheap
# against the broader brand pool.
MIN_MODEL_COMPARABLES: int = 3

# --------------------------------------------------------------------------- #
# Grouping modes (selectable per search; see olx_finder/stats.py)
# --------------------------------------------------------------------------- #
# Default strategy when none is specified.
DEFAULT_GROUPING_MODE: str = "brand_guarded"

# Kids/junior bikes (excluded from the adult comparison pool in guarded mode).
KIDS_TITLE_TOKENS: frozenset[str] = frozenset(
    {"copii", "copil", "copilas", "junior", "baietel", "fetita", "prescolar"}
)
# Wheel sizes at or below this (inches) are treated as kids/small bikes.
SMALL_WHEEL_MAX_INCHES: float = 20.0

# --------------------------------------------------------------------------- #
# Noise filtering
# --------------------------------------------------------------------------- #

# Prices below this (lei) are treated as implausible / placeholder and dropped.
MIN_PLAUSIBLE_PRICE: float = 100.0

# Titles containing any of these (diacritic-stripped, lowercased) tokens are
# parts/accessories, not whole bikes, and are excluded from the analysis.
PART_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "cadru",      # frame
        "roata",      # wheel
        "roti",       # wheels
        "janta",      # rim
        "jante",      # rims
        "piese",      # parts
        "piesa",
        "ghidon",     # handlebar
        "furca",      # fork
        "sa",         # saddle (matched as a whole word only)
        "pedale",     # pedals
        "pedala",
        "lant",       # chain
        "frana",      # brake
        "frane",      # brakes
        "anvelopa",   # tyre
        "anvelope",   # tyres
        "cauciuc",    # tyre/rubber
        "cauciucuri",
        "schimbator", # derailleur
        "manete",     # shifters/levers
        "pompa",      # pump
        "casca",      # helmet
        "suport",     # rack/stand
        "portbagaj",  # carrier
    }
)

# --------------------------------------------------------------------------- #
# Known bike brands and their normalized aliases
# --------------------------------------------------------------------------- #
#
# Key = canonical brand name (used for display + grouping).
# Value = list of normalized (lowercase, diacritic-free, space-collapsed) aliases
#         to match in a title. The canonical name (normalized) is matched too.
# Multi-word aliases are supported (matched as a contiguous phrase).
BRANDS: dict[str, list[str]] = {
    "GT": ["gt"],
    "Trek": ["trek"],
    "Specialized": ["specialized", "specialised"],
    "Giant": ["giant"],
    "Cube": ["cube"],
    "Cannondale": ["cannondale"],
    "Scott": ["scott"],
    "Merida": ["merida"],
    "Centurion": ["centurion"],
    # Decathlon house brands all normalize to this entry.
    "Btwin": ["btwin", "b twin", "b'twin", "btwin", "decathlon"],
    "Carrera": ["carrera"],
    "Bianchi": ["bianchi"],
    "Focus": ["focus"],
    "Kross": ["kross"],
    "Drag": ["drag"],
    "Rockrider": ["rockrider", "rock rider"],
    "Nakamura": ["nakamura"],
    "Pegas": ["pegas"],
    "Decathlon": ["decathlon"],
    "Orbea": ["orbea"],
    "Ghost": ["ghost"],
    "Haibike": ["haibike"],
    "KTM": ["ktm"],
    "Author": ["author"],
    "Romet": ["romet"],
    "Ideal": ["ideal"],
    "Carpat": ["carpat", "carpati"],
    "Dhs": ["dhs"],
    "Ultra": ["ultra"],
    "Velors": ["velors"],
    "Corratec": ["corratec"],
    "Lapierre": ["lapierre"],
    "Felt": ["felt"],
    "Norco": ["norco"],
    "Marin": ["marin"],
    "Mongoose": ["mongoose"],
    "Bulls": ["bulls"],
    "Conway": ["conway"],
}

# --------------------------------------------------------------------------- #
# Marketplace request settings (be polite)
# --------------------------------------------------------------------------- #

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_DELAY: float = 1.5     # seconds between paginated requests
PAGE_LIMIT: int = 50           # listings requested per page
MAX_PAGES: int = 10            # hard cap on pages fetched per search
REQUEST_TIMEOUT: float = 25.0  # seconds
MAX_RETRIES: int = 4           # retries on 403/429/timeout
BACKOFF_BASE: float = 2.0      # exponential backoff base (seconds)

# OLX-specific: the bicycles category id, confirmed from live API traffic.
OLX_BICYCLES_CATEGORY_ID: int = 987
OLX_OFFERS_ENDPOINT: str = "https://www.olx.ro/api/v1/offers/"

# --- Other Romanian marketplaces ------------------------------------------ #
# These have no clean public JSON API like OLX, so each source scopes to the
# site's bicycle section and we filter results to the selected city client-side
# (none expose a simple city filter for all of our cities). Endpoints/markup
# were confirmed from live pages and may need re-tuning if a site changes.

# Publi24: the bicycles category listing page (clean HTML cards, ?pag=N paging).
PUBLI24_BASE: str = "https://www.publi24.ro"
PUBLI24_BICYCLES_URL: str = (
    "https://www.publi24.ro/anunturi/timp-liber-sport/biciclete-accesorii/biciclete/"
)

# Lajumate: a Next.js site; the bikes category embeds listing JSON in the
# page's __NEXT_DATA__ script (?page=N paging). Cleaner than scraping its markup.
LAJUMATE_BASE: str = "https://lajumate.ro"
LAJUMATE_BICYCLES_URL: str = (
    "https://lajumate.ro/anunturi/sport-timp-liber-arta/biciclete-fitness-suplimente"
)

# Anuntul: no bike-only category, so we keyword-search ("bicicleta") and let the
# downstream brand/parts filtering drop the non-bike noise (?page=N paging).
ANUNTUL_BASE: str = "https://www.anuntul.ro"
ANUNTUL_SEARCH_URL: str = "https://www.anuntul.ro/anunturi/"

# Default search query (product type is fixed to bikes for now).
DEFAULT_QUERY: str = "bicicleta"

# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #

CACHE_DB_PATH: str = "cache.db"
CACHE_TTL_MINUTES: int = 5

# --------------------------------------------------------------------------- #
# Cities -> OLX city_id (all Romanian cities; discovered from the live API).
# Covers Romania's municipalities and towns; the value is the OLX numeric
# city_id used by the offers API. To add a locality, search it on olx.ro and
# read the city id from the offers API response (location.city.id).
DEFAULT_CITY: str = "Bucuresti"  # preselected in the UI city picker

CITIES: dict[str, int] = {
    "Abrud":                 24693,
    "Adjud":                 79685,
    "Agnita":                32583,
    "Aiud":                  24701,
    "Alba Iulia":            24723,
    "Alesd":                 48789,
    "Alexandria":            69235,
    "Amara":                 65477,
    "Anina":                 93063,
    "Aninoasa":              62753,
    "Arad":                  90749,
    "Ardud":                 58073,
    "Avrig":                 32615,
    "Azuga":                 66087,
    "Babadag":               78703,
    "Babeni":                88775,
    "Bacau":                 34959,
    "Baia de Arama":         85755,
    "Baia de Aries":         25433,
    "Baia Mare":             55935,
    "Baia Sprie":            56745,
    "Baicoi":                66099,
    "Baile Govora":          88789,
    "Baile Herculane":       93077,
    "Baile Olanesti":        88797,
    "Baile Tusnad":          29225,
    "Bailesti":              81149,
    "Balan":                 57247,
    "Balcesti":              88815,
    "Bals":                  87489,
    "Baraolt":               28559,
    "Barlad":                46649,
    "Bechet":                84129,
    "Beclean":               51531,
    "Beius":                 48845,
    "Berbesti":              56929,
    "Beresti":               45369,
    "Bicaz":                 42929,
    "Bistrita":              51539,
    "Blaj":                  25523,
    "Bocsa":                 93119,
    "Boldesti-Scaeni":       66169,
    "Bolintin-Vale":         64125,
    "Borsa":                 51275,
    "Borsec":                29235,
    "Botosani":              37653,
    "Brad":                  94477,
    "Bragadiru":             24497,
    "Braila":                69963,
    "Brasov":                26711,
    "Breaza":                66189,
    "Brezoi":                88875,
    "Brosteni":              59591,
    "Bucecea":               38947,
    "Bucuresti":             1,
    "Budesti":               61817,
    "Buftea":                24509,
    "Buhusi":                36297,
    "Bumbesti-Jiu":          84543,
    "Busteni":               66231,
    "Buzau":                 72473,
    "Buzias":                97029,
    "Cajvana":               45095,
    "Calafat":               81261,
    "Calan":                 94599,
    "Calarasi":              61821,
    "Calimanesti":           88949,
    "Campeni":               25629,
    "Campia Turzii":         52817,
    "Campina":               66239,
    "Campulung":             59829,
    "Campulung Moldovenesc": 45105,
    "Caracal":               87559,
    "Caransebes":            93161,
    "Carei":                 58145,
    "Cavnic":                56825,
    "Cazanesti":             89639,
    "Cehu Silvaniei":        57307,
    "Cernavoda":             74291,
    "Chisineu-Cris":         92613,
    "Chitila":               24527,
    "Ciacova":               97053,
    "Cisnadie":              32697,
    "Cluj-Napoca":           52953,
    "Codlea":                28267,
    "Comanesti":             36345,
    "Comarnic":              66311,
    "Constanta":             74335,
    "Copsa Mica":            32701,
    "Corabia":               87597,
    "Costesti":              73521,
    "Covasna":               101127,
    "Craiova":               81351,
    "Cristuru Secuiesc":     29291,
    "Cugir":                 25753,
    "Curtea de Arges":       60035,
    "Curtici":               92649,
    "Dabuleni":              83875,
    "Darabani":              39057,
    "Darmanesti":            45179,
    "Dej":                   54815,
    "Deta":                  97105,
    "Deva":                  94695,
    "Dolhasca":              45187,
    "Dorohoi":               39085,
    "Draganesti-Olt":        87695,
    "Dragasani":             89045,
    "Dragomiresti":          56905,
    "Drobeta-Turnu Severin": 85981,
    "Dumbraveni":            45567,
    "Eforie":                76543,
    "Fagaras":               28291,
    "Faget":                 97139,
    "Falticeni":             45253,
    "Faurei":                72091,
    "Fetesti":               65577,
    "Fieni":                 63017,
    "Fierbinti-Targ":        65583,
    "Filiasi":               83943,
    "Flamanzi":              39109,
    "Focsani":               79885,
    "Frasin":                85735,
    "Fundulea":              62537,
    "Gaesti":                63029,
    "Galati":                76959,
    "Gataia":                97169,
    "Geoagiu":               95379,
    "Gheorgheni":            29369,
    "Gherla":                54891,
    "Ghimbav":               28303,
    "Giurgiu":               64249,
    "Gura Humorului":        45363,
    "Harlau":                39897,
    "Harsova":               76559,
    "Hateg":                 95429,
    "Horezu":                89223,
    "Huedin":                54905,
    "Hunedoara":             95443,
    "Husi":                  47791,
    "Ianca":                 72129,
    "Iasi":                  39939,
    "Iernut":                30597,
    "Ineu":                  92767,
    "Insuratei":             72139,
    "Intorsura Buzaului":    28699,
    "Isaccea":               78833,
    "Jibou":                 57539,
    "Jimbolia":              97245,
    "Lehliu-Gara":           62599,
    "Lipova":                92777,
    "Liteni":                39635,
    "Livada":                58279,
    "Ludus":                 30629,
    "Lugoj":                 97265,
    "Lupeni":                96079,
    "Macin":                 78859,
    "Magurele":              24621,
    "Mangalia":              76625,
    "Marasesti":             80695,
    "Marghita":              49283,
    "Medgidia":              76635,
    "Medias":                32771,
    "Miercurea Nirajului":   30675,
    "Miercurea Sibiului":    33429,
    "Miercurea-Ciuc":        29481,
    "Mihailesti":            65349,
    "Milisauti":             45437,
    "Mioveni":               60231,
    "Mizil":                 66589,
    "Moinesti":              36671,
    "Moldova Noua":          93425,
    "Moreni":                63153,
    "Motru":                 84843,
    "Murfatlar":             76667,
    "Murgeni":               47905,
    "Nadlac":                92803,
    "Nasaud":                52361,
    "Navodari":              76673,
    "Negresti":              47919,
    "Negresti-Oas":          58321,
    "Negru Voda":            76681,
    "Nehoiu":                73773,
    "Novaci":                84889,
    "Nucet":                 63185,
    "Ocna Mures":            26103,
    "Ocna Sibiului":         33457,
    "Ocnele Mari":           89499,
    "Odobesti":              80777,
    "Odorheiu Secuiesc":     29859,
    "Oltenita":              62647,
    "Onesti":                36761,
    "Oradea":                49313,
    "Orastie":               96095,
    "Oravita":               93455,
    "Orsova":                87225,
    "Otelu Rosu":            93463,
    "Otopeni":               24645,
    "Ovidiu":                76709,
    "Panciu":                80799,
    "Pancota":               92811,
    "Pantelimon":            24647,
    "Pascani":               42493,
    "Patarlagele":           73871,
    "Pecica":                92823,
    "Petrila":               96135,
    "Petrosani":             96147,
    "Piatra Neamt":          43323,
    "Piatra-Olt":            87923,
    "Pitesti":               60321,
    "Ploiesti":              66613,
    "Plopeni":               66397,
    "Podu Iloaiei":          42509,
    "Pogoanele":             73909,
    "Popesti-Leordeni":      24663,
    "Potcoava":              87951,
    "Predeal":               28401,
    "Pucioasa":              63269,
    "Racari":                63283,
    "Radauti":               45563,
    "Ramnicu Sarat":         73953,
    "Ramnicu Valcea":        89649,
    "Rasnov":                28417,
    "Recas":                 97403,
    "Reghin":                30823,
    "Resita":                93513,
    "Roman":                 44319,
    "Rosiori de Vede":       69765,
    "Rovinari":              84979,
    "Roznov":                44823,
    "Rupea":                 28437,
    "Sacele":                28439,
    "Sacueni":               51289,
    "Salcea":                45583,
    "Saliste":               33523,
    "Salistea de Sus":       57037,
    "Salonta":               51303,
    "Sangeorgiu de Padure":  30849,
    "Sangeorz-Bai":          52439,
    "Sannicolau Mare":       97451,
    "Santana":               92875,
    "Sarmasu":               30907,
    "Satu Mare":             58409,
    "Saveni":                39409,
    "Scornicesti":           88041,
    "Sebes":                 26355,
    "Sebis":                 92901,
    "Segarcea":              84251,
    "Seini":                 57061,
    "Sfantu Gheorghe":       28763,
    "Sibiu":                 33555,
    "Sighetu Marmatiei":     57071,
    "Sighisoara":            30935,
    "Simeria":               96727,
    "Simleu Silvaniei":      57717,
    "Sinaia":                69029,
    "Siret":                 45625,
    "Slanic":                69047,
    "Slanic-Moldova":        37445,
    "Slatina":               88057,
    "Slobozia":              65709,
    "Solca":                 45633,
    "Somcuta Mare":          57105,
    "Sovata":                30961,
    "Stefanesti":            61607,
    "Stei":                  51393,
    "Strehaia":              87409,
    "Suceava":               45653,
    "Sulina":                78953,
    "Talmaciu":              34907,
    "Tandarei":              66025,
    "Targoviste":            63351,
    "Targu Bujor":           78655,
    "Targu Carbunesti":      85153,
    "Targu Frumos":          42699,
    "Targu Jiu":             85169,
    "Targu Lapus":           57147,
    "Targu Neamt":           44907,
    "Targu Ocna":            37503,
    "Targu Secuiesc":        29163,
    "Targu-Mures":           30987,
    "Tarnaveni":             32479,
    "Tasnad":                59497,
    "Tautii-Magheraus":      57159,
    "Techirghiol":           76775,
    "Tecuci":                78659,
    "Teius":                 26483,
    "Ticleni":               85663,
    "Timisoara":             97487,
    "Tismana":               85679,
    "Titu":                  63967,
    "Toplita":               30013,
    "Topoloveni":            61653,
    "Tulcea":                78971,
    "Turceni":               85705,
    "Turda":                 55259,
    "Turnu Magurele":        69899,
    "Ulmeni":                62715,
    "Ungheni":               32497,
    "Uricani":               96813,
    "Urlati":                69161,
    "Urziceni":              66029,
    "Valea lui Mihai":       51501,
    "Valenii de Munte":      69223,
    "Vanju Mare":            87449,
    "Vascau":                51521,
    "Vaslui":                48221,
    "Vatra Dornei":          46497,
    "Vicovu de Sus":         46517,
    "Victoria":              72305,
    "Videle":                69925,
    "Viseu de Sus":          57213,
    "Vlahita":               30057,
    "Voluntari":             24691,
    "Vulcan":                96889,
    "Zalau":                 57769,
    "Zarnesti":              28553,
    "Zimnicea":              69939,
    "Zlatna":                26683,
}
