# Design Document: LANDFIRE Terrain Data Ingestion Pipeline

**Status:** Draft  
**Scope:** Automated fetch of LANDFIRE `.tif` rasters → population of `TerrainData` / `RasterLayer` dataclasses  
**Version:** TBD (LANDFIRE version to be locked during implementation)

---

## 1. Overview

This module fetches surface fuel and terrain raster layers from the LANDFIRE REST API, reprojects/aligns all layers to a common grid, and assembles them into a frozen `TerrainData` object whose `layers` dict contains one `RasterLayer` per product.

### 1.1 Target Layers

| `RasterLayer.name` | LANDFIRE Product Code | Description | Units |
|---|---|---|---|
| `fuel_load` | `FBFM40` (SB40 fuel model) | 1-hr fuel load | ton/ac |
| `fuel_sav` | `FBFM40` | Surface-area-to-volume ratio | ft²/ft³ |
| `fuel_depth` | `FBFM40` | Fuel bed depth | ft |
| `fuel_mx` | `FBFM40` | Dead fuel moisture of extinction | % |
| `fuel_h` | `FBFM40` | Heat content | BTU/lb |
| `dem` | `ELEV` | Digital elevation model | m |
| `canopy_cover` | `CC` | Canopy cover | % |
| `canopy_height` | `CH` | Canopy height | m |
| `slope` | derived from `ELEV` | Slope | degrees |
| `aspect` | derived from `ELEV` | Aspect | degrees |

> **Note:** SB40 fuel parameters (`fuel_load`, `fuel_sav`, `fuel_depth`, `fuel_mx`, `fuel_h`) are not delivered as separate rasters by LANDFIRE. The `FBFM40` product is a fuel model *index* raster. Fuel parameters are retrieved by joining each pixel's integer fuel model code against the standard Scott & Burgan 40 fuel model lookup table at runtime. See §4.3.

---

## 2. Data Source

### 2.1 LANDFIRE REST API

**Base URL:** `https://lfps.usgs.gov/arcgis/rest/services/LandFireProduct/MapServer`

Key endpoints:

| Endpoint | Purpose |
|---|---|
| `/export` | Export a map image / raster for a given AOI and product |
| `/identify` | Point query |
| `https://lfps.usgs.gov/helpdocs/productstable.html` | Product code reference |

LANDFIRE also provides a download service at:
`https://lfps.usgs.gov/lfps/landFirePortalInterface` (bulk `.zip` of GeoTIFFs).

For programmatic access the preferred endpoint is the **LFPS download API**:
```
GET https://lfps.usgs.gov/arcgis/rest/services/LandFireProduct/GPServer/
        LandFireProductDownload/submitJob
```

Parameters:

| Parameter | Type | Notes |
|---|---|---|
| `Layer_list` | `str` | Semicolon-delimited product codes e.g. `ELEV;FBFM40;CC;CH` |
| `Area_of_Interest` | `str` | WKT polygon or bounding box in WGS84 |
| `Output_Projection` | `str` | EPSG code or WKID e.g. `102039` (Albers CONUS) |
| `Resample_Resolution` | `int` | Cell size in output CRS units (meters) |
| `f` | `str` | `json` |

The job is async; poll `checkJobStatus` until `jobStatus == "esriJobSucceeded"`, then retrieve result URLs.

### 2.2 Versioning

LANDFIRE version is a runtime parameter (`lf_version: str`, e.g. `"220"` for LF 2.2.0). All product codes are prefixed with the version at fetch time (e.g. `220ELEV`, `220FBFM40`). Default should be the most recent stable release; lock to a specific version per project for reproducibility and record in `TerrainData.created_from`.

---

## 3. Module Structure

```
terrain/
├── __init__.py
├── dataclasses.py          # TerrainData, RasterLayer definitions (provided)
├── fetch.py                # LANDFIRE API client
├── io.py                   # GeoTIFF read/write helpers
├── reproject.py            # CRS alignment, reprojection, resampling
├── sb40_lookup.py          # SB40 fuel parameter lookup table + rasterization
├── terrain_builder.py      # Orchestrator: fetch → process → assemble TerrainData
└── utils.py                # Bounding box helpers, AOI validation
```

---

## 4. Processing Pipeline

```
AOI (lat/lon bbox or polygon)
        │
        ▼
┌─────────────────────────────┐
│  fetch.py                   │
│  Submit LFPS download job   │
│  Layer_list: ELEV FBFM40    │
│             CC CH           │
│  Poll until complete        │
│  Download .tif files        │
└────────────┬────────────────┘
             │  raw .tif files (native LANDFIRE CRS)
             ▼
┌─────────────────────────────┐
│  reproject.py               │
│  Determine primary CRS      │
│  (use ELEV as reference)    │
│  Reproject all layers to    │
│  primary CRS + grid         │
│  Resample to common res     │
└────────────┬────────────────┘
             │  aligned arrays
             ▼
┌─────────────────────────────┐
│  sb40_lookup.py             │
│  Read FBFM40 index array    │
│  Join → 5 fuel param arrays │
│  (load, SAV, depth, mx, h)  │
└────────────┬────────────────┘
             │  fuel parameter arrays
             ▼
┌─────────────────────────────┐
│  reproject.py               │
│  Derive slope & aspect      │
│  from DEM (richdem / numpy) │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  terrain_builder.py         │
│  Construct RasterLayer per  │
│  layer, assemble TerrainData│
└─────────────────────────────┘
```

### 4.1 CRS and Grid Alignment

