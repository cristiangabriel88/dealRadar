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

# Rough fix-up cost (lei) subtracted when framing a deal's resale margin, so the
# "Est. margin" shown is what's left after a typical clean-up/touch-up.
TOUCHUP_BUFFER_LEI: float = 150.0

# Currency normalization. A few sources price listings in EUR (and Facebook in
# USD when hit logged-out); every price is converted to RON up front so all
# comparisons, the noise filter and the UI work in a single currency. Rough
# rates — bump them as the exchange rate drifts.
EUR_TO_RON: float = 5.07
USD_TO_RON: float = 4.35

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

# "Cheapest by brand" view: CHEAPEST_PER_BRAND_MAX is the hard cap of cheapest
# listings materialised per brand server-side; the UI's per-brand selector ranges
# 1..MAX and starts at CHEAPEST_PER_BRAND_DEFAULT.
CHEAPEST_PER_BRAND_MAX: int = 20
CHEAPEST_PER_BRAND_DEFAULT: int = 5

# --------------------------------------------------------------------------- #
# Sleepers — "the seller doesn't know what they have" scoring
# --------------------------------------------------------------------------- #
# The Sleepers view (see olx_finder/sleepers.py) ranks listings the deal engine
# discards (no recognised brand, so never grouped) by neglect/mislabel signals.
# Each signal adds its weight ONLY when its data is present, so a missing
# description or photo count never penalises a listing — it just can't fire that
# one signal. A listing is shown when its total score reaches SLEEPER_MIN_SCORE.
SLEEPER_WEIGHT_NO_BRAND: float = 3.0       # no known brand recognised in the title
SLEEPER_WEIGHT_SHORT_TITLE: float = 1.5    # terse, low-effort title
SLEEPER_WEIGHT_MIN_DESC: float = 1.5       # minimal/empty description (when known)
SLEEPER_WEIGHT_FEW_PHOTOS: float = 1.0     # one or no photos (when known)
SLEEPER_WEIGHT_CHEAP_CATEGORY: float = 3.0  # graded by how far below category median
SLEEPER_WEIGHT_MOTIVATED: float = 2.0      # "urgent", "mutare", "lichidare", …
SLEEPER_WEIGHT_PREMIUM_COMPONENT: float = 2.0  # title/desc names a premium part

SLEEPER_SHORT_TITLE_MAX_WORDS: int = 3     # titles with this many words or fewer
SLEEPER_MIN_DESC_CHARS: int = 40           # descriptions this short count as minimal
SLEEPER_FEW_PHOTOS_MAX: int = 1            # photo counts at or below this
# The cheap-vs-category signal starts contributing once a listing is this far
# below the category median, ramping linearly to its full weight at the cap.
SLEEPER_MIN_CATEGORY_BELOW: float = 0.30
SLEEPER_CATEGORY_BELOW_CAP: float = 0.70

SLEEPER_MIN_SCORE: float = 3.0   # minimum total score to surface as a sleeper
SLEEPER_MAX_RESULTS: int = 60    # hard cap on sleepers materialised per search

# Diacritic-stripped, lowercased tokens that mark a motivated/under-pressure
# seller (moving, liquidating, needs cash fast) — a soft "may take a low offer".
MOTIVATED_SELLER_TOKENS: frozenset[str] = frozenset(
    {
        "urgent", "urgenta", "mutare", "mut", "mutat", "plec", "plecare",
        "lichidare", "rapid", "repede", "graba", "imediat",
    }
)

# Tokens that mark scrap / broken / for-parts listings. A title hit zeroes the
# sleeper score so junk doesn't flood the top (frames are already dropped by
# PART_NOISE_TOKENS' "cadru").
SLEEPER_JUNK_TOKENS: frozenset[str] = frozenset(
    {
        "fier", "vechi", "defect", "dezmembrez", "dezmembrari", "stricat",
        "nefunctional",
    }
)

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

