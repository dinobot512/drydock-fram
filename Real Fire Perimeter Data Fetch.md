
- Go to **[https://firms.modaps.eosdis.nasa.gov/download/](https://firms.modaps.eosdis.nasa.gov/download/)**
- Fill in form to request data:
    - **Data source:** VIIRS S-NPP
    - **Date range:** 2025-01-07 to 2025-01-31
    - **Region:** draw a box over the Palisades area (west LA coast), or enter coordinates `-118.75, 33.95, -118.40, 34.15`
- Submit — they'll email you a download link within a few minutes
- Download the CSV

this should be all the data needed




---
Additionally, (if its helpful)
Drop the CSV in project folder and run the following script:
it will output a .geojson file & infogrpahic png 
# Palisades.py

(just copy-paste everything below)




"""  
palisades.py  
------------  
Reads the NASA FIRMS CSV downloaded from https://firms.modaps.eosdis.nasa.gov/download/  
and produces:  
    palisades_firms.geojson   — fire detections as GeoJSON    palisades_growth.png      — plot of daily detections and fire intensity  
Requirements:  
    pip install geopandas matplotlib pandas shapely"""  
  
import sys  
  
import geopandas as gpd  
import matplotlib.dates as mdates  
import matplotlib.pyplot as plt  
import pandas as pd  
  
# ---------------------------------------------------------------------------  
# Configuration  
# ---------------------------------------------------------------------------  
  
INPUT_CSV      = "palisades_data.csv"  
OUTPUT_GEOJSON = "palisades_firms.geojson"  
OUTPUT_PLOT    = "palisades_growth.png"  
  
  
# ---------------------------------------------------------------------------  
# Load CSV  
# ---------------------------------------------------------------------------  
  
print("=" * 60)  
print("Palisades Fire — plotting from FIRMS CSV")  
print("=" * 60)  
  
try:  
    df = pd.read_csv(INPUT_CSV)  
except FileNotFoundError:  
    print(f"\nERROR: Could not find '{INPUT_CSV}'")  
    print("Make sure the file is in the same folder as this script.")  
    sys.exit(1)  
  
print(f"\nLoaded {len(df)} rows")  
print(f"Columns: {df.columns.tolist()}")  
print(f"\nFirst few rows:")  
print(df.head(3).to_string())  
  
  
# ---------------------------------------------------------------------------  
# Parse datetime  
# ---------------------------------------------------------------------------  
  
if "acq_date" in df.columns and "acq_time" in df.columns:  
    df["acq_time_str"] = df["acq_time"].astype(str).str.zfill(4)  
    df["datetime"] = pd.to_datetime(  
        df["acq_date"] + " " + df["acq_time_str"].str[:2] + ":" + df["acq_time_str"].str[2:],  
        utc=True  
    )  
elif "acq_date" in df.columns:  
    df["datetime"] = pd.to_datetime(df["acq_date"], utc=True)  
else:  
    print("WARNING: No date column found — plots will use row index.")  
    df["datetime"] = pd.NaT  
  
df = df.sort_values("datetime").reset_index(drop=True)  
print(f"\nDate range: {df['datetime'].min()} to {df['datetime'].max()}")  
print(f"Total detections: {len(df)}")  
  
  
# ---------------------------------------------------------------------------  
# Save GeoJSON  
# ---------------------------------------------------------------------------  
  
gdf = gpd.GeoDataFrame(  
    df,  
    geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),  
    crs="EPSG:4326"  
)  
  
print(f"\nSaving GeoJSON -> {OUTPUT_GEOJSON}")  
gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON")  
print(f"  Done")  
  
  
# ---------------------------------------------------------------------------  
# Plot  
# ---------------------------------------------------------------------------  
  
print(f"\nGenerating plot -> {OUTPUT_PLOT}")  
  
has_frp = "frp" in df.columns and df["frp"].notna().any()  
  
daily = df.groupby(df["datetime"].dt.date).agg(  
    n_detections=("latitude", "count"),  
    **( {"mean_frp": ("frp", "mean")} if has_frp else {} )  
).reset_index()  
daily["datetime"] = pd.to_datetime(daily["datetime"])  
  
n_panels = 2 if has_frp else 1  
fig, axes = plt.subplots(n_panels, 1, figsize=(12, 3.5 * n_panels), sharex=True)  
if n_panels == 1:  
    axes = [axes]  
  
fig.suptitle(  
    "Palisades Fire — VIIRS fire detections (Jan 2025)\nSource: NASA FIRMS",  
    fontsize=12, y=0.99  
)  
  
axes[0].bar(daily["datetime"], daily["n_detections"], color="#c0392b", alpha=0.8, width=0.8)  
axes[0].set_ylabel("VIIRS detections per day", fontsize=10)  
axes[0].set_title("Daily fire pixel count  (burn activity proxy)", fontsize=10, loc="left")  
axes[0].grid(True, alpha=0.25, linestyle="--", axis="y")  
  
if has_frp and n_panels > 1:  
    frp_vals = daily["mean_frp"].astype(float)  
    axes[1].plot(daily["datetime"], frp_vals, color="#e67e22", linewidth=1.8)  
    axes[1].fill_between(daily["datetime"], frp_vals, alpha=0.12, color="#e67e22")  
    axes[1].set_ylabel("Mean FRP (MW)", fontsize=10)  
    axes[1].set_title("Mean Fire Radiative Power  (fire intensity)", fontsize=10, loc="left")  
    axes[1].grid(True, alpha=0.25, linestyle="--")  
  
axes[-1].set_xlabel("Date", fontsize=10)  
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))  
axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=2))  
fig.autofmt_xdate(rotation=30)  
  
plt.tight_layout()  
plt.savefig(OUTPUT_PLOT, dpi=150, bbox_inches="tight")  
plt.close()  
  
  
# ---------------------------------------------------------------------------  
# Done  
# ---------------------------------------------------------------------------  
  
print("\n" + "=" * 60)  
print("Done. Files written:")  
print(f"  {OUTPUT_GEOJSON}  ({len(gdf)} detections)")  
print(f"  {OUTPUT_PLOT}")  
print("=" * 60)  
print("\nTips:")  
print("  - Drop the GeoJSON into kepler.gl (kepler.gl/demo) to see")  
print("    all detections on a map with a time slider.")  
print("  - Load into QGIS and enable Temporal Controller to animate day by day.")