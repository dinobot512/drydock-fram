## How terrain data works in AngryBird

### The `TerrainData` struct

Everything about terrain is held in a single frozen dataclass defined in `angrybird/types.py:11`:

```
@dataclass(frozen=True)class TerrainData:    elevation:           float32[rows, cols]   # metres    slope:               float32[rows, cols]   # degrees    aspect:              float32[rows, cols]   # degrees clockwise from north    fuel_model:          int8[rows, cols]      # Anderson 13 fire behaviour fuel model IDs (1-13)    resolution_m:        float                 # grid cell size in metres (default 50 m)    origin:              (lat, lon)            # WGS84 NW corner    shape:               (rows, cols)    # Optional canopy layers:    canopy_base_height:  float32[rows, cols]   # m (None if unavailable)    canopy_bulk_density: float32[rows, cols]   # kg/m³ (None if unavailable)    canopy_cover:        float32[rows, cols]   # fraction 0-1 (None if unavailable)
```

It is **frozen** — loaded once at startup and never mutated. All subsystems receive the same object and treat it as read-only.

---

### Two loading paths

#### Path 1: Real data — `tif_getter.download_terrain()` `angrybird/tif_getter.py`

This is the operational path for real terrain. It talks to the **LANDFIRE Product Service (LFPS)** REST API at `lfps.usgs.gov`:

1. **Submit job** — POST to `_SUBMIT_URL` with a bbox (min_lon, min_lat, max_lon, max_lat in WGS84) and a list of LANDFIRE layer codes:
    
    |Field|LANDFIRE layer code|Notes|
    |---|---|---|
    |`elevation`|`US_220DEM`|metres|
    |`slope`|`US_220SLPD`|degrees|
    |`aspect`|`US_220ASP`|degrees from north|
    |`fuel_model`|`US_220FBFM13`|Anderson 13 IDs|
    |`canopy_cover`|`US_220CC`|percent → ÷100 → fraction|
    |`canopy_base_height`|`US_220CBH`|metres|
    |`canopy_bulk_density`|`US_220CBD`|stored ×100 in LANDFIRE → ÷100|
    
2. **Poll** until `jobStatus == "esriJobSucceeded"` (5 s interval, 600 s timeout).
3. **Download zip** (cached to disk by job ID), extract GeoTIFFs.
4. **Reproject**: each `.tif` is reprojected with rasterio into the local **UTM zone** for the bbox centre (e.g. EPSG:32610 for western US), at `resolution_m` (default 50 m). All layers are snapped to the elevation DEM's grid so every array has the same `(rows, cols)`.
5. **Clean up**:
    - `nodata` sentinels → `0.0`
    - LANDFIRE non-burnable codes 91–99 → `0` (treated as non-fuel by the fire engine)
    - Anderson 13 IDs clipped to `[0, 13]`
    - CBD divided by 100 (LANDFIRE stores it scaled)
    - CC divided by 100 (percent → fraction)
6. **Slope/aspect fallback**: if LANDFIRE's slope or aspect layers are missing, they are derived from the elevation array using `numpy.gradient` (central differences) with the standard GIS formulae.
7. Returns `TerrainData` with `origin` as (lat, lon) of the NW corner, converted back from UTM via pyproj.

#### Path 2: Synthetic terrain — `terrain.synthetic_terrain()` `angrybird/terrain.py:76`

Used for offline development and tests. Generates a physically plausible fractal DEM:

- **DEM**: FFT-based 1/f² power-law spectrum (Brownian surface), normalised to 100–1600 m.
- **Slope/aspect**: computed from the DEM via Sobel operators (8-connected finite differences).
- **Fuel models**: assigned by elevation band to mimic vegetation zonation:
    - Below 500 m → grassland/chaparral (Anderson 1, 2, 3, 6, 7)
    - 500–900 m → shrub/open woodland (4, 5, 6, 7)
    - Above 900 m → timber/slash (8, 9, 10, 11)
- **Canopy arrays**: derived from per-fuel-model proxy lookup tables in `config.py` (`CANOPY_CBH_M`, `CANOPY_CBD_KGM3`, `CANOPY_COVER_FRACTION`), plus ±10% spatial jitter.