# "Strong" part tokens: a title containing one is a part/accessory being sold on
# its own, even if it also names a whole bike ("set piese bicicleta"). These
# rarely appear in a complete-bike title, so they drop the listing outright.
PART_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "cadru",      # frame
        "janta",      # rim
        "jante",      # rims
        "piese",      # parts
        "piesa",
        "anvelopa",   # tyre
        "anvelope",   # tyres
        "cauciuc",    # tyre/rubber
        "cauciucuri",
        "pompa",      # pump
        "casca",      # helmet
        "suport",     # rack/stand
        "portbagaj",  # carrier
    }
)

# "Component" tokens: words for parts that whole-bike listings ALSO routinely
# name ("bicicleta MTB 26 frane disc", "roti 29"). On their own they're
# ambiguous, so a listing with one of these is treated as a part only when
# nothing else signals a complete bike — no WHOLE_ITEM_TOKENS word and no known
# brand (see olx_finder/parsing.is_part_listing). This keeps genuine parts out
# while no longer discarding bikes described by their components — the very
# minimal-title listings the Sleepers view is meant to surface.
PART_COMPONENT_TOKENS: frozenset[str] = frozenset(
    {
        "roata",      # wheel
        "roti",       # wheels (also a bike's wheel size: "roti 29")
        "ghidon",     # handlebar
        "furca",      # fork
        "sa",         # saddle (matched as a whole word only)
        "pedale",     # pedals
        "pedala",
        "lant",       # chain
        "frana",      # brake
        "frane",      # brakes
        "schimbator", # derailleur
        "manete",     # shifters/levers
    }
)

# Words that mark a *complete* bike. Their presence overrides an ambiguous
# component token (so "bicicleta ... frane disc" stays a bike).
WHOLE_ITEM_TOKENS: frozenset[str] = frozenset(
    {
        "bicicleta", "biciclete", "bike", "mtb", "mountain", "cursiera",
        "trekking", "gravel", "bmx", "downhill", "enduro", "hardtail", "ebike",
    }
)

# Premium drivetrain/fork/material keywords. A cheap bike whose title or
# description names one of these is often worth more than its asking price —
# exactly the "seller doesn't know what they have" case — so the Sleepers scorer
# rewards them and shows which were found. Canonical label -> normalized aliases
# (same shape/whole-word matching as BRANDS; multi-word aliases supported).
PREMIUM_BIKE_COMPONENTS: dict[str, list[str]] = {
    "Deore": ["deore"],
    "SLX": ["slx"],
    "XT": ["xt", "deore xt"],
    "XTR": ["xtr"],
    "GRX": ["grx"],
    "SRAM": ["sram", "gx eagle", "nx eagle", "gx", "nx"],
    "RockShox": ["rockshox", "rock shox"],
    "Fox": ["fox"],
    "Manitou": ["manitou"],
    "Carbon": ["carbon"],
    "Hydraulic disc": ["hidraulic", "hidraulice", "hidraulica"],
    "Tubeless": ["tubeless"],
}

# Generic Romanian condition/sale descriptors that follow a model name in any
# product's listings and must never be mistaken for (a part of) a model. Shared
# by every product's model-stopword set.
GENERIC_DESCRIPTOR_TOKENS: frozenset[str] = frozenset(
    {
        "noua", "nou", "noi", "stare", "buna", "foarte", "ca", "si", "cu",
        "de", "in", "la", "pentru", "second", "hand", "import", "germania",
        "bun", "buni", "perfect", "perfecta", "impecabil", "impecabila",
        "intretinuta", "ingrijita", "urgent", "urgenta", "negociabil", "fix",
        "ieftin", "ieftina", "putin", "folosita", "folosit", "vand", "vanzare",
    }
)

