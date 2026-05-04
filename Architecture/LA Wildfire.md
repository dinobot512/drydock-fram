# IGNIS × LA Wildfires: Implementation Guide

## Target

Reconstruct the January 7-8, 2025 Palisades Fire using real terrain, real weather station data, real ignition location. Demonstrate that IGNIS identifies the critical terrain features and wind channels where prediction uncertainty was highest — and where drone observations would have most improved the forecast.

## The Fire

- **Palisades Fire:** 95 km², ignited ~10:30 AM PST January 7 near 34.046°N, 118.526°W
- **Driven by:** Santa Ana winds gusting 60-100 mph through Santa Monica Mountain canyons
- **At 50m resolution:** ~38,000 cells (smaller than your current 200×200 = 40,000 test grid)
- **Compute requirement:** Trivial. This is 1× scale.

## Data Acquisition

### 1. Terrain from LANDFIRE (30 minutes)

```python
# Install
pip install landfire rasterio pyproj numpy

# Download
from landfire import Landfire

# Bounding box: covers Palisades Fire + buffer
# Pacific Palisades / Santa Monica Mountains
bbox = "-118.65,34.00,-118.40,34.12"  # west,south,east,north

lf = Landfire(bbox, output_crs="EPSG:32611")  # UTM zone 11N for LA

# Pull all needed layers
lf.request_data(
    layers=[
        "200F40_22",    # Scott & Burgan 40 fuel models (2022)
        "200EVT_22",    # Existing vegetation type
        "200CC_22",     # Canopy cover
        "200CH_22",     # Canopy height
        "200CBH_22",    # Canopy base height
        "200CBD_22",    # Canopy bulk density
        "ELEV2020",     # Elevation (DEM)
        "SLP2020",      # Slope
        "ASP2020",      # Aspect
    ],
    output_path="./data/landfire_la/"
)
```

**Fallback if LANDFIRE API is slow:** Download the full California LANDFIRE tiles (~2 GB) from https://landfire.gov/viewer/ and clip with rasterio:

```python
import rasterio
from rasterio.mask import mask
from shapely.geometry import box

bbox_geom = box(-118.65, 34.00, -118.40, 34.12)
with rasterio.open("full_ca_dem.tif") as src:
    clipped, transform = mask(src, [bbox_geom], crop=True)
```

**Resample to 50m:** LANDFIRE is 30m native. Downsample:

```python
from scipy.ndimage import zoom

factor = 30.0 / 50.0  # 0.6 — shrink
elevation_50m = zoom(elevation_30m, factor, order=1)  # bilinear for continuous
fuel_model_50m = zoom(fuel_model_30m, factor, order=0)  # nearest-neighbor for categorical
```

### 2. Weather Stations from Synoptic/MesoWest (1 hour)

Register for a free API token at https://api.synoptic.io/. The free tier provides sufficient access.

```python
import requests

# Find all stations within 50km of Palisades Fire center
url = "https://api.synopticdata.com/v2/stations/metadata"
params = {
    "token": "YOUR_TOKEN",
    "radius": "34.046,-118.526,50",  # 50km radius from fire center
    "status": "active",
    "vars": "air_temp,relative_humidity,wind_speed,wind_direction",
    "network": "1,2",  # NWS + RAWS networks
}
response = requests.get(url, params=params).json()

# Extract station IDs and locations
stations = []
for s in response["STATION"]:
    stations.append({
        "stid": s["STID"],
        "lat": float(s["LATITUDE"]),
        "lon": float(s["LONGITUDE"]),
        "elevation": float(s["ELEVATION"]),
        "name": s["NAME"]
    })
# Expect 10-30 stations in the LA basin
```

Pull historical time series for January 7-8:

```python
# Time series for all stations during the fire
stids = ",".join([s["stid"] for s in stations])
url = "https://api.synopticdata.com/v2/stations/timeseries"
params = {
    "token": "YOUR_TOKEN",
    "stid": stids,
    "start": "202501070000",  # Jan 7 midnight UTC
    "end": "202501090000",    # Jan 9 midnight UTC
    "vars": "air_temp,relative_humidity,wind_speed,wind_direction,fuel_moisture",
    "units": "temp|C,speed|m/s",
    "obtimezone": "UTC",
}
weather_data = requests.get(url, params=params).json()

# Parse into per-station time series
for station in weather_data["STATION"]:
    stid = station["STID"]
    obs = station["OBSERVATIONS"]
    timestamps = obs["date_time"]
    temp = obs.get("air_temp_set_1", [None] * len(timestamps))
    rh = obs.get("relative_humidity_set_1", [None] * len(timestamps))
    ws = obs.get("wind_speed_set_1", [None] * len(timestamps))
    wd = obs.get("wind_direction_set_1", [None] * len(timestamps))
    # Store for GP ingestion
```

**Key stations to look for near the fire:**

The Santa Monica Mountains have RAWS stations. Look for stations with IDs containing "RAWS" in network 2. CEDU (Cerro Negro), PTGU (Point Mugu), MALI (Malibu), and LAX ASOS are likely in range. The critical data: wind speed and direction during the January 7 Santa Ana event. Expect 15-30 m/s sustained winds with gusts to 40+ m/s at exposed stations.

### 3. Fire Ignition (5 minutes)

Hardcode in config:

```python
PALISADES_IGNITION = {
    "lat": 34.046,
    "lon": -118.526,
    "time_utc": "2025-01-07T18:30:00Z",  # 10:30 AM PST = 18:30 UTC
    "name": "Palisades Fire"
}
```

### 4. Validation Data — FIRMS Fire Detections (30 minutes)

Download VIIRS active fire detections from NASA FIRMS:

```
https://firms.modaps.eosdis.nasa.gov/api/area/csv/YOUR_MAP_KEY/VIIRS_SNPP_NRT/-118.65,34.00,-118.40,34.12/2/2025-01-07
```

Register for a free MAP_KEY at https://firms.modaps.eosdis.nasa.gov/api/area/. Returns CSV with latitude, longitude, brightness, scan, track, acquisition datetime, confidence for each fire detection.

This gives you 375m-resolution fire detections every ~12 hours. Use as ground truth for where the fire actually was at each time.

```python
import pandas as pd

firms = pd.read_csv("firms_viirs_palisades.csv")
firms["datetime"] = pd.to_datetime(firms["acq_date"] + " " + firms["acq_time"].astype(str).str.zfill(4), 
                                     format="%Y-%m-%d %H%M")
# Convert lat/lon to grid cells
firms["row"] = ((firms.lat - origin_lat) / resolution * -1).astype(int)
firms["col"] = ((firms.lon - origin_lon) / resolution).astype(int)
```

---

## Code Changes

### 1. Terrain Loader (new file: `ignis/data/la_terrain.py`)

Replace synthetic terrain generation with LANDFIRE data loading:

```python
import rasterio
from pyproj import Transformer
from scipy.ndimage import zoom

def load_la_terrain(landfire_dir: str, resolution_m: float = 50.0) -> TerrainData:
    """Load LANDFIRE GeoTIFFs for the LA fire domain."""
    
    layers = {}
    filenames = {
        "elevation": "ELEV2020.tif",
        "slope": "SLP2020.tif", 
        "aspect": "ASP2020.tif",
        "fuel_model": "200F40_22.tif",
        "canopy_cover": "200CC_22.tif",
        "canopy_height": "200CH_22.tif",
        "canopy_base_height": "200CBH_22.tif",
        "canopy_bulk_density": "200CBD_22.tif",
    }
    
    for name, fname in filenames.items():
        with rasterio.open(f"{landfire_dir}/{fname}") as src:
            data = src.read(1).astype(np.float32)
            if name == "fuel_model":
                data = data.astype(np.int16)
            
            if src.res[0] != resolution_m:
                factor = src.res[0] / resolution_m
                order = 0 if name == "fuel_model" else 1
                data = zoom(data, factor, order=order)
            
            layers[name] = data
            
            if name == "elevation":
                transform = src.transform
                crs = src.crs
    
    # LANDFIRE scaling factors
    layers["canopy_cover"] = layers["canopy_cover"] / 100.0          # percent → fraction
    layers["canopy_height"] = layers["canopy_height"] / 10.0         # 10×m → m
    layers["canopy_base_height"] = layers["canopy_base_height"] / 10.0
    layers["canopy_bulk_density"] = layers["canopy_bulk_density"] / 100.0  # 100×kg/m³ → kg/m³
    
    # Compute UTM origin
    origin_x = transform.c  # easting of top-left
    origin_y = transform.f  # northing of top-left
    
    return TerrainData(
        elevation=layers["elevation"],
        slope=layers["slope"],
        aspect=layers["aspect"],
        fuel_model=layers["fuel_model"],
        canopy_cover=layers["canopy_cover"],
        canopy_height=layers["canopy_height"],
        canopy_base_height=layers["canopy_base_height"],
        canopy_bulk_density=layers["canopy_bulk_density"],
        resolution_m=resolution_m,
        origin_x=origin_x,
        origin_y=origin_y,
        utm_epsg=str(crs),
        shape=layers["elevation"].shape
    )
```

### 2. Weather Ingestion (new file: `ignis/data/la_weather.py`)

Convert Synoptic API data to RAWS observations for the GP:

```python
def load_raws_for_time(weather_data: dict, target_time: datetime,
                       terrain: TerrainData, window_minutes: int = 30) -> dict:
    """
    Extract RAWS observations nearest to target_time.
    Returns dict with locations, fmc_vals, ws_vals, wd_vals for gp.add_raws().
    """
    transformer = Transformer.from_crs("EPSG:4326", terrain.utm_epsg)
    
    locations = []
    fmc_vals = []
    ws_vals = []
    wd_vals = []
    
    for station in weather_data["STATION"]:
        # Find observation closest to target_time
        times = pd.to_datetime(station["OBSERVATIONS"]["date_time"])
        idx = (times - target_time).abs().argmin()
        
        if abs((times[idx] - target_time).total_seconds()) > window_minutes * 60:
            continue  # no observation near target time
        
        # Convert lat/lon to grid cell
        lat = float(station["LATITUDE"])
        lon = float(station["LONGITUDE"])
        x, y = transformer.transform(lat, lon)
        row = int((terrain.origin_y - y) / terrain.resolution_m)
        col = int((x - terrain.origin_x) / terrain.resolution_m)
        
        if not (0 <= row < terrain.shape[0] and 0 <= col < terrain.shape[1]):
            continue  # station outside domain
        
        obs = station["OBSERVATIONS"]
        
        # Wind speed (already in m/s from API units param)
        ws = obs.get("wind_speed_set_1", [None])[idx]
        wd = obs.get("wind_direction_set_1", [None])[idx]
        temp = obs.get("air_temp_set_1", [None])[idx]
        rh = obs.get("relative_humidity_set_1", [None])[idx]
        
        if ws is None or wd is None:
            continue
        
        # Estimate FMC from temperature and humidity via simplified Nelson
        if temp is not None and rh is not None:
            fmc = estimate_nelson_fmc(temp, rh / 100.0, 
                                       terrain.slope[row, col],
                                       terrain.aspect[row, col])
        else:
            fmc = 0.06  # dry default for Santa Ana conditions
        
        locations.append((row, col))
        fmc_vals.append(fmc)
        ws_vals.append(ws)
        wd_vals.append(wd)
    
    return {
        "locations": locations,
        "fmc_vals": fmc_vals,
        "ws_vals": ws_vals,
        "wd_vals": wd_vals
    }
```

### 3. Nelson Model (new file: `ignis/nelson.py`)

Simplified Nelson for the GP prior mean:

