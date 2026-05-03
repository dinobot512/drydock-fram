# IGNIS × ELMFIRE: Integration Design Document

**Audience:** The team member responsible for making ELMFIRE work as the fire engine inside the IGNIS pipeline.

**Your job:** Build a Python wrapper (`ignis/fire_engine.py`) that takes GP-generated perturbation fields, runs ELMFIRE, and returns a numpy array of arrival times. Everything upstream (GP, perturbation generation) and downstream (information field, QUBO, EnKF) is someone else's code. You own the boundary.

---

## 1. What the Rest of the Pipeline Expects

Your wrapper must satisfy this interface:

```python
class FireEngine(Protocol):
    def run(self, snapshot: CycleSnapshot, config: EnsembleConfig) -> EnsembleResult:
        ...
```

**Input you receive:**

```python
@dataclass(frozen=True)
class CycleSnapshot:
    terrain: TerrainData           # static — elevation, slope, aspect, fuel_model, cbh, cbd, cc
    fire_state: np.ndarray         # float32[rows, cols] — current fire arrival times
    fuel_moisture_1hr: np.ndarray  # float32[rows, cols] — GP posterior mean for 1-hr FMC
    wind_speed: np.ndarray         # float32[rows, cols] — GP posterior mean, m/s at 10m
    wind_direction: np.ndarray     # float32[rows, cols] — GP posterior mean, degrees

@dataclass(frozen=True)
class EnsembleConfig:
    n_members: int                 # 200-1000
    horizon_hours: float           # 6.0
    perturbations: dict            # pre-generated perturbation fields from GP
        # perturbations["fmc_1hr"]:     float32[N, rows, cols]
        # perturbations["wind_speed"]:  float32[N, rows, cols]
        # perturbations["wind_dir"]:    float32[N, rows, cols]
```

The perturbation fields are GP-scaled spatially correlated noise fields. Each `perturbations["fmc_1hr"][n]` is a complete FMC field for ensemble member n — the GP mean plus a correlated perturbation scaled by local GP variance. These are in physical units (fraction for FMC, m/s for wind, degrees for direction).

**Output you must produce:**

```python
@dataclass(frozen=True)
class EnsembleResult:
    member_arrival_times: np.ndarray   # float32[N, rows, cols]
                                       # arrival time in seconds since simulation start
                                       # MAX_ARRIVAL (= 2 * horizon_hours * 3600) for unburned cells
    burn_probability: np.ndarray       # float32[rows, cols] — fraction of members that burned
    mean_arrival_time: np.ndarray      # float32[rows, cols]
    arrival_time_variance: np.ndarray  # float32[rows, cols]
    member_fmc_fields: np.ndarray      # float32[N, rows, cols] — the FMC used by each member
    member_wind_fields: np.ndarray     # float32[N, rows, cols] — the wind speed used by each member
    n_members: int
```

The `member_fmc_fields` and `member_wind_fields` are passed through from the input perturbations. The downstream sensitivity computation needs them to correlate arrival times with input perturbations.

---

## 2. How ELMFIRE Works

ELMFIRE is a Fortran executable. It reads GeoTIFF rasters from disk, runs the simulation, and writes GeoTIFF rasters to disk. There is no library API — no function calls, no shared memory, no pybind. Communication is entirely via files.

**ELMFIRE I/O flow:**

```
 Python wrapper                    ELMFIRE (Fortran binary)
      │                                    │
      ├─── Write input GeoTIFFs ──────────▶│
      │    (FMC, wind, terrain, phi)       │
      │                                    │
      ├─── Write elmfire.data config ─────▶│
      │                                    │
      ├─── subprocess.run(["elmfire"]) ───▶│ ──── runs simulation
      │                                    │
      │◀── Read output GeoTIFFs ──────────┤
      │    (time_of_arrival, flin, etc.)   │
      │                                    │
```

### Input Rasters (GeoTIFF)

**Terrain/fuels (10 files, written once at initialization):**

