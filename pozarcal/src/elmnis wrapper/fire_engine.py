"""
ignis/fire_engine.py

ELMFIRE wrapper for the IGNIS pipeline.

Satisfies the FireEngine protocol:
    engine.run(snapshot: CycleSnapshot, config: EnsembleConfig) -> EnsembleResult

All ELMFIRE I/O is file-based (GeoTIFF + Fortran namelist).
This module owns the Python/ELMFIRE boundary: unit conversions,
directory layout, subprocess management, and output parsing.

Dependencies:
    rasterio, numpy, concurrent.futures (stdlib)

Usage:
    engine = ElmfireEngine(
        elmfire_binary="/usr/local/bin/elmfire",
        work_dir="/dev/shm/ignis_elmfire",   # prefer RAM disk
        max_workers=8,
    )
    result = engine.run(snapshot, config)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from rasterio.transform import from_origin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data contracts (mirror whatever your pipeline defines; defined here so
# fire_engine.py is self-contained during development/testing)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TerrainData:
    """Static spatial inputs.  All arrays are float32[rows, cols] unless noted."""
    elevation:            np.ndarray   # metres
    slope:                np.ndarray   # degrees
    aspect:               np.ndarray   # degrees
    fuel_model:           np.ndarray   # Scott & Burgan 40 code, int16
    canopy_base_height:   np.ndarray   # metres
    canopy_bulk_density:  np.ndarray   # kg/m³
    canopy_cover:         np.ndarray   # fraction [0, 1]
    canopy_height:        np.ndarray   # metres
    # Spatial reference
    resolution_m: float                # cell size in metres (square cells)
    origin_x:     float                # UTM easting of top-left corner
    origin_y:     float                # UTM northing of top-left corner

    @property
    def shape(self) -> tuple[int, int]:
        return self.elevation.shape


@dataclass(frozen=True)
class CycleSnapshot:
    terrain:            TerrainData
    fire_state:         np.ndarray   # float32[rows, cols] — arrival times so far
    fuel_moisture_1hr:  np.ndarray   # float32[rows, cols] — GP posterior mean, fraction
    wind_speed:         np.ndarray   # float32[rows, cols] — GP posterior mean, m/s at 10m
    wind_direction:     np.ndarray   # float32[rows, cols] — degrees
    utm_epsg:           str          # e.g. "EPSG:32610"
    ignition_x:         float        # UTM easting
    ignition_y:         float        # UTM northing
    cycle_number:       int = 0


@dataclass(frozen=True)
class EnsembleConfig:
    n_members:     int    # typically 200-1000
    horizon_hours: float  # 6.0
    perturbations: dict   # keys: "fmc_1hr", "wind_speed", "wind_dir"
                          # values: float32[N, rows, cols] in physical units


@dataclass(frozen=True)
class EnsembleResult:
    member_arrival_times:  np.ndarray   # float32[N, rows, cols], seconds
    burn_probability:      np.ndarray   # float32[rows, cols]
    mean_arrival_time:     np.ndarray   # float32[rows, cols]
    arrival_time_variance: np.ndarray   # float32[rows, cols]
    member_fmc_fields:     np.ndarray   # float32[N, rows, cols], passed through
    member_wind_fields:    np.ndarray   # float32[N, rows, cols], passed through
    n_members:             int


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def _to_elmfire_wind_speed(ws_ms_10m: np.ndarray) -> np.ndarray:
    """
    10-m wind speed in m/s  →  20-ft wind speed in mph.

    ELMFIRE reads 20-ft winds in mph (WS_AT_10M = .FALSE.).
    Conversion: m/s → mph via ×2.23694; 10m → 20ft via ×1.15.
    The 1.15 factor is a neutral-stability log-law approximation
    (z0 = 0.1 m, 10 m → 6.1 m = 20 ft).
    """
    return ws_ms_10m * 2.23694 * 1.15   # → mph at 20 ft


def _to_elmfire_fmc(fmc_fraction: np.ndarray) -> np.ndarray:
    """Fuel moisture fraction [0, 1]  →  percent as expected by ELMFIRE."""
    return fmc_fraction * 100.0


# ---------------------------------------------------------------------------
# Config-file template
# ---------------------------------------------------------------------------

_CONFIG_TEMPLATE = """\
&INPUTS
FUELS_AND_TOPOGRAPHY_DIRECTORY = '{terrain_dir}'
ASP_FILENAME   = 'asp'
CBD_FILENAME   = 'cbd'
CBH_FILENAME   = 'cbh'
CC_FILENAME    = 'cc'
CH_FILENAME    = 'ch'
DEM_FILENAME   = 'dem'
FBFM_FILENAME  = 'fbfm40'
SLP_FILENAME   = 'slp'
ADJ_FILENAME   = 'adj'
PHI_FILENAME   = 'phi'
WEATHER_DIRECTORY       = '{weather_dir}'
WS_FILENAME             = 'ws'
WD_FILENAME             = 'wd'
M1_FILENAME             = 'm1'
M10_FILENAME            = 'm10'
M100_FILENAME           = 'm100'
LH_MOISTURE_CONTENT     = 30.0
LW_MOISTURE_CONTENT     = 60.0
FOLIAR_MOISTURE_CONTENT = 100.0
WS_AT_10M               = .FALSE.
/

