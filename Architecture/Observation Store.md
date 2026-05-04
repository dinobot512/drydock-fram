# Observation Store Design Specification

---

## Problem

Observations are currently scattered across multiple lists inside `IGNISGPPrior` — separate lists for FMC locs/vals/sigmas/times, wind speed locs/vals/sigmas/times, wind direction locs/vals/sigmas/times, and parallel RAWS versions of each. Adding a new observation type (satellite fire detection, thermal hotspot) requires touching 6+ internal lists and modifying every method that iterates them. The GP class is doing double duty as both a statistical model and an observation database.

## Solution

A centralized `ObservationStore` that owns all observations. Other components (GP, EnKF, information field, visualization) read from it but don't store observations themselves. The store handles ingestion, decay, pruning, locking, and query.

---

## Observation Base Class

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ObservationType(Enum):
    FMC = "fmc"
    WIND_SPEED = "wind_speed"
    WIND_DIRECTION = "wind_direction"
    FIRE_DETECTION = "fire_detection"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"

class ObservationSource(Enum):
    RAWS = "raws"
    DRONE_MULTISPECTRAL = "drone_multispectral"
    DRONE_ANEMOMETER = "drone_anemometer"
    DRONE_WEATHER = "drone_weather"
    DRONE_THERMAL = "drone_thermal"
    SATELLITE_VIIRS = "satellite_viirs"
    SATELLITE_GOES = "satellite_goes"
    SATELLITE_MODIS = "satellite_modis"

@dataclass(frozen=True)
class Observation:
    """Base observation. Immutable once created."""
    location: tuple[int, int]          # (row, col) in grid coordinates
    obs_type: ObservationType
    source: ObservationSource
    value: float                       # measured value in SI units
    sigma: float                       # measurement noise (original, never inflated)
    timestamp: float                   # simulation time in seconds
    source_id: str                     # e.g., "RAWS_CEDU", "drone_03", "VIIRS_pass_12"

    def effective_sigma(self, current_time: float, tau: float) -> float:
        """Sigma inflated by temporal decay."""
        age = max(0.0, current_time - self.timestamp)
        return self.sigma * np.exp(age / tau)

    def is_expired(self, current_time: float, tau: float, 
                   drop_factor: float = 10.0) -> bool:
        """Has this observation decayed beyond usefulness?"""
        return self.effective_sigma(current_time, tau) > drop_factor * self.sigma
```

### Specialized Observation Subclasses

These override decay behavior where the base class doesn't apply:

```python
@dataclass(frozen=True)
class RAWSObservation(Observation):
    """
    RAWS observations don't decay — they're replaced by fresh readings each cycle.
    """
    def effective_sigma(self, current_time: float, tau: float) -> float:
        return self.sigma  # no decay

    def is_expired(self, current_time: float, tau: float,
                   drop_factor: float = 10.0) -> bool:
        return False  # never expires — only replaced

@dataclass(frozen=True)
class FireDetectionObservation(Observation):
    """
    Fire/no-fire is permanent — a burned cell stays burned.
    Binary observation with confidence rather than continuous value.
    """
    is_fire: bool = True
    confidence: float = 0.95           # P(detection is correct)

    def effective_sigma(self, current_time: float, tau: float) -> float:
        return self.sigma  # no decay — fire state is permanent

    def is_expired(self, current_time: float, tau: float,
                   drop_factor: float = 10.0) -> bool:
        return False

@dataclass(frozen=True) 
class SatelliteObservation(Observation):
    """
    Satellite observations cover a footprint, not a point.
    The footprint_cells field lists all grid cells within the pixel.
    """
    footprint_cells: tuple[tuple[int, int], ...] = ()  # all cells in the pixel
    
    # Decay normally — satellite FMC estimates go stale like drone obs
```

---

## Observation Store

```python
import threading
from collections import defaultdict
from typing import Iterator