|File|Content|ELMFIRE units|Your units|Conversion|
|---|---|---|---|---|
|`asp.tif`|Aspect|degrees, Int16|degrees|none|
|`cbd.tif`|Canopy bulk density|100 × kg/m³, Int16|kg/m³|multiply by 100|
|`cbh.tif`|Canopy base height|10 × meters, Int16|meters|multiply by 10|
|`cc.tif`|Canopy cover|percent, Int16|fraction|multiply by 100|
|`ch.tif`|Canopy height|10 × meters, Int16|meters|multiply by 10|
|`dem.tif`|Elevation|meters, Int16|meters|none|
|`fbfm40.tif`|Fuel model (Scott & Burgan 40)|code, Int16|code|none|
|`slp.tif`|Slope|degrees, Int16|degrees|none|
|`adj.tif`|Spread rate adjustment|factor, Float32|—|set to 1.0|
|`phi.tif`|Initial level set|Float32|—|see Fire Initialization below|

**Weather (5 files, written per ensemble member):**

|File|Content|ELMFIRE units|Your units|Conversion|
|---|---|---|---|---|
|`m1.tif`|1-hr dead FMC|percent, Float32|fraction|multiply by 100|
|`m10.tif`|10-hr dead FMC|percent, Float32|fraction|multiply by 100|
|`m100.tif`|100-hr dead FMC|percent, Float32|fraction|multiply by 100|
|`ws.tif`|Wind speed|mph at 20ft, Float32|m/s at 10m|× 2.237 for mph, × 1.15 for 20ft|
|`wd.tif`|Wind direction|degrees, Float32|degrees|none|

**Critical unit conversions:**

```python
def to_elmfire_wind_speed(ws_ms_10m):
    """Convert 10m wind speed in m/s to 20-ft wind speed in mph."""
    ws_mph = ws_ms_10m * 2.23694       # m/s to mph
    ws_20ft = ws_mph * 1.15            # 10m to 20ft (approximate, varies with canopy)
    return ws_20ft

def to_elmfire_fmc(fmc_fraction):
    """Convert FMC fraction to percent."""
    return fmc_fraction * 100.0
```

Get these wrong and ROS will be off by orders of magnitude. Validate by comparing a single-cell ELMFIRE output against BehavePlus for the same conditions.

### Fire Initialization (phi raster)

ELMFIRE uses a level set function φ to represent the fire. φ < 0 means burned, φ > 0 means unburned. The initial fire is specified either via:

1. A phi raster where φ = -1 inside the initial fire and φ = +1 outside
2. An ignition point specified in the config file

For the first cycle, use an ignition point. For subsequent cycles (after EnKF updates the fire state), you'd need to construct a phi raster from the ensemble consensus fire perimeter. For the hackathon, ignition point is simpler:

```fortran
&IGNITION
IGNITION_TYPE = 'POINT'
IGNITION_X    = 500000.0    ! UTM easting of ignition
IGNITION_Y    = 4200000.0   ! UTM northing of ignition
/
```

### Configuration File (elmfire.data)

Fortran namelist format. Template with the fields you'll modify per member:

```fortran
&INPUTS
FUELS_AND_TOPOGRAPHY_DIRECTORY = './terrain'
ASP_FILENAME  = 'asp'
CBD_FILENAME  = 'cbd'
CBH_FILENAME  = 'cbh'
CC_FILENAME   = 'cc'
CH_FILENAME   = 'ch'
DEM_FILENAME  = 'dem'
FBFM_FILENAME = 'fbfm40'
SLP_FILENAME  = 'slp'
ADJ_FILENAME  = 'adj'
PHI_FILENAME  = 'phi'
WEATHER_DIRECTORY    = '{MEMBER_WEATHER_DIR}'
WS_FILENAME          = 'ws'
WD_FILENAME          = 'wd'
M1_FILENAME          = 'm1'
M10_FILENAME         = 'm10'
M100_FILENAME        = 'm100'
LH_MOISTURE_CONTENT  = 30.0
LW_MOISTURE_CONTENT  = 60.0
FOLIAR_MOISTURE_CONTENT = 100.0
WS_AT_10M            = .FALSE.
/

&COMPUTATIONAL_DOMAIN
A_SRS = '{UTM_EPSG}'
COMPUTATIONAL_DOMAIN_CELLSIZE   = 50.0
COMPUTATIONAL_DOMAIN_XLLCORNER  = {XMIN}
COMPUTATIONAL_DOMAIN_YLLCORNER  = {YMIN}
/

&TIME_CONTROL
SIMULATION_TSTART  = 0.0
SIMULATION_TSTOP   = {HORIZON_SECONDS}
SIMULATION_DT      = 5.0
SIMULATION_DTMAX   = 300.0
TARGET_CFL         = 0.4
/

&SIMULATOR
ALLOW_NONBURNABLE_PIXEL_IGNITION = .FALSE.
NUM_IGNITIONS = 1
/

&IGNITION
IGNITION_TYPE = 'POINT'
IGNITION_X    = {IGN_X}
IGNITION_Y    = {IGN_Y}
/

&OUTPUTS
OUTPUTS_DIRECTORY     = '{MEMBER_OUTPUT_DIR}'
DUMP_TIME_OF_ARRIVAL  = .TRUE.
DUMP_FLIN             = .TRUE.
DUMP_SPREAD_RATE      = .TRUE.
DUMP_CROWN_FIRE       = .TRUE.
DTDUMP                = {HORIZON_SECONDS}
/
```

