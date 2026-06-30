# OLX Deal Finder

A small local web app that surfaces **underpriced bicycle listings on OLX.ro**.
You pick a city; it pulls current bike listings, groups them by brand/model,
and flags the statistical outliers — listings priced well below comparable ones —
with a plain, numbers-based explanation of *why* each is a good deal.

It only **finds candidates**. It does not judge condition or legitimacy — you
verify every listing by hand.

## How it works

1. **Fetch** — uses OLX.ro's internal JSON offers API (the same endpoint the
   site's own search calls), not HTML scraping. The bicycles category
   (`category_id=987`) and the `city_id` filter were confirmed from live traffic.
   Requests are polite: realistic User-Agent, ~1.5 s between pages, a max-pages
   cap, retries with exponential backoff on 403/429/timeout, and a 5-minute
   SQLite cache so repeated searches don't hammer the API.
2. **Parse** — each title is normalized hard (lowercase, Romanian diacritics
   stripped, spacing collapsed) and the brand + model are extracted. OLX's own
   `brand` tag is used as a hint when present; the title parser is the primary
   source.
3. **Group & score** — listings are regrouped by their **exact brand + model**
   (e.g. `Cube Touring SL`, not just `Cube`), and within each model group a
   **modified z-score** is computed from the **median** and **MAD** (median
   absolute deviation) — robust statistics suited to small, noisy samples.
4. **Flag** — a listing is a deal only when its model has at least
   **3 comparable listings** (a real second-hand market to value it against),
   its modified z-score is `≤ -1.5`, **and** it is at least **25%** below that
   model's median. A lone cheap listing of a one-off model — say a single
   `Cube Touring SL` with no other on OLX — is never flagged, because there is no
   way to estimate its market value.

## Install & run

Requires Python 3.11+.

```bash
pip install -r requirements.txt
```

### 1. CLI (verify the data + parsing)

```bash
python cli.py --city "Bucuresti"
python cli.py --city "Cluj-Napoca" --mode strict --no-cache --sample 15
```

Prints a sample of parsed listings, the full grouped breakdown
(brand+model, count, median, range), and the flagged deals with explanations.
Good for confirming the OLX integration and the parser before/while using the UI.

### 2. Web app

```bash
python app.py
```

Open <http://127.0.0.1:5000>. Pick a **city** (type to search), a **grouping
strategy**, choose how to **match** comparables, and hit **Find deals**.

- **Match by** (checkbox):
  - **checked — Brand + model** *(default)* — a listing is valued only against
    same brand+model comparables, so one-off models are never flagged.
  - **unchecked — Brand only** — values each listing against its whole brand pool
    (the looser, original behavior: more candidates, but a one-off model can look
    cheap against the brand).

Each deal card shows the thumbnail, price, the usual price (median) and typical
range, percent below median, city, post date, how many comparable listings back
the median (confidence), and an "Open on OLX" button.

Once results are in, a **filter bar** lets you narrow the cards by **brand** and
**model** (the model list follows the selected brand), with a **Reset filter**
button. Filtering is instant and client-side — it never re-queries OLX. Below the
cards is the breakdown (model-level when matching by brand+model, brand-level
otherwise) so you can sanity-check the grouping.

## Grouping strategies

Deals are **always** valued against same brand+model comparables (see step 4
above) — that part is not optional. The selectable mode only controls the
**noise filter and the breakdown view**: which listings enter the pool before
they are grouped by model.

| Mode | What it does | Trade-off |
|------|--------------|-----------|
| **Brand-only, kids/small-wheel excluded** *(default)* | Drops kids/junior and ≤20″ bikes from the pool; shows a brand-level breakdown | Balanced recall + precision |
| **Strict brand + model** | Keeps everything; shows the breakdown already grouped by brand+model | Same deals, model-level breakdown |
| **Brand-only, no filtering** | No guards — kids and small-wheel bikes stay in the pool | A kids model can be flagged if it has enough kids-model comparables |

## Tuning the thresholds

Everything tunable lives in [`config.py`](config.py):

- `MOD_Z_THRESHOLD` (default `-1.5`) — how extreme an outlier must be. More
  negative = stricter (fewer deals).
- `MIN_PERCENT_BELOW` (default `0.25`) — minimum discount below the median.
- `MIN_SAMPLES` (default `5`) / `STRICT_MIN_SAMPLES` (default `3`) — how many
  listings a *breakdown* group needs before its median is shown.
- `MIN_MODEL_COMPARABLES` (default `3`) — how many same brand+model listings
  (including the candidate) must exist before a deal can be flagged against that
  model's median. This is the guard against one-off "deals" with no comparables;
  raise it for stricter valuations, lower it (to `2`) to accept thinner markets.
