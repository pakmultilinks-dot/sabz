"""SABZ location intelligence: read the map, learn the neighborhood.

His demand: "system must analyze locations... see in the maps that there is a
school, there is something." So SABZ queries OpenStreetMap for what surrounds
an intersection (schools, offices, mosques, markets, hospitals) and
auto-generates time-of-day priority plans from it. No hand-tuning per junction.

Bearing convention: N=0, E=90, S=180, W=270 degrees from the intersection.
"""
import math
import requests

OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "SABZ-prototype/1.0 (LGU AI Championship research)"}

# amenity -> (time windows [(start_h, end_h)], reason)
# days: "schooldays" (Mon-Fri), "fri", "daily"
PLANS = {
    "school": ([(7.25, 8.5), (13.5, 15.0)], "schooldays", "school run"),
    "university": ([(8.0, 10.0), (15.0, 17.0)], "schooldays", "university commute"),
    "college": ([(7.25, 8.5), (13.5, 15.0)], "schooldays", "college run"),
    "office": ([(8.5, 10.0), (17.0, 19.5)], "schooldays", "office commute"),
    "marketplace": ([(17.0, 21.0)], "daily", "evening bazaar"),
    "place_of_worship": ([(12.0, 14.5)], "fri", "Jummah prayer"),
    "hospital": ([], "daily", "emergency corridor standby"),
}


def bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def bearing_to_approach(b):
    if b < 45 or b >= 315:
        return "N"
    if b < 135:
        return "E"
    if b < 225:
        return "S"
    return "W"


def approach_to_phase(a):
    return "NS" if a in ("N", "S") else "EW"


def fetch_pois(lat, lon, radius=600):
    q = (f"[out:json][timeout:30];("
         f"node(around:{radius},{lat},{lon})[\"amenity\"];"
         f"way(around:{radius},{lat},{lon})[\"amenity\"];"
         f");out center 60;")
    r = requests.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    pois = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        amenity = tags.get("amenity")
        if amenity not in PLANS:
            continue
        plat = el.get("lat") or el.get("center", {}).get("lat")
        plon = el.get("lon") or el.get("center", {}).get("lon")
        if plat is None:
            continue
        pois.append({"amenity": amenity,
                     "name": tags.get("name", "unnamed"),
                     "lat": plat, "lon": plon,
                     "bearing": bearing(lat, lon, plat, plon)})
    return pois


def find_schools_lahore(limit=5):
    q = ("[out:json][timeout:60];"
         'node(around:8000,31.5204,74.3587)["amenity"="school"];'
         f"out {limit};")
    r = requests.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    out = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        out.append({"name": tags.get("name", "unnamed school"),
                    "lat": el["lat"], "lon": el["lon"]})
    return out


def generate_plan(pois):
    """POIs -> prioritized list of {days, start, end, phase, reason, poi}."""
    plan = []
    for p in pois:
        windows, days, reason = PLANS[p["amenity"]]
        if not windows:
            continue
        appr = bearing_to_approach(p["bearing"])
        for start, end in windows:
            plan.append({"days": days, "start": start, "end": end,
                         "phase": approach_to_phase(appr),
                         "approach": appr, "reason": reason,
                         "poi": p["name"], "amenity": p["amenity"]})
    # school-day plans outrank generic ones on overlap; sort by start
    plan.sort(key=lambda e: (e["start"], e["days"] != "schooldays"))
    return plan


def schedule_fn(plan, sim_start_h=7.0, weekday="mon"):
    def sched(t):
        tod = sim_start_h + t / 3600.0
        for e in plan:
            if e["days"] == "fri" and weekday != "fri":
                continue
            if e["days"] == "schooldays" and weekday in ("sat", "sun"):
                continue
            if e["start"] <= tod <= e["end"]:
                return e["phase"]
        return None
    return sched


if __name__ == "__main__":
    print("Looking for schools in Lahore (OpenStreetMap)...")
    schools = find_schools_lahore()
    for s in schools:
        print(f"  - {s['name']} @ {s['lat']:.5f}, {s['lon']:.5f}")
    s0 = schools[0]
    print(f"\nAnalyzing 600 m around: {s0['name']}")
    pois = fetch_pois(s0["lat"], s0["lon"])
    print(f"Found {len(pois)} relevant POIs:")
    for p in pois[:12]:
        print(f"  [{p['amenity']}] {p['name']} -> {bearing_to_approach(p['bearing'])} approach")
    plan = generate_plan(pois)
    print(f"\nAuto-generated time-of-day plan ({len(plan)} windows):")
    for e in plan:
        print(f"  {e['days']:10s} {e['start']:5.2f}-{e['end']:5.2f}h "
              f"priority {e['phase']} ({e['reason']}: {e['poi'][:40]})")