# Tokens that are never part of a *bike* model (units, types, sizes), unioned
# with the generic descriptors above.
BIKE_MODEL_STOPWORDS: frozenset[str] = GENERIC_DESCRIPTOR_TOKENS | frozenset(
    {
        "mtb", "full", "suspension", "hardtail", "carbon", "aluminiu", "alu",
        "copii", "copil", "dama", "barbati", "femei", "baieti", "fete",
        "electrica", "electric", "ebike", "e", "bike", "bicicleta", "mountain",
        "cursiera", "city", "trekking", "gravel", "bmx", "downhill", "enduro",
        "viteze", "inch", "marimea", "marime", "roti", "roata",
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
# Known guitar brands and their normalized aliases
# --------------------------------------------------------------------------- #
#
# Same shape as BRANDS above, but for guitars. Ambiguous English words that
# double as common listing descriptors (e.g. "vintage", "flight") are left out
# so they don't mis-tag generic guitars. "Hora" is the Romanian maker (Reghin).
GUITAR_BRANDS: dict[str, list[str]] = {
    "Fender": ["fender"],
    "Squier": ["squier"],
    "Gibson": ["gibson"],
    "Epiphone": ["epiphone"],
    "Ibanez": ["ibanez"],
    "Yamaha": ["yamaha"],
    "Jackson": ["jackson"],
    "ESP": ["esp", "ltd", "esp ltd"],
    "Schecter": ["schecter"],
    "PRS": ["prs", "paul reed smith"],
    "Gretsch": ["gretsch"],
    "Cort": ["cort"],
    "Harley Benton": ["harley benton", "harleybenton"],
    "Takamine": ["takamine"],
    "Martin": ["martin"],
    "Taylor": ["taylor"],
    "Washburn": ["washburn"],
    "Dean": ["dean"],
    "Charvel": ["charvel"],
    "Music Man": ["music man", "musicman", "sterling"],
    "BC Rich": ["bc rich", "b c rich"],
    "Hohner": ["hohner"],
    "Stagg": ["stagg"],
    "Ortega": ["ortega"],
    "Cordoba": ["cordoba"],
    "Admira": ["admira"],
    "Alhambra": ["alhambra"],
    "Valencia": ["valencia"],
    "Aria": ["aria"],
    "Hagstrom": ["hagstrom"],
    "Framus": ["framus"],
    "Kremona": ["kremona"],
    "Eko": ["eko"],
    "Hora": ["hora"],
    "Lag": ["lag"],
    "Vox": ["vox"],
}

# Titles containing any of these tokens are guitar parts/accessories, not whole
# guitars, and are excluded from the analysis (mirrors PART_NOISE_TOKENS).
GUITAR_PART_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "husa",        # gig bag
        "toc",         # hard case
        "corzi",       # strings
        "coarda",      # string
        "pana",        # pick
        "pene",        # picks
        "pick",
        "pickuri",
        "doza",        # pickup
        "doze",        # pickups
        "ampli",       # amp
        "amplificator",
        "combo",       # combo amp
        "boxa",        # speaker
        "statie",      # amp head
        "pedala",      # effects pedal
        "efect",       # effect
        "efecte",
        "procesor",    # multi-fx
        "curea",       # strap
        "stativ",      # stand
        "stand",
        "suport",      # holder
        "acordor",     # tuner
        "metronom",
        "capodastru",  # capo
        "capo",
        "cablu",       # cable
        "jack",
        "diapazon",    # fretboard/diapason (sold as a part)
        "scaun",       # stool
    }
)

# Tokens that are never part of a *guitar* model (types, sizes), unioned with
# the generic descriptors.
GUITAR_MODEL_STOPWORDS: frozenset[str] = GENERIC_DESCRIPTOR_TOKENS | frozenset(
    {
        "chitara", "chitare", "guitar", "electrica", "electric", "acustica",
        "acustic", "clasica", "clasic", "classical", "electroacustica",
        "semiacustica", "bas", "bass", "ukulele", "copii", "copil",
        "incepatori", "incepator", "junior", "set", "pachet", "lemn",
        "profesionala", "profesional", "marimea", "marime",
    }
)

# Children's / junior guitars, excluded from the adult comparison pool in the
# guarded grouping mode (the guitar analogue of KIDS_TITLE_TOKENS for bikes).
GUITAR_KIDS_TITLE_TOKENS: frozenset[str] = frozenset(
    {"copii", "copil", "copilas", "junior"}
)

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