```python
def compute_nelson_field(terrain: TerrainData, temperature_c: float,
                          relative_humidity: float, hour_utc: float) -> np.ndarray:
    """
    Compute Nelson dead fuel moisture at every grid cell.
    Simplified: equilibrium moisture from T/RH + terrain correction.
    """
    # Equilibrium moisture content (percent)
    rh_pct = relative_humidity * 100
    if rh_pct < 10:
        emc = 0.03229 + 0.281073 * rh_pct - 0.000578 * rh_pct * temperature_c
    elif rh_pct < 50:
        emc = 2.22749 + 0.160107 * rh_pct - 0.01478 * temperature_c
    else:
        emc = 21.0606 + 0.005565 * rh_pct**2 - 0.00035 * rh_pct * temperature_c
    
    emc_fraction = emc / 100.0
    
    # Terrain correction: south-facing slopes are drier
    aspect_rad = np.radians(terrain.aspect)
    solar_factor = np.clip(-np.cos(aspect_rad), 0, 1)  # 1 on south, 0 on north
    
    # Hour-of-day correction (PST = UTC - 8)
    hour_local = (hour_utc - 8) % 24
    # Afternoon (12-16) is driest, pre-dawn (4-8) is wettest
    diurnal = 0.02 * np.cos(2 * np.pi * (hour_local - 14) / 24)
    
    # Canopy shading retains moisture
    canopy_effect = 0.02 * terrain.canopy_cover
    
    # Slope effect: steep slopes drain faster
    slope_effect = -0.005 * np.clip(terrain.slope / 30, 0, 1)
    
    fmc = emc_fraction - 0.03 * solar_factor + diurnal + canopy_effect + slope_effect
    
    return np.clip(fmc, 0.02, 0.40).astype(np.float32)
```

**For the Santa Ana event:** temperature was ~20-25°C, RH was 5-15%, producing Nelson FMC estimates of ~3-6% — critically dry conditions. The GP corrections from RAWS data will adjust this where stations report differently.

### 4. FIRMS Validation Loader (new file: `ignis/data/la_validation.py`)

```python
def load_firms_detections(csv_path: str, terrain: TerrainData) -> dict:
    """
    Load VIIRS fire detections as time-stamped grid cells.
    Returns dict mapping timestamp -> list of (row, col) fire cells.
    """
    firms = pd.read_csv(csv_path)
    transformer = Transformer.from_crs("EPSG:4326", terrain.utm_epsg)
    
    detections = {}
    for _, row in firms.iterrows():
        x, y = transformer.transform(row.latitude, row.longitude)
        r = int((terrain.origin_y - y) / terrain.resolution_m)
        c = int((x - terrain.origin_x) / terrain.resolution_m)
        
        if not (0 <= r < terrain.shape[0] and 0 <= c < terrain.shape[1]):
            continue
        
        dt = pd.to_datetime(f"{row.acq_date} {str(row.acq_time).zfill(4)}", 
                           format="%Y-%m-%d %H%M")
        
        if dt not in detections:
            detections[dt] = []
        detections[dt].append((r, c))
    
    return detections
```

### 5. Scenario Runner (new file: `ignis/scenarios/palisades.py`)

Wire everything together for the Palisades reconstruction:

```python
def run_palisades_reconstruction(config):
    """
    Full IGNIS reconstruction of the January 7-8 Palisades Fire.
    """
    # 1. Load real terrain
    terrain = load_la_terrain("./data/landfire_la/", resolution_m=50.0)
    
    # 2. Load weather data
    weather = json.load(open("./data/weather_la.json"))
    
    # 3. Initialize GP with terrain
    gp = IGNISGPPrior(terrain=terrain, resolution_m=50.0)
    
    # 4. Load FIRMS validation data
    firms = load_firms_detections("./data/firms_palisades.csv", terrain)
    
    # 5. Simulation timeline: Jan 7 18:30 UTC to Jan 8 18:30 UTC (24 hours)
    start_time = datetime(2025, 1, 7, 18, 30, tzinfo=timezone.utc)
    end_time = datetime(2025, 1, 8, 18, 30, tzinfo=timezone.utc)
    cycle_interval = timedelta(minutes=20)
    
    # 6. Ignition
    ignition_cell = latlon_to_cell(34.046, -118.526, terrain)
    
    # 7. Ground truth wind evolution
    # Use RAWS time series interpolated to the grid as "ground truth"
    # (This is an approximation — real ground truth would be HRRR reanalysis)
    
    current_time = start_time
    cycle_count = 0
    results = []
    
    while current_time < end_time:
        cycle_count += 1
        sim_seconds = (current_time - start_time).total_seconds()
        
        # Update RAWS observations for this time
        raws = load_raws_for_time(weather, current_time, terrain)
        gp.add_raws(**raws)
        
        # Update Nelson mean for current conditions
        avg_temp = np.mean(raws["fmc_vals"]) * 100 + 20  # rough
        # Better: interpolate T/RH from RAWS stations
        nelson = compute_nelson_field(terrain, temperature_c=25.0,
                                       relative_humidity=0.10,
                                       hour_utc=current_time.hour)
        gp.set_nelson_mean(nelson)
        gp.update_time(sim_seconds)
        
        # Run IGNIS cycle
        report = orchestrator.run_cycle(observations=[])  # no drone obs in reconstruction
        
        # Compare ensemble prediction against FIRMS detections at this time
        # Find nearest FIRMS timestamp
        nearest_firms = find_nearest_firms(firms, current_time)
        if nearest_firms:
            validation = compare_prediction_vs_firms(
                report.ensemble.burn_probability,
                nearest_firms, terrain
            )
            report.validation = validation
        
        results.append(report)
        current_time += cycle_interval
    
    return results
```

---

## What Does NOT Change

|Component|Changes?|Notes|
|---|---|---|
|GP prior (gp.py)|No|Already handles real terrain, RAWS, Nelson, temporal decay|
|Fire engine|No|Operates on TerrainData regardless of source (synthetic or LANDFIRE)|
|Ensemble|No|Perturbation generation uses GP variance regardless of data source|
|Sensitivity computation|No|Operates on EnsembleResult arrays|
|Information field|No|Elementwise w = variance × sensitivity × observability|
|Greedy / QUBO selectors|No|Operate on information field|
|EnKF|No|Assimilates observations regardless of source|
|Simulation harness|Minimal|Ground truth uses RAWS interpolation instead of synthetic fields|

The entire core pipeline is data-source agnostic. The only new code is data loading and format conversion.

---

## What to Validate

### Quick Smoke Tests (first hour)

1. **Terrain loads correctly.** Plot elevation, fuel model, canopy cover. Verify the Santa Monica Mountains are visible, Pacific Palisades is identifiable, coastline is in the right place.
    
2. **CRS is correct.** Plot ignition point on terrain. It should be on the ridge above Pacific Palisades, not in the ocean.
    
3. **Fuel models are reasonable.** The Santa Monica Mountains should be primarily chaparral (fuel models 4, 5, 6 in Anderson 13, or SH/TL types in SB40). Urban areas may show non-burnable (NB) codes — this is correct.
    
4. **RAWS data exists and loads.** Print station count, location, and wind speed range. Expect 10-20 stations. Wind speeds on January 7 should show 15-40 m/s at exposed stations.
    
5. **Nelson FMC is reasonable.** Plot the Nelson field. Expect 3-8% on south-facing chaparral slopes, 8-15% on north-facing forested areas. If values are >20% everywhere, the T/RH inputs are wrong.
    

### Ensemble Validation (second hour)

6. **Fire spreads in the right direction.** Under Santa Ana winds (northeast to southwest), the ensemble should push fire toward the coast (southwest). If fire spreads north or east, wind direction conversion is wrong.
    