class ObservationStore:
    """
    Centralized observation management.
    
    Thread-safe. Supports concurrent observation ingestion (from drones)
    and batch reads (from GP/EnKF). Lock prevents reads of partially
    updated state during a cycle's prior computation.
    """

    def __init__(self, decay_config: dict[ObservationType, float]):
        """
        decay_config: maps ObservationType to tau (seconds).
        E.g., {ObservationType.FMC: 3600, ObservationType.WIND_SPEED: 7200, ...}
        """
        self._decay_config = decay_config
        self._current_time: float = 0.0

        # RAWS: keyed by source_id (station identifier).
        # New reading replaces old — dict semantics handle this.
        # Inner dict keyed by ObservationType so one station can provide
        # FMC + wind_speed + wind_direction simultaneously.
        self._raws: dict[str, dict[ObservationType, RAWSObservation]] = {}

        # Drone observations: append-only (until pruned by decay).
        # Stored per-type for efficient querying.
        self._drone: dict[ObservationType, list[Observation]] = defaultdict(list)

        # Satellite observations: append-only, separate because of footprint handling.
        self._satellite: dict[ObservationType, list[SatelliteObservation]] = defaultdict(list)

        # Fire detections: separate because binary, non-decaying, and
        # consumed differently (particle filter, not EnKF).
        self._fire_detections: list[FireDetectionObservation] = []

        # Lock: acquired during cycle prior computation.
        # Prevents new observations from arriving mid-computation.
        self._lock = threading.RLock()
        self._locked_for_cycle = False

        # Statistics
        self._total_ingested = 0
        self._total_pruned = 0

    # ------------------------------------------------------------------
    # Time management
    # ------------------------------------------------------------------

    def update_time(self, t: float) -> None:
        """Advance the store clock. Call once per cycle."""
        self._current_time = t

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_raws(self, station_id: str, observations: list[RAWSObservation]) -> None:
        """
        Add or replace RAWS station readings.
        All observations from this station_id are replaced atomically.
        """
        with self._lock:
            if self._locked_for_cycle:
                raise RuntimeError("Cannot add observations during cycle computation. "
                                   "Buffer externally and add after cycle completes.")
            self._raws[station_id] = {}
            for obs in observations:
                self._raws[station_id][obs.obs_type] = obs
            self._total_ingested += len(observations)

    def add_drone_observations(self, observations: list[Observation]) -> None:
        """
        Add drone observations. Appended to the store.
        Subject to temporal decay and eventual pruning.
        """
        with self._lock:
            if self._locked_for_cycle:
                raise RuntimeError("Cannot add observations during cycle computation.")
            for obs in observations:
                self._drone[obs.obs_type].append(obs)
            self._total_ingested += len(observations)

    def add_satellite_observations(self, observations: list[SatelliteObservation]) -> None:
        """Add satellite observations (FMC estimates or thermal)."""
        with self._lock:
            if self._locked_for_cycle:
                raise RuntimeError("Cannot add observations during cycle computation.")
            for obs in observations:
                self._satellite[obs.obs_type].append(obs)
            self._total_ingested += len(observations)

    def add_fire_detections(self, detections: list[FireDetectionObservation]) -> None:
        """Add binary fire/no-fire detections."""
        with self._lock:
            if self._locked_for_cycle:
                raise RuntimeError("Cannot add observations during cycle computation.")
            self._fire_detections.extend(detections)
            self._total_ingested += len(detections)

    # ------------------------------------------------------------------
    # Cycle lock
    # ------------------------------------------------------------------

    def lock_for_cycle(self) -> None:
        """
        Prevent observation ingestion during cycle computation.
        Call at the start of each IGNIS cycle. New observations arriving
        during the cycle should be buffered externally and added after
        unlock_cycle().
        """
        self._lock.acquire()
        self._locked_for_cycle = True

    def unlock_cycle(self) -> None:
        """
        Allow observation ingestion again.
        Call at the end of each IGNIS cycle.
        """
        self._locked_for_cycle = False
        self._lock.release()

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(self) -> int:
        """
        Remove expired observations based on temporal decay.
        Call once per cycle (typically after unlock, before next lock).
        Returns number of observations pruned.
        """
        pruned = 0
        for obs_type in list(self._drone.keys()):
            tau = self._decay_config.get(obs_type, float('inf'))
            before = len(self._drone[obs_type])
            self._drone[obs_type] = [
                obs for obs in self._drone[obs_type]
                if not obs.is_expired(self._current_time, tau)
            ]
            pruned += before - len(self._drone[obs_type])

        for obs_type in list(self._satellite.keys()):
            tau = self._decay_config.get(obs_type, float('inf'))
            before = len(self._satellite[obs_type])
            self._satellite[obs_type] = [
                obs for obs in self._satellite[obs_type]
                if not obs.is_expired(self._current_time, tau)
            ]
            pruned += before - len(self._satellite[obs_type])

        # RAWS: never pruned (replaced on add)
        # Fire detections: never pruned (permanent)

        self._total_pruned += pruned
        return pruned

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_all_for_type(self, obs_type: ObservationType,
                          include_raws: bool = True,
                          include_drone: bool = True,
                          include_satellite: bool = True
                          ) -> list[Observation]:
        """
        Return all observations of a given type across all sources.
        Observations are returned as-is (original sigma, not decayed).
        Use get_decayed_for_type() for GP fitting.
        """
        result = []
        if include_raws:
            for station in self._raws.values():
                if obs_type in station:
                    result.append(station[obs_type])
        if include_drone:
            result.extend(self._drone.get(obs_type, []))
        if include_satellite:
            result.extend(self._satellite.get(obs_type, []))
        return result

    def get_decayed_for_type(self, obs_type: ObservationType
                              ) -> tuple[list[Observation], list[float]]:
        """
        Return all observations of a type with their effective (decayed) sigmas.
        RAWS observations return original sigma (no decay).
        Drone/satellite observations return age-inflated sigma.
        
        Returns: (observations, effective_sigmas) — parallel lists.
        This is what the GP consumes for fitting.
        """
        tau = self._decay_config.get(obs_type, float('inf'))
        observations = []
        effective_sigmas = []

        # RAWS: no decay
        for station in self._raws.values():
            if obs_type in station:
                obs = station[obs_type]
                observations.append(obs)
                effective_sigmas.append(obs.sigma)  # original, not decayed

        # Drone: decayed
        for obs in self._drone.get(obs_type, []):
            eff = obs.effective_sigma(self._current_time, tau)
            observations.append(obs)
            effective_sigmas.append(eff)

        # Satellite: decayed
        for obs in self._satellite.get(obs_type, []):
            eff = obs.effective_sigma(self._current_time, tau)
            observations.append(obs)
            effective_sigmas.append(eff)

        return observations, effective_sigmas

    def get_fire_detections(self, since: Optional[float] = None
                            ) -> list[FireDetectionObservation]:
        """
        Return fire detections, optionally filtered to those after a timestamp.
        Used by the particle filter branch of the EnKF.
        """
        if since is None:
            return list(self._fire_detections)
        return [d for d in self._fire_detections if d.timestamp >= since]

    def get_observations_near(self, location: tuple[int, int], 
                               radius_cells: int,
                               obs_type: Optional[ObservationType] = None
                               ) -> list[Observation]:
        """
        Spatial query: all observations within radius of a location.
        Used by the EnKF for localization and by visualization.
        """
        result = []
        for obs in self._iter_all(obs_type):
            dr = abs(obs.location[0] - location[0])
            dc = abs(obs.location[1] - location[1])
            if dr <= radius_cells and dc <= radius_cells:
                if dr * dr + dc * dc <= radius_cells * radius_cells:
                    result.append(obs)
        return result

    def get_observation_locations(self, obs_type: Optional[ObservationType] = None
                                  ) -> list[tuple[int, int]]:
        """All unique observation locations. For visualization overlays."""
        locs = set()
        for obs in self._iter_all(obs_type):
            locs.add(obs.location)
        return list(locs)

    def _iter_all(self, obs_type: Optional[ObservationType] = None
                  ) -> Iterator[Observation]:
        """Iterate over all observations, optionally filtered by type."""
        for station in self._raws.values():
            for ot, obs in station.items():
                if obs_type is None or ot == obs_type:
                    yield obs
        for ot, obs_list in self._drone.items():
            if obs_type is None or ot == obs_type:
                yield from obs_list
        for ot, obs_list in self._satellite.items():
            if obs_type is None or ot == obs_type:
                yield from obs_list
        if obs_type is None or obs_type == ObservationType.FIRE_DETECTION:
            yield from self._fire_detections

    # ------------------------------------------------------------------
    # Statistics and diagnostics
    # ------------------------------------------------------------------

    def count(self, obs_type: Optional[ObservationType] = None) -> dict:
        """Count observations by source and type."""
        counts = {
            "raws": 0,
            "drone": 0,
            "satellite": 0,
            "fire_detection": len(self._fire_detections),
            "total": 0,
        }
        for station in self._raws.values():
            for ot in station:
                if obs_type is None or ot == obs_type:
                    counts["raws"] += 1
        for ot, obs_list in self._drone.items():
            if obs_type is None or ot == obs_type:
                counts["drone"] += len(obs_list)
        for ot, obs_list in self._satellite.items():
            if obs_type is None or ot == obs_type:
                counts["satellite"] += len(obs_list)
        counts["total"] = sum(counts.values())
        return counts

    def age_summary(self) -> dict[ObservationType, dict]:
        """
        For each observation type, return min/max/mean age of drone observations.
        Diagnostic for monitoring temporal decay behavior.
        """
        summary = {}
        for obs_type, obs_list in self._drone.items():
            if not obs_list:
                continue
            ages = [self._current_time - obs.timestamp for obs in obs_list]
            summary[obs_type] = {
                "count": len(ages),
                "min_age_s": min(ages),
                "max_age_s": max(ages),
                "mean_age_s": sum(ages) / len(ages),
            }
        return summary

    def snapshot(self) -> 'ObservationSnapshot':
        """
        Create an immutable snapshot of the current observation state.
        Used for the counterfactual evaluator — it needs to fork the
        observation state without affecting the live store.
        """
        return ObservationSnapshot(
            raws={sid: dict(obs) for sid, obs in self._raws.items()},
            drone={ot: list(obs) for ot, obs in self._drone.items()},
            satellite={ot: list(obs) for ot, obs in self._satellite.items()},
            fire_detections=list(self._fire_detections),
            current_time=self._current_time,
            decay_config=dict(self._decay_config),
        )