### Output Files

ELMFIRE writes to the `OUTPUTS_DIRECTORY`. The files you need:

|File pattern|Content|Use|
|---|---|---|
|`time_of_arrival_XXXXXXX_YYYYYYY.tif`|Arrival time in seconds, Float32|**Primary output** — this IS your arrival time field|
|`flin_XXXXXXX_YYYYYYY.tif`|Fireline intensity, kW/m|For spotting risk overlay|
|`crown_fire_XXXXXXX_YYYYYYY.tif`|Crown fire type (0/1/2)|For bimodal regime detection|
|`spread_rate_XXXXXXX_YYYYYYY.tif`|Rate of spread, m/s|Diagnostic|

XXXXXXX = ensemble member number (7 digits, zero-padded) YYYYYYY = simulation time in seconds (7 digits)

Unburned cells in the time_of_arrival raster have a value of -1 or a very large number (depends on ELMFIRE version). Map these to MAX_ARRIVAL in your output.

---

## 3. Wrapper Implementation

### Directory Structure per Cycle

```
/tmp/ignis_elmfire/
├── terrain/                    # Written once at initialization
│   ├── asp.tif
│   ├── cbd.tif
│   ├── cbh.tif
│   ├── cc.tif
│   ├── ch.tif
│   ├── dem.tif
│   ├── fbfm40.tif
│   ├── slp.tif
│   ├── adj.tif
│   └── phi.tif
│
├── cycle_001/
│   ├── member_0000/
│   │   ├── weather/            # Per-member perturbed weather
│   │   │   ├── ws.tif
│   │   │   ├── wd.tif
│   │   │   ├── m1.tif
│   │   │   ├── m10.tif
│   │   │   └── m100.tif
│   │   ├── elmfire.data        # Per-member config
│   │   └── outputs/
│   │       └── time_of_arrival_0000001_021600.tif
│   ├── member_0001/
│   │   └── ...
│   └── member_0199/
│       └── ...
```

### Core Wrapper Code