# OLX guitars: the offers API also accepts a bare ``query`` with no category, so
# rather than hard-code an unverified instruments category id we search by
# keyword only (None => the category_id param is omitted). Set this to the live
# "Chitare" category id if you want to scope OLX results more tightly.
OLX_GUITARS_CATEGORY_ID: int | None = None

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
# Publi24 musical-instruments category (same card markup / ?pag=N paging). It
# pools all instruments; non-guitars are dropped downstream since they carry no
# known guitar brand, and accessories are removed by GUITAR_PART_NOISE_TOKENS.
PUBLI24_GUITARS_URL: str = (
    "https://www.publi24.ro/anunturi/timp-liber-sport/instrumente-muzicale/"
)

# Lajumate: a Next.js site; the bikes category embeds listing JSON in the
# page's __NEXT_DATA__ script (?page=N paging). Cleaner than scraping its markup.
LAJUMATE_BASE: str = "https://lajumate.ro"
LAJUMATE_BICYCLES_URL: str = (
    "https://lajumate.ro/anunturi/sport-timp-liber-arta/biciclete-fitness-suplimente"
)
# Lajumate musical-instruments category. The same Next.js app serves this page
# (follow_redirects resolves it to the canonical route), so __NEXT_DATA__ parsing
# and ?page=N paging work as for bikes. Re-confirm the path if the site changes.
LAJUMATE_GUITARS_URL: str = (
    "https://lajumate.ro/anunturi_muzica-instrumente-muzicale.html"
)

# Anuntul: no bike-only category, so we keyword-search ("bicicleta") and let the
# downstream brand/parts filtering drop the non-bike noise (?page=N paging).
ANUNTUL_BASE: str = "https://www.anuntul.ro"
ANUNTUL_SEARCH_URL: str = "https://www.anuntul.ro/anunturi/"

# Biklo: a bike-only marketplace (Next.js front-end backed by a clean Laravel
# JSON API). Its "bazar" classifieds expose a per-category, page-based endpoint;
# we hit the whole-bikes ("biciclete") category directly and filter to the
# selected city client-side. Listing prices are always in RON. Images are served
# from the storage path on the same admin host.
BIKLO_BASE: str = "https://www.biklo.ro"
BIKLO_BICYCLES_URL: str = "https://admin.dirtbike.ro/api/bazar-ads-elastic/biciclete"
BIKLO_IMAGE_BASE: str = "https://admin.dirtbike.ro/storage/"

# Facebook Marketplace: login-gated and JS-rendered, so unlike the httpx sources
# above it is driven by a real browser (Playwright). The app launches Chromium
# with a dedicated, persistent profile; you log in once via
# ``python -m olx_finder.fb_login`` and every later search reuses that session
# headless. Marketplace is keyword-based (like OLX/Anuntul), so it uses
# ``Product.query`` and needs no per-product category URL.
#
# Marketplace results are pinned to whatever location the logged-in account last
# set (the app's account defaults to Paris), and that location can't be steered
# by query params — it lives server-side. So rather than try to follow the city
# picker, this source ALWAYS searches Bucharest and honours the UI's km radius
# selector via the ``radius`` query param. The location id below is the one
# Marketplace assigns to the Bucharest area; it must sit in the ``/marketplace/np/<id>/``
# path (the ``np`` — "neighbourhood page" — prefix is what makes the path-based
# location actually take; a bare ``/marketplace/<id>/`` is ignored).
FB_MARKETPLACE_BASE: str = "https://www.facebook.com/marketplace"
# Where the logged-in browser profile is stored (gitignored). Relative to the
# project root / wherever the app is launched.
FB_PROFILE_DIR: str = ".fb_profile"
# Infinite-scroll budget (the Marketplace analog of MAX_PAGES / REQUEST_DELAY):
# how many times to scroll to load more cards, and how long to wait for each
# batch to render before scrolling again.
FB_MAX_SCROLLS: int = 8
FB_SCROLL_PAUSE_MS: int = 1500
# Marketplace location id for the Bucharest area (read from the URL after setting
# the location to Bucharest in the picker). Every Facebook search is forced to
# this location; see the note above.
FB_LOCATION_ID: str = "113381412010894"
# Radius (km) to use when the UI asks for "this city only" (distance 0). The
# Bucharest pin sits on the city's edge, so a modest radius is needed to cover
# the whole city. Any non-zero UI distance is passed through to FB verbatim.
FB_DEFAULT_RADIUS_KM: int = 20
# The locality FB is always pinned to (see note above). Used to client-filter
# FB's results to the user's selected city scope and to skip the browser launch
# when that scope can't reach Bucharest.
FB_SEARCH_CITY: str = "Bucuresti"