@dataclass(frozen=True)
class ObservationSnapshot:
    """Immutable snapshot for counterfactual evaluation."""
    raws: dict
    drone: dict
    satellite: dict
    fire_detections: list
    current_time: float
    decay_config: dict
```

---

## How Each Consumer Uses the Store

### GP Prior

```python
class IGNISGPPrior:
    def __init__(self, obs_store: ObservationStore, ...):
        self._store = obs_store
    
    def fit(self):
        # FMC observations with decay
        fmc_obs, fmc_sigmas = self._store.get_decayed_for_type(ObservationType.FMC)
        locs = [o.location for o in fmc_obs]
        vals = [o.value for o in fmc_obs]
        # Subtract Nelson, fit GP on residuals with effective sigmas
        self._gp_fmc = self._fit_variable(locs, vals, fmc_sigmas, ...)
        
        # Wind speed
        ws_obs, ws_sigmas = self._store.get_decayed_for_type(ObservationType.WIND_SPEED)
        # ... same pattern
        
        # Wind direction
        wd_obs, wd_sigmas = self._store.get_decayed_for_type(ObservationType.WIND_DIRECTION)
        # ... same pattern
```

The GP no longer stores observations internally. It reads from the store each cycle.

### EnKF

```python
class DataAssimilator:
    def assimilate(self, ensemble, obs_store: ObservationStore):
        # Continuous observations: standard EnKF
        for obs_type in [ObservationType.FMC, ObservationType.WIND_SPEED, 
                         ObservationType.WIND_DIRECTION]:
            obs_list = obs_store.get_all_for_type(obs_type, include_raws=False)
            # Only assimilate drone/satellite obs collected THIS cycle
            recent = [o for o in obs_list if o.timestamp >= self._last_cycle_time]
            if recent:
                ensemble = self._enkf_update(ensemble, recent)
        
        # Binary fire detections: particle filter reweighting
        detections = obs_store.get_fire_detections(since=self._last_cycle_time)
        if detections:
            ensemble = self._particle_filter_update(ensemble, detections)
        
        return ensemble