```python
import subprocess
import numpy as np
import rasterio
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import shutil

class ElmfireEngine:
    def __init__(self, elmfire_binary: str = "elmfire",
                 work_dir: str = "/tmp/ignis_elmfire",
                 max_workers: int = 8):
        self.binary = elmfire_binary
        self.work_dir = Path(work_dir)
        self.max_workers = max_workers
        self.terrain_dir = self.work_dir / "terrain"
        self._terrain_written = False
        self._cycle_count = 0
        self._geo_meta = None  # rasterio profile for writing GeoTIFFs
    
    def _write_terrain(self, terrain: TerrainData, utm_epsg: str):
        """Write terrain rasters once. Reused across all cycles and members."""
        self.terrain_dir.mkdir(parents=True, exist_ok=True)
        
        profile = {
            "driver": "GTiff",
            "dtype": "int16",
            "width": terrain.shape[1],
            "height": terrain.shape[0],
            "count": 1,
            "crs": utm_epsg,
            "transform": rasterio.transform.from_origin(
                terrain.origin_x, terrain.origin_y,
                terrain.resolution_m, terrain.resolution_m
            ),
        }
        self._geo_meta = profile.copy()
        
        int16_layers = {
            "asp": terrain.aspect,
            "slp": terrain.slope,
            "dem": terrain.elevation,
            "fbfm40": terrain.fuel_model,
            "cc": (terrain.canopy_cover * 100).astype(np.int16),
            "ch": (terrain.canopy_height * 10).astype(np.int16),
            "cbh": (terrain.canopy_base_height * 10).astype(np.int16),
            "cbd": (terrain.canopy_bulk_density * 100).astype(np.int16),
        }
        for name, data in int16_layers.items():
            self._write_raster(self.terrain_dir / f"{name}.tif",
                             data.astype(np.int16), profile)
        
        float_profile = {**profile, "dtype": "float32"}
        self._write_raster(self.terrain_dir / "adj.tif",
                         np.ones(terrain.shape, dtype=np.float32), float_profile)
        
        # Initial phi: +1 everywhere (unburned). Ignition set via config.
        self._write_raster(self.terrain_dir / "phi.tif",
                         np.ones(terrain.shape, dtype=np.float32), float_profile)
        
        self._terrain_written = True
    
    def run(self, snapshot: CycleSnapshot, config: EnsembleConfig) -> EnsembleResult:
        """Run N ensemble members through ELMFIRE. Returns EnsembleResult."""
        if not self._terrain_written:
            self._write_terrain(snapshot.terrain, snapshot.utm_epsg)
        
        self._cycle_count += 1
        cycle_dir = self.work_dir / f"cycle_{self._cycle_count:03d}"
        
        N = config.n_members
        rows, cols = snapshot.terrain.shape
        horizon_s = config.horizon_hours * 3600
        MAX_ARRIVAL = 2.0 * horizon_s
        
        # Step 1: Write per-member weather rasters
        member_dirs = []
        for n in range(N):
            member_dir = cycle_dir / f"member_{n:04d}"
            weather_dir = member_dir / "weather"
            output_dir = member_dir / "outputs"
            weather_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            fmc_pct = config.perturbations["fmc_1hr"][n] * 100.0
            ws_mph_20ft = config.perturbations["wind_speed"][n] * 2.23694 * 1.15
            wd_deg = config.perturbations["wind_dir"][n]
            
            float_profile = {**self._geo_meta, "dtype": "float32"}
            self._write_raster(weather_dir / "m1.tif", fmc_pct.astype(np.float32), float_profile)
            self._write_raster(weather_dir / "m10.tif", (fmc_pct * 1.2).astype(np.float32), float_profile)
            self._write_raster(weather_dir / "m100.tif", (fmc_pct * 1.5).astype(np.float32), float_profile)
            self._write_raster(weather_dir / "ws.tif", ws_mph_20ft.astype(np.float32), float_profile)
            self._write_raster(weather_dir / "wd.tif", wd_deg.astype(np.float32), float_profile)
            
            # Write config
            self._write_config(member_dir, weather_dir, output_dir,
                             snapshot, horizon_s)
            
            member_dirs.append(member_dir)
        
        # Step 2: Run all members in parallel
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._run_single, d): i 
                for i, d in enumerate(member_dirs)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Member {idx} failed: {e}")
        
        # Step 3: Read arrival times
        arrival_times = np.full((N, rows, cols), MAX_ARRIVAL, dtype=np.float32)
        for n, member_dir in enumerate(member_dirs):
            toa = self._read_arrival_time(member_dir / "outputs", horizon_s)
            if toa is not None:
                # Replace ELMFIRE's unburned sentinel with our MAX_ARRIVAL
                toa[toa < 0] = MAX_ARRIVAL          # ELMFIRE uses -1 for unburned
                toa[toa > MAX_ARRIVAL] = MAX_ARRIVAL # catch any large values
                arrival_times[n] = toa
        
        # Step 4: Compute derived fields
        burned = arrival_times < (MAX_ARRIVAL * 0.9)
        burn_probability = burned.mean(axis=0).astype(np.float32)
        
        # Mean arrival time (only over members that burned)
        masked = np.where(burned, arrival_times, np.nan)
        with np.errstate(invalid='ignore'):
            mean_arrival = np.nanmean(masked, axis=0).astype(np.float32)
        mean_arrival = np.nan_to_num(mean_arrival, nan=MAX_ARRIVAL)
        
        variance = arrival_times.var(axis=0).astype(np.float32)
        
        # Step 5: Cleanup (optional — keep for debugging)
        # shutil.rmtree(cycle_dir)
        
        return EnsembleResult(
            member_arrival_times=arrival_times,
            burn_probability=burn_probability,
            mean_arrival_time=mean_arrival,
            arrival_time_variance=variance,
            member_fmc_fields=config.perturbations["fmc_1hr"],
            member_wind_fields=config.perturbations["wind_speed"],
            n_members=N
        )
    
    def _run_single(self, member_dir: Path):
        """Run one ELMFIRE instance."""
        result = subprocess.run(
            [self.binary, str(member_dir / "elmfire.data")],
            cwd=str(member_dir),
            capture_output=True,
            timeout=120  # kill if takes longer than 2 minutes
        )
        if result.returncode != 0:
            raise RuntimeError(f"ELMFIRE failed: {result.stderr.decode()[:500]}")
    
    def _read_arrival_time(self, output_dir: Path, horizon_s: float):
        """Find and read the time_of_arrival raster from ELMFIRE output."""
        toa_files = list(output_dir.glob("time_of_arrival_*.tif"))
        if not toa_files:
            return None
        # Take the last one (final simulation time)
        toa_file = sorted(toa_files)[-1]
        with rasterio.open(toa_file) as src:
            return src.read(1).astype(np.float32)
    
    def _write_raster(self, path: Path, data: np.ndarray, profile: dict):
        """Write a 2D numpy array as a single-band GeoTIFF."""
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)
    
    def _write_config(self, member_dir, weather_dir, output_dir,
                      snapshot, horizon_s):
        """Write elmfire.data config for one member."""
        config_text = f"""&INPUTS
FUELS_AND_TOPOGRAPHY_DIRECTORY = '{self.terrain_dir}'
ASP_FILENAME  = 'asp'
CBD_FILENAME  = 'cbd'
CBH_FILENAME  = 'cbh'
CC_FILENAME   = 'cc'
CH_FILENAME   = 'ch'
DEM_FILENAME  = 'dem'
FBFM_FILENAME = 'fbfm40'
SLP_FILENAME  = 'slp'
ADJ_FILENAME  = 'adj'
PHI_FILENAME  = 'phi'
WEATHER_DIRECTORY    = '{weather_dir}'
WS_FILENAME          = 'ws'
WD_FILENAME          = 'wd'
M1_FILENAME          = 'm1'
M10_FILENAME         = 'm10'
M100_FILENAME        = 'm100'
LH_MOISTURE_CONTENT  = 30.0
LW_MOISTURE_CONTENT  = 60.0
FOLIAR_MOISTURE_CONTENT = 100.0
/

&COMPUTATIONAL_DOMAIN
A_SRS = '{snapshot.utm_epsg}'
COMPUTATIONAL_DOMAIN_CELLSIZE = {snapshot.terrain.resolution_m}
COMPUTATIONAL_DOMAIN_XLLCORNER = {snapshot.terrain.origin_x}
COMPUTATIONAL_DOMAIN_YLLCORNER = {snapshot.terrain.origin_y}
/

&TIME_CONTROL
SIMULATION_TSTART = 0.0
SIMULATION_TSTOP  = {horizon_s}
SIMULATION_DT     = 5.0
SIMULATION_DTMAX  = 300.0
TARGET_CFL        = 0.4
/

&SIMULATOR
ALLOW_NONBURNABLE_PIXEL_IGNITION = .FALSE.
NUM_IGNITIONS = 1
/

&IGNITION
IGNITION_TYPE = 'POINT'
IGNITION_X    = {snapshot.ignition_x}
IGNITION_Y    = {snapshot.ignition_y}
/

&OUTPUTS
OUTPUTS_DIRECTORY    = '{output_dir}'
DUMP_TIME_OF_ARRIVAL = .TRUE.
DUMP_FLIN            = .TRUE.
DUMP_CROWN_FIRE      = .TRUE.
DTDUMP               = {horizon_s}
/
"""
        (member_dir / "elmfire.data").write_text(config_text)
```

