import json
import random
import re
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

AIRPORTS = [
    {"code": "JFK", "name": "John F. Kennedy, New York",   "region": "Northeast"},
    {"code": "LGA", "name": "LaGuardia, New York",          "region": "Northeast"},
    {"code": "EWR", "name": "Newark Liberty, NJ",           "region": "Northeast"},
    {"code": "BOS", "name": "Boston Logan",                  "region": "Northeast"},
    {"code": "PHL", "name": "Philadelphia Intl",             "region": "Northeast"},
    {"code": "DCA", "name": "Washington Reagan",             "region": "Northeast"},
    {"code": "IAD", "name": "Washington Dulles",             "region": "Northeast"},
    {"code": "BWI", "name": "Baltimore/Washington",          "region": "Northeast"},
    {"code": "ATL", "name": "Hartsfield-Jackson, Atlanta",  "region": "Southeast"},
    {"code": "MCO", "name": "Orlando Intl",                  "region": "Southeast"},
    {"code": "MIA", "name": "Miami Intl",                    "region": "Southeast"},
    {"code": "FLL", "name": "Fort Lauderdale",               "region": "Southeast"},
    {"code": "TPA", "name": "Tampa Intl",                    "region": "Southeast"},
    {"code": "CLT", "name": "Charlotte Douglas",             "region": "Southeast"},
    {"code": "RDU", "name": "Raleigh-Durham",                "region": "Southeast"},
    {"code": "MSY", "name": "New Orleans",                   "region": "Southeast"},
    {"code": "ORD", "name": "Chicago O'Hare",               "region": "Midwest"},
    {"code": "MDW", "name": "Chicago Midway",                "region": "Midwest"},
    {"code": "DTW", "name": "Detroit Metro",                 "region": "Midwest"},
    {"code": "MSP", "name": "Minneapolis-St. Paul",          "region": "Midwest"},
    {"code": "STL", "name": "St. Louis Lambert",             "region": "Midwest"},
    {"code": "CMH", "name": "Columbus Intl",                 "region": "Midwest"},
    {"code": "CLE", "name": "Cleveland Hopkins",             "region": "Midwest"},
    {"code": "IND", "name": "Indianapolis Intl",             "region": "Midwest"},
    {"code": "DFW", "name": "Dallas/Fort Worth",             "region": "South & Southwest"},
    {"code": "DAL", "name": "Dallas Love Field",             "region": "South & Southwest"},
    {"code": "IAH", "name": "Houston Bush",                  "region": "South & Southwest"},
    {"code": "HOU", "name": "Houston Hobby",                 "region": "South & Southwest"},
    {"code": "PHX", "name": "Phoenix Sky Harbor",            "region": "South & Southwest"},
    {"code": "LAS", "name": "Las Vegas Harry Reid",          "region": "South & Southwest"},
    {"code": "DEN", "name": "Denver Intl",                   "region": "South & Southwest"},
    {"code": "SAT", "name": "San Antonio Intl",              "region": "South & Southwest"},
    {"code": "LAX", "name": "Los Angeles Intl",              "region": "West Coast"},
    {"code": "SFO", "name": "San Francisco Intl",            "region": "West Coast"},
    {"code": "SJC", "name": "San Jose Mineta",               "region": "West Coast"},
    {"code": "OAK", "name": "Oakland Intl",                  "region": "West Coast"},
    {"code": "SEA", "name": "Seattle-Tacoma",                "region": "West Coast"},
    {"code": "PDX", "name": "Portland Intl",                 "region": "West Coast"},
    {"code": "SAN", "name": "San Diego Intl",                "region": "West Coast"},
    {"code": "SNA", "name": "Orange County",                 "region": "West Coast"},
]

AIRPORT_TIERS = {
    "ATL": 1, "LAX": 1, "ORD": 1, "DFW": 1, "DEN": 1,
    "JFK": 1, "SFO": 1, "SEA": 1, "LAS": 1, "MCO": 1,
    "MIA": 1, "CLT": 1, "EWR": 1, "PHX": 1, "IAH": 1,
    "BOS": 1, "MSP": 1, "DTW": 1, "FLL": 1, "LGA": 1,
    "PHL": 1, "BWI": 2, "DCA": 2, "IAD": 2, "TPA": 2,
    "MDW": 2, "PDX": 2, "SAN": 2, "HOU": 2, "DAL": 2,
    "STL": 2, "RDU": 2, "MSY": 2, "SNA": 2, "OAK": 2,
    "SJC": 2, "CMH": 3, "CLE": 3, "IND": 3, "SAT": 3,
}
BASE_WAIT = {1: 18, 2: 12, 3: 7}

# Cherry Hill, NJ → nearby airports
CHERRY_HILL = (39.9346, -75.0307)
NEARBY_AIRPORTS = {
    "PHL": (39.8721, -75.2411),
    "EWR": (40.6895, -74.1745),
    "JFK": (40.6413, -73.7781),
}


# ── FAA delay data ────────────────────────────────────────────────────────────