```

### Visualization

```python
class Renderer:
    def render_observation_layer(self, ax, obs_store: ObservationStore):
        # Plot all observation locations with markers by source
        for obs in obs_store._iter_all():
            marker = {"raws": "o", "drone": "^", "satellite": "s"}
            color = {"fmc": "green", "wind_speed": "blue", "wind_direction": "cyan"}
            # ...
```

### Orchestrator

```python
class Orchestrator:
    def run_cycle(self):
        # Lock store during computation
        self._obs_store.lock_for_cycle()
        try:
            self._obs_store.update_time(self._current_time)
            
            # GP reads from store
            gp_prior = self._gp.predict(self._shape)
            
            # Ensemble, info field, selection...
            ...
            
            # EnKF reads from store
            self._assimilator.assimilate(ensemble, self._obs_store)
            
        finally:
            self._obs_store.unlock_cycle()
        
        # Prune after unlock — old observations removed
        pruned = self._obs_store.prune()
        
        # Now external sources can add new observations
        # (drone telemetry, satellite passes, RAWS updates)
```

---

## Observation Thinning

Thinning is a query-time operation, not a storage operation. The store keeps all observations. Consumers thin when they need to:

```python
def get_thinned_for_type(self, obs_type: ObservationType,
                          min_spacing_cells: int) -> tuple[list[Observation], list[float]]:
    """
    Return observations thinned to one per min_spacing_cells.
    Keeps lowest-sigma observation in each spatial bin.
    Used by the GP to avoid singularity from dense swath observations.
    """
    obs_list, sigmas = self.get_decayed_for_type(obs_type)
    
    # Sort by effective sigma (lowest first = most precise)
    paired = sorted(zip(obs_list, sigmas), key=lambda x: x[1])
    
    thinned_obs = []
    thinned_sigmas = []
    for obs, sigma in paired:
        if all(
            abs(obs.location[0] - t.location[0]) > min_spacing_cells or
            abs(obs.location[1] - t.location[1]) > min_spacing_cells
            for t in thinned_obs
        ):
            thinned_obs.append(obs)
            thinned_sigmas.append(sigma)
    
    return thinned_obs, thinned_sigmas
