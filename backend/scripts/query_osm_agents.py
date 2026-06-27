#!/usr/bin/env python3
"""
Query OSM Overpass API for mobile money agents and informal financial
services within each ward bounding box.
Runs at 1 req/sec to respect Overpass rate limits.
Expected runtime: 3-6 hours for all 9,308 wards.
Safe to interrupt and re-run — skips already-queried wards.

DB auth: connects as user=postgres with no inline password; the launching
environment must export PGPASSWORD (see scripts launched with the project .env).
"""
import psycopg2, requests, time, logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/osm_agents.log"),
    ]
)
log = logging.getLogger(__name__)

# Public Overpass mirrors, tried in order. The public instances rate-limit
# sustained load hard (HTTP 429/504), so we rotate mirrors and back off.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Seconds to sleep between successful requests (fair-use; public instances
# throttle aggressively below ~2s sustained).
REQUEST_DELAY = 2.0

# Overpass rejects requests without a descriptive User-Agent (HTTP 406), so
# every request must carry one — otherwise the whole run silently records zeros.
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "BankMap-AI/1.0 (financial-inclusion research; contact philiposita1041@gmail.com)",
})

conn = psycopg2.connect(host="localhost", port=5432, dbname="bankmap", user="postgres")
cur = conn.cursor()

cur.execute("""
    SELECT
        w.id, w.name, w.population,
        ST_YMin(w.geometry::box2d) as south,
        ST_XMin(w.geometry::box2d) as west,
        ST_YMax(w.geometry::box2d) as north,
        ST_XMax(w.geometry::box2d) as east
    FROM wards w
    WHERE w.osm_agent_queried = FALSE
      AND w.geometry IS NOT NULL
    ORDER BY w.population DESC NULLS LAST
""")
wards = cur.fetchall()
log.info(f"Wards to query: {len(wards)}")

def overpass_query(south, west, north, east):
    return f"""
[out:json][timeout:25];
(
  node["amenity"="mobile_money_agent"]({south},{west},{north},{east});
  node["amenity"="money_transfer"]({south},{west},{north},{east});
  node["shop"="mobile_money"]({south},{west},{north},{east});
  node["shop"="financial_services"]({south},{west},{north},{east});
  node["amenity"="payment_terminal"]({south},{west},{north},{east});
  node["amenity"="atm"]({south},{west},{north},{east});
  node["name"~"opay|moniepoint|palmpay|momo|kuda|paga|gtpay",i]({south},{west},{north},{east});
);
out body;
"""

def _parse(elements):
    mobile, pos, other = 0, 0, 0
    for el in elements:
        tags = el.get('tags', {})
        amenity = tags.get('amenity', '')
        shop    = tags.get('shop', '')
        name    = tags.get('name', '').lower()
        if (amenity in ('mobile_money_agent', 'money_transfer', 'payment_terminal')
                or shop in ('mobile_money', 'financial_services')
                or any(b in name for b in
                       ['opay','moniepoint','palmpay','momo','kuda','paga'])):
            mobile += 1
        elif amenity == 'atm':
            pos += 1
        else:
            other += 1
    return mobile, pos, other


def query(ward_id, south, west, north, east, retries=4):
    """
    Return (mobile, pos, other) on a successful query (HTTP 200), or None if
    every attempt failed (throttled/error). Callers MUST treat None as "skip,
    leave unqueried" — never record it as zeros, or persistent throttling would
    silently brand wards as having no agents.
    """
    body = {"data": overpass_query(south, west, north, east)}
    for attempt in range(retries):
        url = OVERPASS_MIRRORS[attempt % len(OVERPASS_MIRRORS)]  # rotate mirrors
        try:
            r = SESSION.post(url, data=body, timeout=40)
            if r.status_code == 200:
                return _parse(r.json().get('elements', []))
            if r.status_code in (429, 504, 502, 503):
                wait = 30 * (attempt + 1)
                log.warning(f"Ward {ward_id}: HTTP {r.status_code} on {url.split('/')[2]} "
                            f"— backoff {wait}s")
                time.sleep(wait)
                continue
            log.warning(f"Ward {ward_id}: HTTP {r.status_code} on {url.split('/')[2]}")
            time.sleep(5)
        except requests.exceptions.Timeout:
            log.warning(f"Ward {ward_id}: timeout attempt {attempt+1} ({url.split('/')[2]})")
            time.sleep(10 * (attempt + 1))
        except Exception as e:
            log.warning(f"Ward {ward_id}: {e}")
            time.sleep(5)
    return None  # all attempts failed — skip, do NOT mark queried

processed = 0
skipped = 0
for ward_id, ward_name, population, south, west, north, east in wards:
    result = query(ward_id, south, west, north, east)
    if result is None:
        # Throttled/errored on every attempt — leave osm_agent_queried = FALSE
        # so a later re-run retries this ward instead of recording false zeros.
        skipped += 1
        if skipped % 25 == 0:
            conn.commit()
            log.warning(f"Skipped {skipped} wards so far (throttled); they remain unqueried.")
        time.sleep(REQUEST_DELAY)
        continue

    mobile, pos, other = result
    total   = mobile + pos + other
    adults  = max((population or 0) * 0.55, 1)
    density = total / adults * 1000

    cur.execute("""
        UPDATE wards SET
            mobile_money_agents    = %s,
            pos_terminals          = %s,
            informal_finance_count = %s,
            agent_density_per_1000 = %s,
            osm_agent_queried      = TRUE
        WHERE id = %s
    """, (mobile, pos, other, density, ward_id))

    processed += 1
    if processed % 50 == 0:
        conn.commit()
        log.info(f"Progress: {processed} done, {skipped} skipped / {len(wards)} total "
                 f"— last: {ward_name} agents={mobile} pos={pos}")

    time.sleep(REQUEST_DELAY)

conn.commit()

cur.execute("""
    SELECT COUNT(*) FILTER (WHERE osm_agent_queried),
           SUM(mobile_money_agents),
           COUNT(*) FILTER (WHERE mobile_money_agents > 0)
    FROM wards
""")
queried, total_agents, wards_with_agents = cur.fetchone()
log.info(f"Done. Queried={queried} | Total agents={total_agents} | "
         f"Wards with agents={wards_with_agents}")

cur.close()
conn.close()
