import os
import json
import requests
from datetime import datetime, timezone

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

def fetch_wait_times():
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    results = {}

    if not api_key:
        print("No RAPIDAPI_KEY set — writing null data")
        for a in AIRPORTS:
            results[a["code"]] = None
        return results

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "tsa-wait-times.p.rapidapi.com"
    }

    for airport in AIRPORTS:
        code = airport["code"]
        try:
            url = f"https://tsa-wait-times.p.rapidapi.com/waittimes/{code}"
            res = requests.get(url, headers=headers, timeout=10)
            if code in ("JFK", "LAX"):  # debug first run only for 2 airports
                print(f"DEBUG {code}: status={res.status_code} body={res.text[:300]}")
            if res.status_code == 200:
                data = res.json()
                # Handle both possible response shapes
                if isinstance(data, list) and len(data) > 0:
                    wait = data[0].get("wait_time") or data[0].get("WaitTime") or data[0].get("waitTime")
                elif isinstance(data, dict):
                    wait = data.get("wait_time") or data.get("WaitTime") or data.get("waitTime")
                else:
                    wait = None
                results[code] = int(wait) if wait is not None else None
            else:
                results[code] = None
        except Exception as e:
            print(f"Error fetching {code}: {e}")
            results[code] = None

    return results


def main():
    print("Fetching TSA wait times...")
    wait_times = fetch_wait_times()

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "airports": AIRPORTS,
        "wait_times": wait_times,
    }

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    filled = sum(1 for v in wait_times.values() if v is not None)
    print(f"Done. {filled}/{len(wait_times)} airports have data.")


if __name__ == "__main__":
    main()