# Default search query (the bikes product; see olx_finder/products.py).
DEFAULT_QUERY: str = "bicicleta"
# Keyword used to search guitars on the keyword-based sources (OLX, Anuntul).
GUITAR_QUERY: str = "chitara"

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

# Sentinel value for the "search all of Romania" entry in the city picker. When
# selected, sources drop the city filter entirely (OLX omits city_id; the
# client-filtered sources keep every listing).
ALL_CITIES: str = "All"

# Search-radius options (km) offered in the UI. 0 = the selected city only.
# Applied via OLX's native ``distance`` query param server-side, and by matching
# any MAIN_CITIES locality within range for the client-filtered sources.
DISTANCE_OPTIONS: list[int] = [0, 25, 50, 100, 150]
DEFAULT_DISTANCE: int = 0

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

# --------------------------------------------------------------------------- #
# Main cities -> (latitude, longitude).
# --------------------------------------------------------------------------- #
# The shortlist shown in the city picker: Bucharest plus every county capital
# (resedinta de judet). Every key MUST also exist in CITIES (so OLX's city_id
# lookup works). Coordinates back the "search radius" feature for the
# client-filtered sources: a listing counts as in range when its locality
# matches a main city within the selected radius of the chosen city. OLX uses
# its own server-side ``distance`` filter instead, so it is not limited to this
# shortlist.
MAIN_CITIES: dict[str, tuple[float, float]] = {
    "Bucuresti":              (44.4268, 26.1025),
    "Alba Iulia":             (46.0667, 23.5833),
    "Alexandria":             (43.9667, 25.3333),
    "Arad":                   (46.1667, 21.3167),
    "Bacau":                  (46.5667, 26.9167),
    "Baia Mare":              (47.6567, 23.5681),
    "Bistrita":               (47.1333, 24.5000),
    "Botosani":               (47.7500, 26.6667),
    "Braila":                 (45.2692, 27.9575),
    "Brasov":                 (45.6667, 25.6167),
    "Buzau":                  (45.1500, 26.8167),
    "Calarasi":               (44.2000, 27.3333),
    "Cluj-Napoca":            (46.7667, 23.6000),
    "Constanta":              (44.1733, 28.6383),
    "Craiova":                (44.3302, 23.7949),
    "Deva":                   (45.8833, 22.9000),
    "Drobeta-Turnu Severin":  (44.6361, 22.6561),
    "Focsani":                (45.6967, 27.1858),
    "Galati":                 (45.4353, 28.0080),
    "Giurgiu":                (43.9000, 25.9667),
    "Iasi":                   (47.1622, 27.5889),
    "Miercurea-Ciuc":         (46.3597, 25.8019),
    "Oradea":                 (47.0722, 21.9211),
    "Piatra Neamt":           (46.9275, 26.3708),
    "Pitesti":                (44.8565, 24.8692),
    "Ploiesti":               (44.9419, 26.0225),
    "Ramnicu Valcea":         (45.1000, 24.3667),
    "Resita":                 (45.3008, 21.8892),
    "Satu Mare":              (47.7919, 22.8856),
    "Sfantu Gheorghe":        (45.8667, 25.7833),
    "Sibiu":                  (45.7928, 24.1521),
    "Slatina":                (44.4308, 24.3719),
    "Slobozia":               (44.5639, 27.3661),
    "Suceava":                (47.6514, 26.2556),
    "Targoviste":             (44.9244, 25.4567),
    "Targu Jiu":              (45.0333, 23.2833),
    "Targu-Mures":            (46.5425, 24.5575),
    "Timisoara":              (45.7489, 21.2087),
    "Tulcea":                 (45.1719, 28.7919),
    "Vaslui":                 (46.6383, 27.7297),
    "Zalau":                  (47.1911, 23.0572),
}