There is also an older `terrain.load_terrain()` function that wraps the `landfire` Python package, but `tif_getter.download_terrain()` is the production path that directly talks to the LFPS API.

---

### Coordinate convention

This is stated explicitly in `terrain.py:9`:

> All internal arrays are in a local UTM projection. lat/lon only appears at the boundary (bbox input, origin output field).

Once loaded, `row` = northing, `col` = easting. Distance between cells is always `resolution_m` metres. The `origin` field (lat, lon NW corner) is only used by: the Nelson FMC model (to compute solar angle from latitude) and any external coordinate lookups. Everything inside IGNIS uses grid indices.

---

### How terrain is consumed by each subsystem

#### Fire engine (`wispsim/gpu_fire_engine.py`, constructor)

Terrain is baked into GPU tensors **once at construction** and reused across all ensemble runs:

- **`_tan_slope_sq`**: `tan(slope_radians)²` — the Rothermel slope factor uses `tan²(φ)` directly
- **`_fuel_params`**: `(rows, cols, 8)` tensor — per-cell lookup into the Anderson 13 fuel parameter table (surface load, SAV ratio, moisture of extinction, heat content, etc.)
- **`_cbh` / `_cbd`**: canopy base height and bulk density for the Van Wagner crown fire transition model — taken from `terrain.canopy_base_height/canopy_bulk_density` if present, otherwise filled from per-fuel-model proxy tables
- **`_wind_adj`**: wind adjustment factor (10m → midflame height) derived from canopy cover fraction per fuel model

The fire engine does **not** use elevation directly — slope (derived from elevation) is what Rothermel needs. Aspect is also not used by the fire engine itself.

#### GP prior (`gp.py`)

The GP uses terrain for its **kernel distance metric**. The `_TerrainMatern32` kernel augments geographic distance with terrain dissimilarity:

```
d = geo_dist + alpha * |elev_diff| + beta * aspect_diff
```

Where `alpha=0.001` and `beta=0.005` are set in `config.py`. This means two cells that are geographically close but on opposite sides of a ridge (large elevation or aspect difference) are treated as more distant in GP space — their FMC estimates are less correlated. Observations near a ridgeline don't strongly influence predictions on the other side.

#### Nelson FMC model (`nelson.py`)

Uses `terrain.elevation` and `terrain.aspect` to compute spatially varying equilibrium moisture content:

- **Elevation**: lapse rate correction (temperature drops ~0.006°C/m → higher elevations are wetter)
- **Aspect**: south-facing slopes receive more solar radiation → dry out faster
- **Canopy cover**: derived from fuel model proxy tables — canopy attenuates incoming solar radiation, keeping shaded cells wetter

#### Ground truth FMC / wind field generation (`simulation/ground_truth.py`)

The ground truth uses terrain to create spatially realistic true conditions via the **Terrain Position Index (TPI)** — a local relief measure computed with a uniform filter over `TPI_FILTER_SIZE_CELLS=20` cells:

- Wind speed is amplified on ridges (positive TPI) and suppressed in valleys (negative TPI), scaled by `WIND_TPI_MODULATION=0.3`
- FMC is modified by aspect (south-facing dries), elevation (higher = wetter), TPI (ridge = drier), and canopy cover (canopy = wetter)

---

### Summary flow

```
bbox (WGS84)    │    ▼tif_getter.download_terrain()    │  LFPS API → GeoTIFFs → rasterio reproject to UTM → clean/scale    ▼TerrainData (frozen, metric coordinates)    │    ├──▶ GPUFireEngine.__init__()   → GPU tensors (_tan_slope_sq, _fuel_params,    │                                  _cbh, _cbd, _wind_adj) baked in once    │    ├──▶ IGNISGPPrior               → _TerrainMatern32 kernel uses elevation+aspect    │                                  to modulate spatial correlation    │    ├──▶ nelson_fmc_field()         → elevation + aspect + canopy → FMC prior mean    │    └──▶ GroundTruth generation     → TPI modulates wind + FMC spatial fields
```

The key design choice is that terrain is **static and loaded once** — it never changes during a run. All dynamic state (fire, wind, FMC estimates) lives elsewhere. This lets the fire engine pre-bake expensive terrain lookups as GPU tensors and reuse them across every ensemble member and every IGNIS cycle.