---

## 4. Critical Things to Get Right

### Unit Conversions

This is the #1 source of bugs. ELMFIRE uses a mix of Imperial and metric, and LANDFIRE has its own scaling conventions.

**Validation test:** Before running any ensemble, run a single ELMFIRE simulation with fuel model 1 (short grass), FMC = 3%, wind = 15 mph, flat terrain. The expected head fire ROS is approximately 76 chains/hr (~25 m/min). If your output shows ROS of 2.5 m/min or 250 m/min, you have a unit conversion error.

### m10 and m100 from m1

Your GP estimates 1-hr dead FMC. ELMFIRE needs 1-hr, 10-hr, and 100-hr moisture separately. For the hackathon, approximate:

```python
m10 = m1 * 1.2    # 10-hr fuel is slightly wetter than 1-hr
m100 = m1 * 1.5   # 100-hr fuel is wetter still
```

These ratios are rough but physically reasonable. The Nelson model gives exact relationships but implementing it fully is optional. The 1-hr moisture dominates fire behavior in most fine-fuel scenarios.

### ELMFIRE's Unburned Cell Values

ELMFIRE may use -1, 0, or a very large number for unburned cells depending on version and configuration. Check the output of your first test run:

```python
toa = read_toa_raster()
print(f"Min: {toa.min()}, Max: {toa.max()}, Uniques near edges: {np.unique(toa[:5, :5])}")
```

