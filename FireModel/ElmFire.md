ELMFIRE is significantly more capable than any of the other options we discussed. It may change your build plan.

**What IGNIS needs from the fire engine:**

```
INPUT:
  - Terrain rasters (DEM, slope, aspect, fuel model, CBH, CBD, canopy cover)
  - FMC field (spatially varying, per-member)
  - Wind field (spatially varying, per-member)
  - Fire ignition (point or perimeter)

OUTPUT:
  - Arrival time at every cell (continuous float, not discrete state)
  - Fire type per cell (surface vs crown)
  - Fireline intensity per cell (for crown fire check and spotting risk)

REQUIREMENT:
  - Run N times with different FMC/wind fields (structured perturbations from GP)
  - Return numpy-compatible arrays to the Python pipeline
```

**What ELMFIRE already provides:**

Almost everything. It implements Rothermel surface spread, Van Wagner crown fire initiation, Rothermel 1991 crown fire spread, Nelson fuel moisture conditioning, spotting (Albini-based), AND has built-in Monte Carlo with per-pixel perturbation of FMC, wind speed, wind direction, canopy properties — exactly the structured ensemble your system needs. It reads LANDFIRE GeoTIFFs natively. It's written in Fortran (not C++ — correction to our earlier assumption), compiled, and designed for operational-speed simulations.

The Monte Carlo configuration is almost exactly what your architecture requires:

```fortran
! ELMFIRE already supports this:
NUM_ENSEMBLE_MEMBERS    = 200
NUM_RASTERS_TO_PERTURB  = 3
RASTER_TO_PERTURB(1)    = 'M1'     ! 1-hour dead fuel moisture
RASTER_TO_PERTURB(2)    = 'WS'     ! wind speed
RASTER_TO_PERTURB(3)    = 'WD'     ! wind direction
SPATIAL_PERTURBATION(1) = 'PIXEL'  ! different perturbation at each pixel
PDF_TYPE(1)             = 'UNIFORM'
PDF_LOWER_LIMIT(1)      = -0.10
PDF_UPPER_LIMIT(1)      = 0.10
```

The critical limitation: ELMFIRE's built-in perturbation uses uniform PDFs, not GP-scaled spatially correlated fields. It perturbs each pixel independently with a uniform random value — no spatial correlation structure, and the same perturbation range everywhere regardless of data density.

**How to adapt ELMFIRE for IGNIS:**

There are two approaches, ordered by effort:

**Approach 1: Generate perturbed rasters externally (no ELMFIRE modification).**

Write Python code that generates N sets of perturbed FMC and wind GeoTIFF rasters, with GP-scaled spatially correlated perturbations. Feed each set to a separate ELMFIRE run. ELMFIRE treats them as fixed weather inputs (not Monte Carlo) and produces outputs for each.

```python
def run_elmfire_ensemble(gp_prior, terrain_dir, n_members, horizon_hours):
    results = []
    
    for n in range(n_members):
        # Generate GP-scaled perturbed rasters in Python
        fmc_field = gp_prior.fmc_mean + draw_correlated_field() * np.sqrt(gp_prior.fmc_variance)
        ws_field = gp_prior.ws_mean + draw_correlated_field() * np.sqrt(gp_prior.ws_variance)
        wd_field = gp_prior.wd_mean + draw_correlated_field() * np.sqrt(gp_prior.wd_variance)
        
        # Write to GeoTIFF
        member_dir = f"./ensemble/member_{n:04d}"
        write_geotiff(f"{member_dir}/m1.tif", fmc_field * 100, terrain_meta)  # ELMFIRE expects %
        write_geotiff(f"{member_dir}/ws.tif", ws_field * 2.237, terrain_meta)  # ELMFIRE expects mph
        write_geotiff(f"{member_dir}/wd.tif", wd_field, terrain_meta)
        
        # Write ELMFIRE config
        write_elmfire_config(member_dir, terrain_dir, horizon_hours)
        
        # Run ELMFIRE
        subprocess.run(["elmfire", f"{member_dir}/elmfire.data"], check=True)
        
        # Read arrival time output
        arrival_time = read_geotiff(f"{member_dir}/time_of_arrival.tif")
        results.append(arrival_time)
    
    return np.stack(results)  # (N, rows, cols)
```

**Pros:** Zero modification to ELMFIRE source. Uses ELMFIRE exactly as designed — just providing it pre-computed weather inputs. You get full Rothermel + crown fire + spotting for free.

**Cons:** File I/O overhead. Writing and reading N × 5 GeoTIFFs per cycle (N members × FMC, WS, WD input + arrival time output). For N=200 on a 200×200 grid, that's ~200 files written + 200 files read per cycle. At ~50 KB per file, total I/O is ~20 MB — fast on SSD (~100 ms) but clunky. Also, subprocess launch overhead: 200 ELMFIRE processes, each with startup cost.