&COMPUTATIONAL_DOMAIN
A_SRS                           = '{utm_epsg}'
COMPUTATIONAL_DOMAIN_CELLSIZE   = {cellsize}
COMPUTATIONAL_DOMAIN_XLLCORNER  = {xllcorner}
COMPUTATIONAL_DOMAIN_YLLCORNER  = {yllcorner}
/

&TIME_CONTROL
SIMULATION_TSTART  = 0.0
SIMULATION_TSTOP   = {horizon_s}
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
IGNITION_X    = {ign_x}
IGNITION_Y    = {ign_y}
/

&OUTPUTS
OUTPUTS_DIRECTORY    = '{output_dir}'
DUMP_TIME_OF_ARRIVAL = .TRUE.
DUMP_FLIN            = .TRUE.
DUMP_CROWN_FIRE      = .TRUE.
DUMP_SPREAD_RATE     = .FALSE.
DTDUMP               = {horizon_s}
/
"""


# ---------------------------------------------------------------------------
# Subprocess helper (must be module-level for ProcessPoolExecutor pickling)
# ---------------------------------------------------------------------------

def _run_member(binary: str, member_dir: str, timeout: int) -> None:
    """
    Execute one ELMFIRE instance.
    Raises RuntimeError on non-zero exit so the parent can log and continue.
    """
    result = subprocess.run(
        [binary, str(Path(member_dir) / "elmfire.data")],
        cwd=member_dir,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr_snippet = result.stderr.decode(errors="replace")[:600]
        raise RuntimeError(
            f"ELMFIRE exited {result.returncode} in {member_dir}:\n{stderr_snippet}"
        )


# ---------------------------------------------------------------------------
# Main engine class
# ---------------------------------------------------------------------------

class ElmfireEngine:
    """
    Python wrapper around the ELMFIRE Fortran binary.

    Implements the FireEngine protocol used by the IGNIS orchestrator.
    """

    # Unburned-cell sentinel value we write into EnsembleResult.
    # Downstream code checks: burned = arrival_times < MAX_ARRIVAL * 0.9
    _UNBURNED_FACTOR = 2.0   # MAX_ARRIVAL = _UNBURNED_FACTOR * horizon_s

    def __init__(
        self,
        elmfire_binary: str = "elmfire",
        work_dir: str = "/dev/shm/ignis_elmfire",
        max_workers: int = 8,
        member_timeout_s: int = 120,
    ) -> None:
        """
        Parameters
        ----------
        elmfire_binary
            Path to (or name of) the compiled ELMFIRE executable.
        work_dir
            Root scratch directory.  Prefer /dev/shm (RAM disk) on Linux.
            Falls back to /tmp if /dev/shm is unavailable.
        max_workers
            Number of parallel ELMFIRE processes.
        member_timeout_s
            Per-member wall-clock timeout in seconds before the subprocess
            is killed.  Prevents a hung member from blocking the whole cycle.
        """
        # Prefer RAM disk; fall back to /tmp
        preferred = Path(work_dir)
        fallback  = Path("/tmp/ignis_elmfire")
        if str(preferred).startswith("/dev/shm") and not Path("/dev/shm").exists():
            logger.warning("/dev/shm not available; using %s", fallback)
            self.work_dir = fallback
        else:
            self.work_dir = preferred

        self.binary           = elmfire_binary
        self.max_workers      = max_workers
        self.member_timeout_s = member_timeout_s
        self.terrain_dir      = self.work_dir / "terrain"

        self._terrain_written = False
        self._cycle_count     = 0
        self._geo_profile: Optional[dict] = None  # rasterio profile, set on first terrain write

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, snapshot: CycleSnapshot, config: EnsembleConfig) -> EnsembleResult:
        """
        Run N ensemble members through ELMFIRE.

        Parameters
        ----------
        snapshot
            Current cycle state: terrain, fire boundary, GP posterior means.
        config
            Ensemble size, simulation horizon, and per-member perturbation
            fields (float32[N, rows, cols]) in physical units.

        Returns
        -------
        EnsembleResult
            arrival_times[n, r, c] = seconds from sim start (float32).
            Unburned cells hold MAX_ARRIVAL = 2 × horizon_s.
        """
        # Write static terrain once; reused for every subsequent cycle
        if not self._terrain_written:
            self._write_terrain(snapshot)

        self._cycle_count += 1
        cycle_dir = self.work_dir / f"cycle_{self._cycle_count:03d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        N          = config.n_members
        rows, cols = snapshot.terrain.shape
        horizon_s  = config.horizon_hours * 3600.0
        MAX_ARRIVAL = self._UNBURNED_FACTOR * horizon_s

        # ------------------------------------------------------------------
        # Step 1 — Write per-member weather rasters + config files
        # ------------------------------------------------------------------
        member_dirs: list[Path] = []
        for n in range(N):
            member_dir  = cycle_dir / f"member_{n:04d}"
            weather_dir = member_dir / "weather"
            output_dir  = member_dir / "outputs"
            weather_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            self._write_weather(
                weather_dir=weather_dir,
                fmc_fraction=config.perturbations["fmc_1hr"][n],
                ws_ms=config.perturbations["wind_speed"][n],
                wd_deg=config.perturbations["wind_dir"][n],
            )
            self._write_config(
                member_dir=member_dir,
                weather_dir=weather_dir,
                output_dir=output_dir,
                snapshot=snapshot,
                horizon_s=horizon_s,
            )
            member_dirs.append(member_dir)

        # ------------------------------------------------------------------
        # Step 2 — Run all members in parallel
        # ------------------------------------------------------------------
        failed: list[int] = []
        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(
                    _run_member,
                    self.binary,
                    str(member_dirs[n]),
                    self.member_timeout_s,
                ): n
                for n in range(N)
            }
            for future in as_completed(futures):
                n = futures[future]
                exc = future.exception()
                if exc:
                    logger.error("Member %04d failed: %s", n, exc)
                    failed.append(n)

        if failed:
            logger.warning(
                "%d / %d members failed: %s", len(failed), N,
                failed[:10],   # log at most the first 10
            )

        # ------------------------------------------------------------------
        # Step 3 — Read arrival times; fill failures with MAX_ARRIVAL
        # ------------------------------------------------------------------
        arrival_times = np.full((N, rows, cols), MAX_ARRIVAL, dtype=np.float32)
        for n, member_dir in enumerate(member_dirs):
            if n in failed:
                continue   # already filled with MAX_ARRIVAL sentinel
            toa = self._read_arrival_time(member_dir / "outputs", horizon_s)
            if toa is None:
                logger.warning("Member %04d produced no time_of_arrival raster", n)
                continue

            # Normalise ELMFIRE's various unburned sentinels (-1, 0, very large)
            # to our MAX_ARRIVAL.  Positive arrival times outside the window are
            # also clipped — they indicate cells that ignite after the horizon.
            toa = np.where(toa < 0,           MAX_ARRIVAL, toa)   # ELMFIRE -1 sentinel
            toa = np.where(toa == 0,          MAX_ARRIVAL, toa)   # edge-case: 0 = unburned
            toa = np.where(toa > MAX_ARRIVAL, MAX_ARRIVAL, toa)   # beyond horizon
            arrival_times[n] = toa.astype(np.float32)

        # ------------------------------------------------------------------
        # Step 4 — Derive summary fields
        # ------------------------------------------------------------------
        burned_mask    = arrival_times < (MAX_ARRIVAL * 0.9)   # True where a member burned
        burn_prob      = burned_mask.mean(axis=0).astype(np.float32)

        # Mean arrival time over members that actually burned in each cell.
        # NaN-safe: cells where NO member burned get MAX_ARRIVAL.
        masked = np.where(burned_mask, arrival_times, np.nan)
        with np.errstate(invalid="ignore"):
            mean_arrival = np.nanmean(masked, axis=0).astype(np.float32)
        mean_arrival = np.nan_to_num(mean_arrival, nan=MAX_ARRIVAL).astype(np.float32)

        # Variance over ALL members (including unburned = MAX_ARRIVAL).
        # High variance ≈ uncertainty in whether/when a cell burns.
        variance = arrival_times.var(axis=0).astype(np.float32)

        return EnsembleResult(
            member_arrival_times  = arrival_times,
            burn_probability      = burn_prob,
            mean_arrival_time     = mean_arrival,
            arrival_time_variance = variance,
            member_fmc_fields     = config.perturbations["fmc_1hr"],
            member_wind_fields    = config.perturbations["wind_speed"],
            n_members             = N,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_terrain(self, snapshot: CycleSnapshot) -> None:
        """Write the 10 static terrain / fuel rasters.  Called once."""
        self.terrain_dir.mkdir(parents=True, exist_ok=True)
        t = snapshot.terrain

        # Base rasterio profile — shared by all rasters in this domain
        base_profile = {
            "driver":    "GTiff",
            "width":     t.shape[1],
            "height":    t.shape[0],
            "count":     1,
            "crs":       snapshot.utm_epsg,
            "transform": from_origin(
                t.origin_x, t.origin_y,
                t.resolution_m, t.resolution_m,
            ),
        }
        self._geo_profile = base_profile.copy()

        int16_profile  = {**base_profile, "dtype": "int16"}
        float32_profile = {**base_profile, "dtype": "float32"}

        # Int16 layers --------------------------------------------------------
        # LANDFIRE scaling conventions: CC/CH/CBH/CBD are stored scaled.
        # ELMFIRE decodes them internally using the same conventions.
        int16_layers: dict[str, np.ndarray] = {
            "asp":    t.aspect.astype(np.int16),
            "slp":    t.slope.astype(np.int16),
            "dem":    t.elevation.astype(np.int16),
            "fbfm40": t.fuel_model.astype(np.int16),
            "cc":     np.clip(t.canopy_cover * 100,  0, 32767).astype(np.int16),
            "ch":     np.clip(t.canopy_height * 10,  0, 32767).astype(np.int16),
            "cbh":    np.clip(t.canopy_base_height * 10, 0, 32767).astype(np.int16),
            "cbd":    np.clip(t.canopy_bulk_density * 100, 0, 32767).astype(np.int16),
        }
        for name, data in int16_layers.items():
            self._write_raster(self.terrain_dir / f"{name}.tif", data, int16_profile)

        # Float32 layers ------------------------------------------------------
        # adj: spread-rate adjustment factor (1.0 = no adjustment)
        self._write_raster(
            self.terrain_dir / "adj.tif",
            np.ones(t.shape, dtype=np.float32),
            float32_profile,
        )

        # phi: level-set fire front.
        # φ < 0 = burned, φ > 0 = unburned.
        # Initialise to +1 everywhere; the fire is started via the
        # IGNITION namelist block (IGNITION_TYPE = 'POINT').
        # On cycles > 1, a phi raster reconstructed from fire_state
        # would give ELMFIRE a head-start perimeter — left as a
        # TODO for post-hackathon work (see _build_phi).
        self._write_raster(
            self.terrain_dir / "phi.tif",
            np.ones(t.shape, dtype=np.float32),
            float32_profile,
        )

        self._terrain_written = True
        logger.info("Terrain rasters written to %s", self.terrain_dir)

    def _write_weather(
        self,
        weather_dir: Path,
        fmc_fraction: np.ndarray,  # float32[rows, cols], fraction
        ws_ms: np.ndarray,          # float32[rows, cols], m/s at 10m
        wd_deg: np.ndarray,         # float32[rows, cols], degrees
    ) -> None:
        """Write the 5 per-member weather GeoTIFFs."""
        assert self._geo_profile is not None, "Terrain must be written before weather"
        profile = {**self._geo_profile, "dtype": "float32"}

        fmc_pct     = _to_elmfire_fmc(fmc_fraction)
        ws_mph_20ft = _to_elmfire_wind_speed(ws_ms)

        # 10-hr and 100-hr moisture: rough ratios from dead-fuel equilibrium
        # physics.  The 1-hr moisture dominates ROS in fine-fuel scenarios.
        m10  = fmc_pct * 1.2
        m100 = fmc_pct * 1.5

        rasters = {
            "m1":  fmc_pct,
            "m10": m10,
            "m100": m100,
            "ws":  ws_mph_20ft,
            "wd":  wd_deg,
        }
        for name, data in rasters.items():
            self._write_raster(
                weather_dir / f"{name}.tif",
                data.astype(np.float32),
                profile,
            )

    def _write_config(
        self,
        member_dir: Path,
        weather_dir: Path,
        output_dir: Path,
        snapshot: CycleSnapshot,
        horizon_s: float,
    ) -> None:
        """Render and write elmfire.data for one ensemble member."""
        config_text = _CONFIG_TEMPLATE.format(
            terrain_dir = str(self.terrain_dir),
            weather_dir = str(weather_dir),
            output_dir  = str(output_dir),
            utm_epsg    = snapshot.utm_epsg,
            cellsize    = snapshot.terrain.resolution_m,
            xllcorner   = snapshot.terrain.origin_x,
            yllcorner   = snapshot.terrain.origin_y,
            horizon_s   = horizon_s,
            ign_x       = snapshot.ignition_x,
            ign_y       = snapshot.ignition_y,
        )
        (member_dir / "elmfire.data").write_text(config_text)

    def _read_arrival_time(
        self, output_dir: Path, horizon_s: float
    ) -> Optional[np.ndarray]:
        """
        Find and read the time_of_arrival raster from an ELMFIRE output directory.

        ELMFIRE names the file:
            time_of_arrival_XXXXXXX_YYYYYYY.tif
        where XXXXXXX is the ensemble member index (zero-padded 7 digits)
        and YYYYYYY is the output time in seconds (zero-padded 7 digits).

        We sort the matching files and take the last one (= final dump time).
        """
        matches = sorted(output_dir.glob("time_of_arrival_*.tif"))
        if not matches:
            return None

        toa_path = matches[-1]
        with rasterio.open(toa_path) as src:
            data = src.read(1)

        return data.astype(np.float32)

    @staticmethod
    def _write_raster(path: Path, data: np.ndarray, profile: dict) -> None:
        """Write a 2-D numpy array as a single-band GeoTIFF."""
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)

    # ------------------------------------------------------------------
    # Optional: reconstruct phi from EnKF-updated fire state
    # (cycle > 1, post-hackathon)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_phi(
        fire_state: np.ndarray,  # float32[rows, cols] arrival times, MAX_ARRIVAL = unburned
        max_arrival: float,
    ) -> np.ndarray:
        """
        Build a level-set phi raster from a post-EnKF fire state.

        Cells with arrival_time < max_arrival have burned: φ = -1.
        Unburned cells: φ = +1.

        This gives ELMFIRE a warm-start perimeter instead of re-growing
        the fire from the ignition point on every cycle.  Not used in the
        hackathon (ignition-point restart is simpler); wired in for the
        future.
        """
        phi = np.where(fire_state < max_arrival * 0.9, -1.0, 1.0)
        return phi.astype(np.float32)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def cleanup_cycle(self, cycle_number: Optional[int] = None) -> None:
        """
        Remove scratch files for a completed cycle.

        By default removes the most recently completed cycle.
        Pass cycle_number to target a specific one.
        """
        n = cycle_number if cycle_number is not None else self._cycle_count
        cycle_dir = self.work_dir / f"cycle_{n:03d}"
        if cycle_dir.exists():
            shutil.rmtree(cycle_dir)
            logger.debug("Removed scratch dir %s", cycle_dir)

    def cleanup_all(self) -> None:
        """Remove all scratch directories including terrain.  Call at pipeline shutdown."""
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
            logger.info("Removed all ELMFIRE scratch data at %s", self.work_dir)
        self._terrain_written = False
        self._cycle_count     = 0
        self._geo_profile     = None
