"""Generate aria2c input files for RebalanceIQ and StockIQ raw data downloads."""
import re
import sys
from datetime import date, timedelta
from urllib.parse import quote

import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1]  # directory for generated .txt lists
STATIONS_FILE = sys.argv[2]  # ghcnd-stations.txt

R = f"{ROOT}/RebalanceIQ/data/raw"
K = f"{ROOT}/StockIQ/data/raw"

ACS = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF"


def soql(base, params):
    """Build a Socrata URL with properly encoded SoQL parameters."""
    q = "&".join(f"${k}={quote(v, safe=',()*')}" for k, v in params.items())
    return f"{base}?{q}"


def entry(url, d, name):
    return f"{url}\n  dir={d}\n  out={name}\n"


bulk_r, bulk_k, api_r = [], [], []

# ---------------- RebalanceIQ ----------------
for m in range(1, 13):
    bulk_r.append(entry(f"https://s3.amazonaws.com/tripdata/2025{m:02d}-citibike-tripdata.zip",
                        f"{R}/citibike_trips", f"2025{m:02d}-citibike-tripdata.zip"))

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
for i, mon in enumerate(months, 1):
    bulk_r.append(entry(f"https://storage.googleapis.com/bike-sharing-history/new-york-city/citibike/2025/{mon}.parquet",
                        f"{R}/station_status_history", f"citibike_status_2025_{i:02d}.parquet"))

for f in ["station_information", "station_status", "system_information", "system_regions",
          "system_pricing_plans", "vehicle_types"]:
    bulk_r.append(entry(f"https://gbfs.lyft.com/gbfs/2.3/bkn/en/{f}.json", f"{R}/gbfs_snapshot", f"{f}.json"))

for wban, nm in [("72505394728", "central_park"), ("72503014732", "laguardia")]:
    bulk_r.append(entry(f"https://www.ncei.noaa.gov/data/local-climatological-data/access/2025/{wban}.csv",
                        f"{R}/noaa_lcd_weather", f"lcd_{nm}_{wban}_2025.csv"))

for t in ["b01003", "b01002", "b19013", "b19301", "b08301", "b08201", "b15003"]:
    bulk_r.append(entry(f"{ACS}/data/5YRData/acsdt5y2023-{t}.dat", f"{R}/census_acs_2023_5yr", f"acsdt5y2023-{t}.dat"))
bulk_r.append(entry(f"{ACS}/documentation/Geos20235YR.txt", f"{R}/census_acs_2023_5yr", "Geos20235YR.txt"))
bulk_r.append(entry(f"{ACS}/documentation/ACS20235YR_Table_Shells.txt", f"{R}/census_acs_2023_5yr", "ACS20235YR_Table_Shells.txt"))

bulk_r.append(entry("https://lehd.ces.census.gov/data/lodes/LODES8/ny/wac/ny_wac_S000_JT00_2023.csv.gz",
                    f"{R}/census_lodes", "ny_wac_S000_JT00_2023.csv.gz"))
bulk_r.append(entry("https://lehd.ces.census.gov/data/lodes/LODES8/ny/ny_xwalk.csv.gz",
                    f"{R}/census_lodes", "ny_xwalk.csv.gz"))
bulk_r.append(entry("https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_36_tract.zip",
                    f"{R}/census_tiger_tracts", "tl_2023_36_tract.zip"))
bulk_r.append(entry("https://date.nager.at/api/v3/PublicHolidays/2025/US", f"{R}/holidays", "us_public_holidays_2025.json"))

# Socrata API pulls (throttled separately)
start = date(2025, 1, 1)
wk = 1
while start <= date(2025, 12, 31):
    end = min(start + timedelta(days=6), date(2025, 12, 31))
    url = soql("https://data.ny.gov/resource/5wq4-mkjj.csv", {
        "select": "transit_timestamp,station_complex_id,station_complex,borough,latitude,longitude,"
                  "sum(ridership) as ridership,sum(transfers) as transfers",
        "where": f"transit_timestamp between '{start}T00:00:00' and '{end}T23:59:59'",
        "group": "transit_timestamp,station_complex_id,station_complex,borough,latitude,longitude",
        "limit": "5000000",
    })
    api_r.append(entry(url, f"{R}/mta_subway_hourly", f"mta_subway_hourly_2025_w{wk:02d}.csv"))
    start = end + timedelta(days=1)
    wk += 1