- `MIN_PLAUSIBLE_PRICE` (default `100` lei) and `PART_NOISE_TOKENS` — noise
  filtering (junk prices and parts/accessories rather than whole bikes).
- `BRANDS` — known brands and their aliases (e.g. Btwin ↔ B'Twin ↔ Decathlon).
- `KIDS_TITLE_TOKENS` / `SMALL_WHEEL_MAX_INCHES` — what counts as a kids bike.
- `REQUEST_DELAY`, `MAX_PAGES`, `PAGE_LIMIT`, `MAX_RETRIES`, `CACHE_TTL_MINUTES` —
  politeness and caching.
- `CITIES` — city name → OLX `city_id`. To add a city, search it on olx.ro and
  read `location.city.id` from the offers API response, then add it here.

Start by relaxing `MIN_PERCENT_BELOW` or `MOD_Z_THRESHOLD` (toward `0`) if you
want more candidates, or tighten them to cut noise.

## Tests

```bash
pytest -q
```

Unit tests cover the brand/model parser and the outlier math against hand-made
data — no network access required.

## Architecture

```
config.py                  all tunable constants
cli.py                     CLI entry point
app.py                     Flask web app
olx_finder/
  models.py                Listing / Group / DealResult dataclasses
  parsing.py               normalization + brand/model + wheel/kids detection
  stats.py                 grouping modes + modified-z-score deal detection
  cache.py                 SQLite result cache + dedup
  sources/
    base.py                MarketplaceSource interface
    olx.py                 OlxSource (OLX.ro JSON API)
  templates/index.html     one-page UI
  static/style.css
tests/                     parser + stats unit tests
```

### Adding another marketplace

The marketplace is abstracted behind `MarketplaceSource` (`sources/base.py`).
To add Publi24 or another site, subclass it, implement
`search(query, city) -> list[Listing]` (returning normalized `Listing` objects)
and `supported_cities()`, then register it in `app.py`'s `SOURCES`. Nothing in
parsing, stats, or the UI needs to change.

A site that only makes sense for one product type (e.g. the bike-only
`biklo.ro`) goes in `PRODUCT_SOURCES` instead, keyed by product. Its checkbox
then appears only when that product is selected in the dropdown.

## Daily price history (background job)

The live app is *snapshot-only* — it values a listing against the prices that
happen to be live right now. The **daily job** builds a price history over time
so a listing can be judged against the **average of recent prices** instead.

Once a day it scrapes **bikes only**, from every source **except Facebook
Marketplace**, for Bucharest + 100 km, and appends what it sees to a durable
SQLite store (`history.db`, separate from the throwaway `cache.db`). Each
observation is stamped with the date and compared against the trailing
`HISTORY_WINDOW_DAYS` (30) of same brand+model prices; rows priced far enough
below that median are flagged as deals (`is_deal = 1`). The stack — and the
trustworthiness of the averages — grows with each run.

Run it manually:

```
python -m olx_finder.daily
```

The knobs live in `config.py` (`HISTORY_DB_PATH`, `HISTORY_WINDOW_DAYS`,
`HISTORY_MIN_OBSERVATIONS`, `HISTORY_CITY`, `HISTORY_DISTANCE_KM`); the deal
threshold reuses `MIN_PERCENT_BELOW`.

### Seeing the trend and margins

Once a few days have accumulated, read the stack back as a report — per
brand+model it shows the day-by-day price band (count / min / median / max), how
the median has drifted over the window, and the flip margin of buying the current
cheapest and reselling at the recent typical price (gross, net after the
condition-based fix-up buffer, and ROI — the same math as the live app's deal
cards):

```
python -m olx_finder.history_report                 # top models by gross margin
python -m olx_finder.history_report --brand Trek     # drill into one brand
python -m olx_finder.history_report --model marlin --days 60 --top 30
```

Because brand+model grouping is loose, a pool can mix sub-models (an alloy and a
carbon "Giant TCR"). Before computing a model's typical price and margins the
report trims off-band prices by their modified z-score (median + MAD), and notes
how many it dropped (`N off-band filtered`). Tiny samples are left untouched. The
guard is tunable via `HISTORY_TRIM_MOD_Z` / `HISTORY_TRIM_MIN_SAMPLE` in
`config.py`.

### Running it daily on a Raspberry Pi (cron)

After `pip install -r requirements.txt` on the Pi, add a once-a-day cron entry
(`crontab -e`) — here at 03:00, logging to a file:

```cron
0 3 * * * cd /home/pi/dealRadar && /usr/bin/python3 -m olx_finder.daily >> /home/pi/dealRadar/daily.log 2>&1
```

It needs no browser and no display (Facebook is excluded), so it runs headless
in the background. The web UI (`python app.py`) is unaffected and can later read
`history.db` if you want to surface the accumulated history.