- **Primary CRS:** taken from the `dem` (`ELEV`) layer as downloaded — typically Albers Equal Area Conic (EPSG:5070 for CONUS).
- All other layers are reprojected to match `dem` using `rasterio.warp.reproject` with `Resampling.nearest` for categorical layers (`FBFM40`) and `Resampling.bilinear` for continuous layers.
- `primary_transform` and `shape` are taken from the reprojected DEM grid.
- `resolution_m` is extracted from `primary_transform.a` (x pixel size); assert `|transform.a| == |transform.e|` (square pixels).

### 4.2 Slope and Aspect Derivation

Slope and aspect are derived from the DEM after reprojection using finite-difference gradients:

```python
# Using richdem or numpy gradient
dz_dx, dz_dy = np.gradient(dem_array, resolution_m, resolution_m)
slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
aspect_rad = np.arctan2(-dz_dy, dz_dx)
```

Units: degrees. NoData propagated from DEM nodata mask.

### 4.3 SB40 Fuel Parameter Lookup

LANDFIRE `FBFM40` delivers a single integer raster where each cell contains a fuel model code (1–256, per Scott & Burgan 2005). Five continuous parameter rasters are produced by vectorized lookup:

```python
# sb40_lookup.py
SB40_TABLE: Dict[int, Dict[str, float]] = {
    101: {"fuel_load": 0.2, "fuel_sav": 1500, "fuel_depth": 1.0,
          "fuel_mx": 0.15, "fuel_h": 8000},
    # ... all 40 models
}

def rasterize_fuel_params(fbfm40_array: np.ndarray, nodata: int) -> Dict[str, np.ndarray]:
    """Return dict of float32 arrays keyed by fuel param name."""
```

Source values per Scott & Burgan (2005) *Standard Fire Behavior Fuel Models: A Comprehensive Set for Use with Rothermel's Surface Fire Spread Model*. Units:

| Parameter | `RasterLayer.name` | Units | dtype |
|---|---|---|---|
| 1-hr fuel load | `fuel_load` | ton/ac | `float32` |
| Surface-area-to-volume ratio | `fuel_sav` | ft²/ft³ | `float32` |
| Fuel bed depth | `fuel_depth` | ft | `float32` |
| Moisture of extinction | `fuel_mx` | fraction (0–1) | `float32` |
| Heat content | `fuel_h` | BTU/lb | `float32` |

NoData: pixels where `fbfm40_array == nodata` → `np.nan` in all fuel param arrays.

---

## 5. `RasterLayer` Population

Each layer maps to `RasterLayer` fields as follows:

| `RasterLayer` field | Source |
|---|---|
| `name` | See §1.1 table |
| `array` | NumPy array after reproject/lookup; `float32` for continuous, `int16` for `fbfm40` index |
| `dtype` | `array.dtype` |
| `nodata` | From source `.tif` tag; `np.nan` for derived float layers |
| `crs` | `primary_crs` (all layers reprojected to match) |
| `transform` | `primary_transform` |
| `shape` | `(rows, cols)` matching primary grid |
| `resolution` | `(abs(transform.a), abs(transform.e))` in meters |
| `bounds` | `rasterio.transform.array_bounds(rows, cols, transform)` |
| `source` | Downloaded `.tif` path or LFPS job URL |
| `metadata` | LANDFIRE product code, version string, download timestamp |

---

## 6. `TerrainData` Population

| `TerrainData` field | Value |
|---|---|
| `layers` | Dict of all `RasterLayer` objects keyed by `name` |
| `primary_crs` | CRS of DEM layer |
| `primary_transform` | Transform of DEM layer |
| `shape` | `(rows, cols)` of primary grid |
| `resolution_m` | `primary_transform.a` (meters) |
| `origin_latlon` | NW corner transformed to WGS84 via `rasterio.transform.xy` + `pyproj.Transformer` |
| `bbox` | `(minx, miny, maxx, maxy)` in `primary_crs` from `rasterio.transform.array_bounds` |
| `created_from` | e.g. `"LANDFIRE 2.2.0 — LFPS job_id=abc123 — fetched 2025-01-01"` |
| `notes` | Optional: AOI description, any resampling warnings |

---

## 7. API Interface

```python
def build_terrain_data(
    aoi: Union[Tuple[float, float, float, float], shapely.geometry.Polygon],
    lf_version: str = "220",
    resolution_m: float = 30.0,
    output_crs: Optional[str] = None,   # default: EPSG:5070 Albers CONUS
    cache_dir: Optional[Path] = None,   # if set, skip fetch if tiles cached
) -> TerrainData:
    ...
```

`aoi` accepts either a `(west, south, east, north)` WGS84 bounding box or a Shapely polygon.

---

## 8. Dependencies

| Package | Use |
|---|---|
| `rasterio` | GeoTIFF I/O, CRS, transforms |
| `numpy` | Array ops |
| `pyproj` | CRS transforms, lat/lon conversion |
| `shapely` | AOI geometry handling |
| `httpx` or `requests` | LFPS API calls |
| `richdem` *(optional)* | Slope/aspect derivation (fallback: `numpy.gradient`) |

---

## 9. Open Questions

1. **LANDFIRE version locking** — confirm version per project; update `created_from` accordingly.
2. **Tile stitching** — for large AOIs LFPS may return multi-tile zips; stitching logic (`rasterio.merge`) needs to be added to `io.py` before reprojection.
3. **Unit convention** — confirm whether downstream fire model expects `fuel_mx` as fraction (0–1) or percent (0–100); current design uses fraction.
4. **Slope/aspect library** — `richdem` is more numerically accurate for steep terrain; evaluate whether `numpy.gradient` is sufficient.
5. **Rate limiting / job polling** — LFPS async jobs can take several minutes; implement exponential backoff with configurable timeout.