Map whatever sentinel ELMFIRE uses to your MAX_ARRIVAL constant.

### File I/O Volume

200 members × 5 weather rasters × ~160 KB each (200×200 Float32) = 160 MB written per cycle. 200 members × 1 arrival time raster × ~160 KB = 32 MB read per cycle. Total: ~200 MB per cycle. On SSD this takes ~1 second. On spinning disk, ~5 seconds. On a RAM disk (`/dev/shm` on Linux), ~0.1 second.

**Recommendation:** Set `work_dir = "/dev/shm/ignis_elmfire"` if available. Falls back to `/tmp` otherwise.

### Parallelism

8 ELMFIRE processes running simultaneously, each on a 200×200 grid for a 6-hour simulation, each should complete in 1-5 seconds. Total wall time for 200 members on 8 cores: ~25-125 seconds. If this is too slow, try increasing `SIMULATION_DT` and `TARGET_CFL` (faster but less numerically accurate) or reducing `SIMULATION_DTMAX`.

---

## 5. Fallback Plan

If ELMFIRE won't compile on your hardware (requires gfortran, and sometimes Intel Fortran-specific features), fall back to the custom Rothermel CA in Python/C++. The wrapper interface (`FireEngine.run() → EnsembleResult`) is identical — the orchestrator doesn't know or care which fire engine is behind the interface.

**Day 1 morning checklist:**

```bash
# Clone ELMFIRE
git clone https://github.com/lautenberger/elmfire.git
cd elmfire

# Check for Fortran compiler
which gfortran || echo "NEED GFORTRAN"

# Try to build
cd build
make -f Makefile.gnu    # or Makefile.intel if using Intel compiler

# Test with Tutorial 01
cd ../tutorials/01-constant-wind
./01-run.sh

# If this works, commit to ELMFIRE.
# If not, pivot to custom CA by noon.
```

### Docker Alternative

ELMFIRE provides a Docker image. If compilation fails:

```bash
docker pull ghcr.io/lautenberger/elmfire:latest
# Run ELMFIRE inside container, mount work_dir as volume
docker run -v /tmp/ignis_elmfire:/data ghcr.io/lautenberger/elmfire \
    elmfire /data/cycle_001/member_0000/elmfire.data
```

Docker adds ~0.5-1 second overhead per subprocess call. For 200 members, this adds ~100-200 seconds. Acceptable but not ideal. Test native compilation first.

---

## 6. Testing Checklist

|Test|How|Expected|
|---|---|---|
|ELMFIRE compiles and runs Tutorial 01|`./01-run.sh` in tutorials dir|Produces time_of_arrival raster|
|Unit conversion: wind|Run with known wind, check ELMFIRE log for 20-ft wind used|Matches input after conversion|
|Unit conversion: FMC|Run with known FMC, compare ROS to BehavePlus|ROS within ±10%|
|Single member wrapper|`engine._run_single(member_dir)`|Produces arrival time GeoTIFF|
|Full ensemble|`engine.run(snapshot, config)` with N=5|Returns EnsembleResult with shape (5, rows, cols)|
|Parallel execution|Run N=20 with max_workers=8|All 20 complete without errors, wall time < 4× single run|
|Unburned handling|Check arrival_times for unburned cells|All equal MAX_ARRIVAL, no NaN, no negative values|
|Integration test|Pass EnsembleResult to information field computation|w_i heatmap has spatial structure, no NaN|

---

## 7. What You Don't Need to Worry About

- **GP perturbation generation** — someone else builds this, you receive the arrays
- **Information field computation** — someone else consumes your output
- **QUBO construction** — downstream of you
- **EnKF** — modifies state between cycles, gives you updated snapshot next cycle
- **Visualization** — someone else reads your EnsembleResult
- **Crown fire detection for bimodal layer** — if ELMFIRE outputs crown fire rasters (`DUMP_CROWN_FIRE = .TRUE.`), pass them through as an optional field in EnsembleResult. Someone else handles the bimodal detection.