**Mitigation:** Use ELMFIRE's own `NUM_ENSEMBLE_MEMBERS` to batch runs. Instead of 200 subprocess calls, write all 200 weather variants as multi-band rasters (200 bands each) and let ELMFIRE run them as a single Monte Carlo job internally. ELMFIRE is designed for exactly this — it reads stacked rasters and distributes ensemble members across them. The output is a set of rasters including `times_burned` and per-member arrival times.

**Approach 2: Use ELMFIRE's Monte Carlo but replace the perturbation source.**

Modify the perturbation step by providing ELMFIRE with pre-perturbed multi-band weather rasters where each band is one ensemble member's weather state. Set `SPATIAL_PERTURBATION = 'PIXEL'` and `TEMPORAL_PERTURBATION = 'STATIC'` but instead of letting ELMFIRE draw from a uniform PDF, provide the GP-generated fields directly as the input rasters.

The trick: ELMFIRE's multi-band weather rasters are normally used for _temporal_ variation (band 1 = hour 1, band 2 = hour 2). But for your constant-weather ensemble, you can repurpose bands as _ensemble members_. Set `DT_METEOROLOGY` to something large (so ELMFIRE treats all bands as the same time), and use `METEOROLOGY_BAND_START`, `METEOROLOGY_BAND_STOP`, `METEOROLOGY_BAND_SKIP_INTERVAL` to map each ensemble member to a band.

Actually — this won't work cleanly because ELMFIRE interprets bands as temporal, not ensemble-member-indexed. Approach 1 is cleaner.

**Recommended approach: Approach 1 with batching.**

```
Python (GP + perturbation generation)
    │
    ▼
Write N perturbed GeoTIFF sets
    │
    ▼
Run ELMFIRE N times (parallel via GNU parallel or ELMFIRE's built-in batching)
    │
    ▼
Read N arrival time GeoTIFFs
    │
    ▼
Stack into numpy array (N, rows, cols)
    │
    ▼
Continue with IGNIS pipeline (information field, QUBO, etc.)
```

Parallelize the N ELMFIRE runs with GNU parallel or xargs:

```bash
seq 0 199 | parallel -j 8 "cd ensemble/member_{} && elmfire elmfire.data"
```

Eight ELMFIRE instances running simultaneously on 8 cores. Each ELMFIRE run on a 200×200 grid at 50m for 6 hours takes roughly 1-5 seconds (based on published benchmarks for CA-class simulators at this scale, and ELMFIRE is faster than FARSITE). Total wall time for 200 members on 8 cores: ~25-125 seconds. Within your cycle budget.

**What this gives you over a custom Rothermel CA:**

- Full crown fire (Van Wagner + Rothermel 91) — validated, not your implementation
- Spotting (Albini) — your custom CA can't do this
- Nelson fuel moisture conditioning — operates alongside your GP
- CFL-adaptive timestepping — more numerically stable than fixed-dt CA
- Level-set fire propagation — continuous arrival times natively, no sentinel-value issues
- Validated against real fires — published V&V cases
- Operational credibility — "we use ELMFIRE, the same simulator used for California's state-wide burn probability assessment" is a stronger statement than "we wrote our own CA"

**What you lose:**

- Direct programmatic control of the fire engine (it's a subprocess, not a library call)
- GPU acceleration (ELMFIRE is CPU/Fortran)
- The ability to modify fire physics easily (requires Fortran source modification and recompilation)
- pybind11 zero-copy interface (replaced by file I/O)

**Unit conversions to watch:**

ELMFIRE expects specific units that differ from SI:

- Wind speed: 20-ft wind in mph (not m/s at 10m)
- Fuel moisture: percentage (not fraction)
- CBH: units of 10 meters in LANDFIRE format (ELMFIRE handles internally)
- Slope: degrees
- Aspect: degrees

Your Python wrapper must handle these conversions at the GeoTIFF write boundary. Get one wrong and ROS is off by orders of magnitude.

**My revised recommendation:**

If ELMFIRE compiles and runs on your hackathon hardware (it requires a Fortran compiler — gfortran works), use it. The physics fidelity gain (crown fire + spotting + validated Rothermel + level set) far outweighs the file I/O overhead. You skip writing 130 lines of fire physics, gain validated crown fire and spotting for free, and can honestly claim you're using an operational-grade simulator.

If Fortran compilation is a problem (some hackathon environments don't have gfortran), fall back to the custom Rothermel CA in Python/C++.

Test ELMFIRE compilation on day 1 morning. If it works, commit to it. If not, pivot immediately.