def parse_delay_minutes(s):
    """Parse FAA delay strings like '45 minutes', '1:30', '2 hrs' → int minutes."""
    if not s:
        return 0
    s = str(s).lower().strip()
    # "1:30" format
    m = re.match(r"(\d+):(\d+)", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # "45 minutes" or "2 hrs"
    m = re.search(r"(\d+)\s*(hr|hour|min)", s)
    if m:
        val = int(m.group(1))
        return val * 60 if "hr" in m.group(2) else val
    # bare number
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else 0


def fetch_faa_delays():
    """
    Returns dict: code → delay_multiplier
    1.0 = normal, >1.0 = congested, based on FAA ground/arrival/departure delays.
    """
    multipliers = {}
    try:
        res = requests.get(
            "https://nasstatus.faa.gov/api/airport-status-information",
            timeout=15
        )
        if res.status_code != 200:
            print(f"FAA API status {res.status_code}")
            return multipliers

        text = res.text.strip()
        if not text or text[0] not in ('{', '['):
            print("FAA returned no delay data (clear skies)")
            return multipliers
        data = json.loads(text)
        delay_types = data.get("airport_status_information", {}).get("delay_types", [])

        ground_stopped = set()
        delay_mins = {}   # code → max delay minutes seen

        for block in delay_types:
            # Ground stops → treat as very high congestion
            for gs in block.get("ground_stop_list") or []:
                code = gs.get("arpt", "").upper()
                if code:
                    ground_stopped.add(code)

            # Ground delays (avg minutes)
            for gd in block.get("ground_delay_list") or []:
                code = gd.get("arpt", "").upper()
                mins = parse_delay_minutes(gd.get("avg") or gd.get("max"))
                if code and mins:
                    delay_mins[code] = max(delay_mins.get(code, 0), mins)

            # Arrival / departure delays
            for ad in block.get("arrival_departure_delay_list") or []:
                code = ad.get("arpt", "").upper()
                adv = ad.get("arrival_departure", {})
                mins = parse_delay_minutes(adv.get("max") or adv.get("min"))
                if code and mins:
                    delay_mins[code] = max(delay_mins.get(code, 0), mins)

        # Convert to multipliers
        for code in ground_stopped:
            multipliers[code] = 2.0   # ground stop = very backed up

        for code, mins in delay_mins.items():
            if code not in multipliers:
                # 60-min delay → ~1.6x, 120-min → ~2.0x, capped at 2.2x
                multipliers[code] = min(1.0 + (mins / 100), 2.2)

        print(f"FAA delays: ground_stops={ground_stopped}, delay_airports={list(delay_mins.keys())}")
    except Exception as e:
        print(f"FAA fetch error: {e}")

    return multipliers


# ── TSA national throughput ───────────────────────────────────────────────────

def fetch_tsa_throughput_multiplier():
    """
    Scrapes today's TSA checkpoint passenger count from tsa.gov.
    Returns a multiplier: 1.0 = average day, >1.0 = busier than average.
    """
    try:
        res = requests.get(
            "https://www.tsa.gov/coronavirus/passenger-throughput",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if res.status_code != 200:
            return 1.0

        soup = BeautifulSoup(res.text, "html.parser")
        rows = []
        for row in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) >= 2:
                # Strip commas and parse number
                num_str = cells[1].replace(",", "").replace(" ", "")
                try:
                    rows.append(int(num_str))
                except ValueError:
                    pass

        if len(rows) < 2:
            return 1.0

        today = rows[0]
        # Use last 14 days as baseline average (skip today)
        recent = rows[1:15]
        avg = sum(recent) / len(recent) if recent else today
        mult = today / avg if avg else 1.0
        mult = max(0.6, min(mult, 1.6))   # clamp to sane range
        print(f"TSA throughput: today={today:,}, 14d avg={avg:,.0f}, multiplier={mult:.2f}")
        return mult
    except Exception as e:
        print(f"TSA throughput error: {e}")
        return 1.0


# ── Base estimate ─────────────────────────────────────────────────────────────

def base_estimate(code, now):
    tier = AIRPORT_TIERS.get(code, 2)
    base = BASE_WAIT[tier]

    hour = now.hour  # UTC (ET = UTC-4/5)
    dow  = now.weekday()

    if   10 <= hour < 14:  time_mult = 1.5    # 6–10am ET morning rush
    elif 20 <= hour < 24:  time_mult = 1.35   # 4–8pm ET afternoon rush
    elif 14 <= hour < 17:  time_mult = 0.85   # midday
    elif  3 <= hour <  7:  time_mult = 0.4    # overnight
    else:                  time_mult = 1.0

    if   dow in (4, 6):  day_mult = 1.2   # Fri / Sun
    elif dow in (1, 2):  day_mult = 0.8   # Tue / Wed
    else:                day_mult = 1.0

    rng   = random.Random(code + now.strftime("%Y%m%d%H"))
    noise = rng.uniform(0.88, 1.12)

    return max(1, round(base * time_mult * day_mult * noise))


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_wait_times():
    now              = datetime.now(timezone.utc)
    faa_multipliers  = fetch_faa_delays()
    national_mult    = fetch_tsa_throughput_multiplier()

    results = {}
    for airport in AIRPORTS:
        code  = airport["code"]
        est   = base_estimate(code, now)
        faa_m = faa_multipliers.get(code, 1.0)
        wait  = round(est * faa_m * national_mult)
        results[code] = max(1, wait)

    return results


# ── Drive times ───────────────────────────────────────────────────────────────

def fetch_drive_times():
    times = {}
    for code, (lat, lon) in NEARBY_AIRPORTS.items():
        try:
            url = (f"https://router.project-osrm.org/route/v1/driving/"
                   f"{CHERRY_HILL[1]},{CHERRY_HILL[0]};{lon},{lat}?overview=false")
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                secs = res.json()["routes"][0]["duration"]
                times[code] = round(secs / 60)
            else:
                times[code] = None
        except Exception as e:
            print(f"Drive time error {code}: {e}")
            times[code] = None
    print(f"Drive times: {times}")
    return times


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("Fetching TSA wait times...")
    wait_times  = fetch_wait_times()
    drive_times = fetch_drive_times()

    output = {
        "updated_at":  datetime.now(timezone.utc).isoformat(),
        "airports":    AIRPORTS,
        "wait_times":  wait_times,
        "drive_times": drive_times,
    }

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Done. {len(wait_times)} airports written.")


if __name__ == "__main__":
    main()