for ds in ["bkfu-528j", "tvpp-9vvx"]:
    api_r.append(entry(soql(f"https://data.cityofnewyork.us/resource/{ds}.csv", {
        "where": "start_date_time between '2025-01-01T00:00:00' and '2025-12-31T23:59:59'",
        "limit": "5000000"}), f"{R}/nyc_permitted_events", f"nyc_permitted_events_2025_{ds}.csv"))
api_r.append(entry(soql("https://data.cityofnewyork.us/resource/mzxg-pwib.geojson", {"limit": "1000000"}),
                   f"{R}/nyc_bike_routes", "nyc_bike_routes.geojson"))
api_r.append(entry(soql("https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson", {"limit": "100000"}),
                   f"{R}/nyc_nta_boundaries", "nyc_nta_2020.geojson"))

# ---------------- StockIQ ----------------
IDH = "https://idh-be.iowa.gov/api/v1/datasets"
for yr, ds in [(2020, 1257), (2021, 1258), (2022, 1259), (2023, 1260), (2024, 1261)]:
    bulk_k.append(entry(f"{IDH}/{ds}/rows.csv", f"{K}/iowa_liquor_sales", f"iowa_liquor_sales_{yr}.zip"))
    bulk_k.append(entry(f"{IDH}/{ds}/columns.json", f"{K}/iowa_liquor_sales", f"iowa_liquor_sales_{yr}_columns.json"))

for t in ["b01003", "b01001", "b01002", "b19013", "b19301", "b15003"]:
    bulk_k.append(entry(f"{ACS}/data/5YRData/acsdt5y2023-{t}.dat", f"{K}/census_acs_2023_5yr", f"acsdt5y2023-{t}.dat"))
bulk_k.append(entry(f"{ACS}/documentation/Geos20235YR.txt", f"{K}/census_acs_2023_5yr", "Geos20235YR.txt"))
bulk_k.append(entry(f"{ACS}/documentation/ACS20235YR_Table_Shells.txt", f"{K}/census_acs_2023_5yr", "ACS20235YR_Table_Shells.txt"))

bulk_k.append(entry("https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv",
                    f"{K}/census_population_estimates", "co-est2025-alldata.csv"))
bulk_k.append(entry("https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt",
                    f"{K}/census_zcta_county_crosswalk", "tab20_zcta520_county20_natl.txt"))
bulk_k.append(entry("https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip",
                    f"{K}/census_county_boundaries", "cb_2023_us_county_500k.zip"))
bulk_k.append(entry("https://apps.bea.gov/regional/zip/CAINC1.zip", f"{K}/bea_county_income", "CAINC1.zip"))
bulk_k.append(entry("https://apps.bea.gov/regional/zip/CAINC30.zip", f"{K}/bea_county_income", "CAINC30.zip"))
for yr in range(2020, 2025):
    bulk_k.append(entry(f"https://date.nager.at/api/v3/PublicHolidays/{yr}/US", f"{K}/holidays", f"us_public_holidays_{yr}.json"))

bulk_k.append(entry("https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt", f"{K}/noaa_ghcnd_weather", "ghcnd-stations.txt"))
with open(STATIONS_FILE) as fh:
    for line in fh:
        if re.match(r"^USW\d+", line) and line[38:40] == "IA":
            sid = line[:11]
            bulk_k.append(entry(f"https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/{sid}.csv",
                                f"{K}/noaa_ghcnd_weather", f"{sid}.csv"))

for name, items in [("bulk_rebalanceiq.txt", bulk_r), ("api_rebalanceiq.txt", api_r), ("bulk_stockiq.txt", bulk_k)]:
    with open(f"{OUT}/{name}", "w") as fh:
        fh.write("".join(items))
    print(name, len(items))