```

---

## Spatial Index (optional optimization)

If `get_observations_near()` becomes a bottleneck (many observations, frequent queries), add a grid-based spatial index:

```python
class SpatialIndex:
    """Simple grid-based spatial index for fast proximity queries."""
    
    def __init__(self, grid_shape: tuple[int, int], bin_size: int = 10):
        self.bin_size = bin_size
        n_bins_r = grid_shape[0] // bin_size + 1
        n_bins_c = grid_shape[1] // bin_size + 1
        self._bins: dict[tuple[int,int], list[Observation]] = defaultdict(list)
    
    def insert(self, obs: Observation):
        br = obs.location[0] // self.bin_size
        bc = obs.location[1] // self.bin_size
        self._bins[(br, bc)].append(obs)
    
    def query_radius(self, location, radius_cells):
        br = location[0] // self.bin_size
        bc = location[1] // self.bin_size
        bin_radius = radius_cells // self.bin_size + 1
        
        result = []
        for dbr in range(-bin_radius, bin_radius + 1):
            for dbc in range(-bin_radius, bin_radius + 1):
                for obs in self._bins.get((br + dbr, bc + dbc), []):
                    dr = obs.location[0] - location[0]
                    dc = obs.location[1] - location[1]
                    if dr*dr + dc*dc <= radius_cells * radius_cells:
                        result.append(obs)
        return result
```

Not needed at hackathon scale (<500 observations). Add when observation counts reach thousands.

---

## Migration from Current GP

The current GP stores observations in 18 parallel lists (`_fmc_locs`, `_fmc_vals`, `_fmc_sigmas`, `_fmc_times`, `_raws_fmc_locs`, ...). To migrate:

1. Create `ObservationStore` in the orchestrator.
2. Remove all `_fmc_locs`, `_fmc_vals`, etc. from `IGNISGPPrior`.
3. Remove `add_raws()` and `add_observations()` from `IGNISGPPrior`.
4. GP's `fit()` reads from `obs_store.get_decayed_for_type()` instead of internal lists.
5. `_prune_and_decay()` in GP is deleted — the store handles this.
6. `update_time()` moves from GP to the store.

The GP becomes a pure statistical model: it receives observations and produces posteriors. It doesn't manage observation lifecycle.

---

## External Ingestion Buffer

When the store is locked during a cycle, external sources (drone telemetry, satellite) can't add directly. Use a buffer:

```python
class IngestionBuffer:
    """Buffers observations while the store is locked."""
    
    def __init__(self, store: ObservationStore):
        self._store = store
        self._pending: list[Observation] = []
    
    def add(self, obs: Observation):
        """Always succeeds — buffers if store is locked."""
        try:
            if isinstance(obs, RAWSObservation):
                self._store.add_raws(obs.source_id, [obs])
            elif isinstance(obs, FireDetectionObservation):
                self._store.add_fire_detections([obs])
            else:
                self._store.add_drone_observations([obs])
        except RuntimeError:
            # Store is locked — buffer for later
            self._pending.append(obs)
    
    def flush(self):
        """Push buffered observations to store. Call after cycle unlocks."""
        for obs in self._pending:
            self.add(obs)  # will succeed now that store is unlocked
        self._pending.clear()
```

The simulation harness or real drone telemetry pushes to the buffer. The orchestrator calls `buffer.flush()` after each cycle's `unlock_cycle()`.