7. **Spread rate is reasonable.** The Palisades Fire grew from 10 acres to 11,000+ acres in ~12 hours. That's roughly 2-5 km/hr average ROS. If your ensemble predicts 50 m/hr or 50 km/hr, check Rothermel unit conversions.
    
8. **FIRMS overlay matches.** Plot ensemble burn probability at the time of a FIRMS overpass alongside the FIRMS detections. The high-probability cells should roughly overlap with FIRMS detections. Exact agreement isn't expected (your model uses interpolated wind, not the real microclimate), but gross direction and scale should match.
    

### Information Field Validation (third hour)

9. **w_i concentrates at terrain features.** The information field should highlight ridge lines, canyon mouths, and fuel-type transitions in the Santa Monica Mountains ahead of the fire — NOT uniform across the domain.
    
10. **Wind direction uncertainty is high in canyons.** Santa Ana winds are channeled through canyons. The GP, fitting wind direction from distant RAWS stations, should show high wind direction variance in narrow canyons where terrain steering is strongest and RAWS are absent.
    
11. **Drone placements target canyons and ridges.** The greedy selector should place simulated drones at the mouths of Topanga Canyon, Temescal Canyon, and along Mulholland Drive — the terrain features where wind channeling and FMC variation are highest.
    

---

## Timeline

|Task|Time|Depends on|
|---|---|---|
|Register Synoptic API + FIRMS API keys|15 min|Nothing — do first|
|Download LANDFIRE data|30 min|API key not needed|
|Download RAWS weather data|30 min|Synoptic API key|
|Download FIRMS fire detections|15 min|FIRMS MAP_KEY|
|Write terrain loader|1 hr|LANDFIRE data available|
|Write weather ingestion|1 hr|RAWS data available|
|Write Nelson model|30 min|Nothing|
|Write FIRMS validation loader|30 min|FIRMS data available|
|Write scenario runner|1 hr|All loaders working|
|Run + debug first cycle|1-2 hr|Everything above|
|Run full 24-hour reconstruction|30 min compute + 1 hr analysis|Debugging complete|
|Generate visualizations|1-2 hr|Results available|
|**Total**|**~8-10 hours**||

Parallelizable: data downloads can happen while writing loaders. Nelson model and FIRMS loader are independent of everything else.

---

## SSH Server Requirements

```bash
# Python packages (beyond what IGNIS already requires)
pip install landfire rasterio pyproj cfgrib requests pandas

# Disk space
# LANDFIRE tiles for LA: ~200 MB
# RAWS data: ~5 MB
# FIRMS data: ~1 MB
# Ensemble output per cycle: ~30 MB (200 members × 38K cells × 4 bytes)
# 72 cycles × 30 MB = ~2.2 GB total
# Total: ~3 GB comfortable

# Memory
# Ensemble in memory: ~30 MB (trivial)
# GP fitting: <100 MB
# Total: <500 MB RAM. Any server handles this.

# Compute
# 38,000 cells, 200 members, CPU multiprocessing
# ~15-30 seconds per cycle on 8 cores
# 72 cycles (24 hours at 20-min intervals): ~18-36 minutes total
# Add GP, info field, selectors: ~5 min overhead
# Total wall time: ~25-45 minutes for full reconstruction

# No GPU required at this scale.
```

---

## What Makes It Impressive

The reconstruction shows: "During the Palisades Fire, RAWS stations were 30-50 km from the active fire. The system identifies the critical terrain features — Topanga Canyon, the Mulholland ridgeline, the chaparral-urban interface — where wind and fuel moisture uncertainty most affected the predicted fire trajectory. Simulated drones are routed to these locations. After drone observations (simulated), the ensemble prediction narrows to match the actual FIRMS-observed fire progression."

The money visual: a side-by-side showing the information field (where IGNIS would send drones) overlaid on a map showing where the fire actually accelerated unexpectedly. If those overlap — if the system identifies the critical locations before the fire reaches them — that's the headline result.