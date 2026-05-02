# IGNIS: System Architecture v2

---

## Boundary Definition

IGNIS is the **intelligence layer**. It answers: "Where should sensing drones go next?" It consumes environmental state and constraints, produces prioritized mission requests. It does NOT manage airspace, fly drones, or make operational decisions.

The **UTM layer** (built separately) manages airspace, deconflicts aircraft, enforces TFRs, translates mission requests into executable flight plans. It consumes IGNIS outputs and external constraints, produces flight commands.

The interface between them is a **Mission Request Queue** — a ranked list of sensing tasks with locations, priorities, and information-value estimates. The UTM can accept, modify, defer, or reject any request. IGNIS never assumes its requests will be fulfilled as-is.

```
 EXTERNAL INPUTS                    IGNIS                         UTM LAYER
┌──────────────┐                                              ┌──────────────┐
│ Weather data │──┐          ┌──────────────────┐             │ Airspace     │
│ Fuel maps    │  │          │                  │  Mission    │ management   │
│ DEM/terrain  │  ├────────▶│   INTELLIGENCE   │──Request───▶│ Deconflict   │
│ Fire perim.  │  │          │      LAYER       │  Queue      │ Flight plans │
│ RAWS data    │──┘          │                  │◀─Status────│ Execution    │
│              │             └──────┬───▲───────┘  Updates    └──────┬───────┘
│ Manual       │                    │   │                            │
│ overrides  ──┼───────────────────▶│   │                            │
│ (priority    │                    │   │         ┌──────────┐       │
│  regions,    │             ┌──────▼───┴───────┐ │          │       │
│  forced      │             │  OBSERVATION     │◀┤  DRONES  │◀──────┘
│  targets)    │             │  INGESTION       │ │  (real or │
└──────────────┘             └──────────────────┘ │   sim)   │
                                                  └──────────┘
```

---

## IGNIS External API

The UTM developer and operator interact with IGNIS through these interfaces only. Everything else is internal.

### Orchestrator API (primary interface)

```python
class IGNISOrchestrator:

    def run_cycle(self) -> MissionQueue:
        """Run a full prediction-decomposition-solve cycle.
        Called by timer (every ~20 min) or manually.
        Returns new MissionQueue."""

    def ingest_observation(self, obs: DroneObservation) -> Optional[MissionQueue]:
        """Process a single incoming observation.
        Triggers EnKF update. Returns updated MissionQueue
        only if replan threshold is met, else None."""

    def add_priority_region(self, region: PriorityRegion) -> None:
        """Boost priority weight in a geographic region.
        Takes effect on next cycle or replan."""

    def remove_priority_region(self, region_id: str) -> None:
        """Remove a previously added priority region."""

    def add_exclusion_zone(self, zone: ExclusionZone) -> None:
        """Exclude a region from drone targeting.
        Takes effect immediately on pending queue."""

    def remove_exclusion_zone(self, zone_id: str) -> None:
        """Remove a previously added exclusion zone."""

    def add_forced_target(self, target: ForcedTarget) -> None:
        """Inject a target directly into queue at specified priority.
        Bypasses QUBO — used for operator overrides and external alerts."""

    def update_request_status(self, update: StatusUpdate) -> None:
        """UTM reports what happened to a mission request.
        Used for tracking and informing future cycles."""

    def get_status(self) -> SystemStatus:
        """Returns cycle count, last solve time, solver used,
        ensemble size, current replan threshold state."""
```

---

## Data Types

### Input Types

```python
@dataclass(frozen=True)
class TerrainData:
    elevation: np.ndarray          # float[rows, cols], meters
    slope: np.ndarray              # float[rows, cols], degrees
    aspect: np.ndarray             # float[rows, cols], degrees
    fuel_model: np.ndarray         # int[rows, cols]
    resolution_m: float
    origin: tuple[float, float]    # (lat, lon) of NW corner

@dataclass(frozen=True)
class WeatherState:
    wind_speed: np.ndarray | float       # m/s
    wind_direction: np.ndarray | float   # degrees
    temperature: float                    # °C
    relative_humidity: float              # fraction 0-1
    timestamp: datetime

@dataclass(frozen=True)
class FireState:
    arrival_time: np.ndarray       # float[rows, cols], NaN = unburned
    timestamp: datetime

@dataclass(frozen=True)
class DroneObservation:
    location: tuple[int, int]      # (row, col)
    fuel_moisture: float
    fuel_moisture_sigma: float
    wind_speed: float
    wind_speed_sigma: float
    wind_direction: float
    wind_direction_sigma: float
    timestamp: datetime
    drone_id: str

@dataclass(frozen=True)
class PriorityRegion:
    region_id: str
    polygon: list[tuple[float, float]]   # lat/lon vertices
    weight: float                         # multiplier on info value (>1 = boost)
    reason: str

@dataclass(frozen=True)
class ExclusionZone:
    zone_id: str
    polygon: list[tuple[float, float]]
    reason: str

@dataclass(frozen=True)
class ForcedTarget:
    location: tuple[float, float]        # (lat, lon)
    priority: float
    reason: str

@dataclass(frozen=True)
class StatusUpdate:
    request_id: str
    status: str    # "accepted" | "in_progress" | "completed" | "rejected" | "redirected"
    actual_location: tuple[float, float] | None
    drone_id: str
    timestamp: datetime
```

### Output Types

```python
@dataclass(frozen=True)
class MissionRequest:
    request_id: str
    target_location: tuple[float, float]   # (lat, lon)
    grid_cell: tuple[int, int]             # (row, col)
    information_value: float               # marginal info gain
    cumulative_value: float                # total if top-N fulfilled
    dominant_variable: str                 # "fmc" | "wind_speed" | "wind_direction"
    measurement_types: list[str]           # what to measure
    loiter_time_s: int
    priority_source: str                   # "qubo" | "greedy" | "forced_target"
    expiry: datetime
    substitutes: list[tuple[float, float]] # fallback locations (lat/lon)

@dataclass(frozen=True)
class MissionQueue:
    timestamp: datetime
    cycle_id: int
    solver_used: str                       # "dwave" | "simulated_annealing" | "greedy"
    requests: list[MissionRequest]         # sorted by information_value descending

@dataclass(frozen=True)
class SituationPackage:
    burn_probability: np.ndarray           # float[rows, cols]
    uncertainty_map: np.ndarray            # float[rows, cols]
    attribution: dict[str, np.ndarray]     # variance fraction by source
    drone_value_curve: list[tuple[int, float]]  # (K, cumulative_gain)
    placement_stability: float             # Jaccard with previous cycle

@dataclass(frozen=True)
class SystemStatus:
    cycle_count: int
    last_cycle_time_s: float
    solver_used: str
    ensemble_size: int
    observations_ingested: int
    pending_requests: int
    replan_triggered: bool
```

---

## Internal Components

### Component 1: State Snapshot Factory

**Purpose:** Produces immutable snapshots of all state for each cycle. No component mutates shared state directly. The orchestrator assembles outputs into the next snapshot.

```python
@dataclass(frozen=True)
class CycleSnapshot:
    terrain: TerrainData                    # static, same every cycle
    weather: WeatherState
    fire: FireState
    fuel_moisture: np.ndarray               # current best estimate
    wind_field: np.ndarray                  # current best estimate (speed)
    wind_dir_field: np.ndarray              # current best estimate (direction)
    priority_weights: np.ndarray            # float[rows, cols], default 1.0
    exclusion_mask: np.ndarray              # bool[rows, cols], True = excluded
    forced_targets: list[ForcedTarget]
    previous_queue: MissionQueue | None     # for placement stability calc

class StateFactory:
    def __init__(self, terrain: TerrainData):
        self._terrain = terrain
        self._weather = None
        self._fire = None
        self._fuel_moisture = None         # initialized from weather via Nelson model
        self._wind_field = None
        self._priority_regions = {}        # id -> PriorityRegion
        self._exclusion_zones = {}         # id -> ExclusionZone
        self._forced_targets = []
        self._previous_queue = None

    def update_weather(self, weather: WeatherState) -> None: ...
    def update_fire(self, fire: FireState) -> None: ...
    def apply_assimilation(self, result: AssimilationResult) -> None: ...
    def add_priority_region(self, region: PriorityRegion) -> None: ...
    def remove_priority_region(self, region_id: str) -> None: ...
    def add_exclusion_zone(self, zone: ExclusionZone) -> None: ...
    def remove_exclusion_zone(self, zone_id: str) -> None: ...
    def set_previous_queue(self, queue: MissionQueue) -> None: ...

    def snapshot(self) -> CycleSnapshot:
        """Build and return frozen snapshot of current state.
        Computes priority_weights and exclusion_mask from stored regions/zones."""
        ...
```

**Key invariant:** Once a `CycleSnapshot` is created, it never changes. Components receive it as a read-only input. The `StateFactory` is the only mutable object, and only the orchestrator writes to it.

---

### Component 2: Fire Engine

**Purpose:** Run N-member ensemble of fire spread simulations.

```python
@dataclass(frozen=True)
class EnsembleConfig:
    n_members: int                # 100-200
    horizon_hours: float          # how far forward to predict
    perturbation_ranges: dict[str, tuple[float, float]]
        # e.g., {"fmc": (-0.20, 0.20), "wind_speed": (-0.30, 0.30)}

@dataclass(frozen=True)
class EnsembleResult:
    member_arrival_times: np.ndarray     # float[N, rows, cols]
    member_parameters: list[dict]        # perturbation values per member
    burn_probability: np.ndarray         # float[rows, cols]
    mean_arrival_time: np.ndarray        # float[rows, cols]
    arrival_time_variance: np.ndarray    # float[rows, cols]

class FireEngine:
    def run(self, snapshot: CycleSnapshot, config: EnsembleConfig) -> EnsembleResult:
        """Run ensemble. Pure function — no side effects."""
        ...

    # Degradation: if ensemble produces zero variance everywhere
    # (all members agree), return result with a flag.
    # Orchestrator handles by emitting empty MissionQueue.
```

**Implementation:** Cellular automata. Each cell has states {unburned, burning, burned}. Transition probability from Rothermel ROS formula using cell's fuel model, slope, wind, FMC. Each ensemble member draws different (FMC, wind_speed, wind_direction) from perturbation ranges.

---

### Component 3: Uncertainty Decomposition

**Purpose:** Attribute prediction variance to input variables. Produce typed uncertainty structures for QUBO construction.

```python
@dataclass(frozen=True)
class CandidateLocations:
    indices: list[tuple[int, int]]     # (row, col) for each candidate
    coords: list[tuple[float, float]]  # (lat, lon) for each candidate
    n_candidates: int

@dataclass(frozen=True)
class VariableUncertainty:
    variable: str                          # "fmc" | "wind_speed" | "wind_direction"
    variance: np.ndarray                   # float[M] at candidate locations
    sensitivity: np.ndarray                # float[M] at candidate locations
    spatial_correlation: np.ndarray        # float[M, M]
    candidate_locations: CandidateLocations  # index reference — MUST match across variables

@dataclass(frozen=True)
class UncertaintyMap:
    variables: list[VariableUncertainty]
    total_variance: np.ndarray             # float[M] at candidate locations
    candidate_locations: CandidateLocations
    priority_weights: np.ndarray           # float[M], from PriorityOverrides
    exclusion_mask: np.ndarray             # bool[M], True = excluded

class UncertaintyDecomposer:
    def decompose(
        self,
        ensemble: EnsembleResult,
        snapshot: CycleSnapshot,
        candidates: CandidateLocations
    ) -> UncertaintyMap:
        """Decompose ensemble variance by variable at candidate locations.
        Applies priority weights and exclusion mask from snapshot.
        Pure function."""
        ...
```

**Key design:** `CandidateLocations` is a shared index. Every `VariableUncertainty` carries a reference to the same `CandidateLocations` object. The QUBO Builder verifies index consistency before constructing the matrix. This prevents the silent index misalignment problem.

**Candidate selection strategy (hackathon):** Subsample the grid at 5-10× the resolution. Optionally add terrain-informed points: ridgelines, valley floors, fuel-type boundaries. M = 100-300 candidates for a 100×100 grid.

---

### Component 4: QUBO Builder & Solver

**Purpose:** Construct QUBO from uncertainty data, solve, produce MissionQueue.

```python
@dataclass(frozen=True)
class QUBOMatrix:
    Q: np.ndarray                          # float[M, M], upper triangular
    candidate_locations: CandidateLocations # index reference
    w: np.ndarray                          # float[M], linear terms (for diagnostics)
    J: np.ndarray                          # float[M, M], quadratic terms (for diagnostics)
    penalty_lambda: float

@dataclass(frozen=True)
class SolverResult:
    selected_indices: list[int]            # into candidate_locations
    energy: float
    solver_name: str
    solve_time_s: float
    metadata: dict                         # solver-specific (chain breaks, num_reads, etc.)

@dataclass(frozen=True)
class Observability:
    """Per-candidate, per-variable: can the drone measure this here, and how well?"""
    fmc: np.ndarray          # float[M], 0-1 (0 = unmeasurable, 1 = perfect)
    wind_speed: np.ndarray   # float[M]
    wind_direction: np.ndarray  # float[M]

class QUBOBuilder:
    def build(
        self,
        uncertainty: UncertaintyMap,
        observability: Observability,
        k_drones: int
    ) -> QUBOMatrix:
        """Construct QUBO. Pure function.
        Verifies candidate_locations index consistency across inputs."""
        # Verify indices match
        assert uncertainty.candidate_locations == observability.candidate_locations
        ...

class QUBOSolver:
    """Wraps multiple solvers. Tries primary, falls back on failure."""

    def solve(self, qubo: QUBOMatrix, k_drones: int) -> SolverResult:
        """Try solvers in order: D-Wave → SA → greedy.
        Log which solver succeeded."""
        for solver in [self._dwave, self._sa, self._greedy]:
            try:
                return solver(qubo, k_drones)
            except SolverError as e:
                log.warning(f"{solver.name} failed: {e}, trying next")
        raise AllSolversFailedError()

    # Degradation contract:
    # - D-Wave unreachable → SA fallback (seconds)
    # - SA timeout → greedy fallback (milliseconds)
    # - Greedy always succeeds (O(MK))

class MissionQueueBuilder:
    def build(
        self,
        solver_result: SolverResult,
        baseline_results: dict[str, SolverResult],
        uncertainty: UncertaintyMap,
        forced_targets: list[ForcedTarget],
        cycle_id: int,
        previous_queue: MissionQueue | None
    ) -> tuple[MissionQueue, SituationPackage]:
        """Convert solver output to MissionQueue.
        Computes substitutes, injects forced targets,
        builds situation package with placement stability."""
        ...
```

**Substitute computation:** For each selected location i, find the 3 unselected locations within a radius r that have the highest w_i. These are alternatives the UTM can use without re-querying IGNIS.

**Baselines:** Greedy, uniform, and fire-front baselines run in parallel. Their results are stored for evaluation but only the primary solver's result enters the MissionQueue.

---

### Component 5: Observation Source (interface + implementations)

**Purpose:** Provide observations to Data Assimilation. Abstracted so simulation and real sources are interchangeable.

```python
class ObservationSource(Protocol):
    def get_observations(
        self,
        observed_cells: list[tuple[int, int]]
    ) -> list[DroneObservation]:
        """Return observations for the given cells."""
        ...

class SimulatedSource:
    """Generates synthetic observations from a hidden ground truth."""

    def __init__(self, ground_truth: CycleSnapshot, noise_config: NoiseConfig):
        self._truth = ground_truth
        self._noise = noise_config

    def get_observations(self, observed_cells):
        observations = []
        for cell in observed_cells:
            obs = DroneObservation(
                location=cell,
                fuel_moisture=self._truth.fuel_moisture[cell] + np.random.normal(0, self._noise.fmc_sigma),
                fuel_moisture_sigma=self._noise.fmc_sigma,
                wind_speed=self._truth.wind_field[cell] + np.random.normal(0, self._noise.ws_sigma),
                wind_speed_sigma=self._noise.ws_sigma,
                wind_direction=self._truth.wind_dir_field[cell] + np.random.normal(0, self._noise.wd_sigma),
                wind_direction_sigma=self._noise.wd_sigma,
                timestamp=datetime.now(),
                drone_id="sim"
            )
            observations.append(obs)
        return observations

@dataclass(frozen=True)
class NoiseConfig:
    fmc_sigma: float         # e.g., 0.05
    ws_sigma: float          # e.g., 1.0 m/s
    wd_sigma: float          # e.g., 10 degrees
    degrade_near_fire: bool
    degradation_radius: int  # cells from active fire front
    degradation_factor: float  # multiply sigma by this near fire

class RealSource:
    """Buffers real DroneObservation objects pushed via orchestrator.
    get_observations returns and clears the buffer."""

    def __init__(self):
        self._buffer: list[DroneObservation] = []

    def push(self, obs: DroneObservation) -> None:
        self._buffer.append(obs)

    def get_observations(self, observed_cells=None):
        # observed_cells ignored — returns whatever has been pushed
        result = list(self._buffer)
        self._buffer.clear()
        return result
```

---

### Component 6: Data Assimilation

**Purpose:** EnKF update of ensemble state using observations. Returns new state, does not mutate anything.

```python
@dataclass(frozen=True)
class AssimilationResult:
    updated_fuel_moisture: np.ndarray      # float[rows, cols] ensemble mean
    updated_wind_speed: np.ndarray         # float[rows, cols] ensemble mean
    updated_wind_direction: np.ndarray     # float[rows, cols] ensemble mean
    updated_member_parameters: list[dict]  # per-member updated params for next ensemble
    posterior_variance: np.ndarray         # float[rows, cols] at observed variables
    variance_reduction: float              # scalar: total variance removed by observations
    significant_change: bool              # True if variance_reduction > threshold
    wind_shift_detected: bool             # True if observed wind differs >30° from prior

class DataAssimilator:
    def __init__(self, config: AssimilationConfig):
        self._localization_radius = config.localization_radius
        self._inflation_factor = config.inflation_factor
        self._replan_threshold = config.replan_threshold    # min variance_reduction to trigger replan
        self._wind_shift_threshold = config.wind_shift_deg  # degrees

    def assimilate(
        self,
        observations: list[DroneObservation],
        ensemble: EnsembleResult,
        snapshot: CycleSnapshot
    ) -> AssimilationResult:
        """EnKF update. Pure function — no side effects.
        Returns result with flags for replan triggers."""
        ...

    # Degradation contract:
    # - No observations → return prior unchanged,
    #   significant_change=False, wind_shift_detected=False
    # - Single observation → single-obs EnKF update (still valid)
    # - Observation far from any ensemble member's range → log warning,
    #   apply update anyway (EnKF handles gracefully via large innovation)

@dataclass(frozen=True)
class AssimilationConfig:
    localization_radius: int       # cells — taper Kalman gain beyond this
    inflation_factor: float        # >1.0 — prevent filter collapse
    replan_threshold: float        # min variance_reduction to flag significant_change
    wind_shift_deg: float          # degrees — threshold for wind_shift_detected
```

**Key design:** Data Assimilation returns `significant_change` and `wind_shift_detected` as flags. It does NOT decide whether to replan. The orchestrator reads these flags and decides.

---

### Component 7: Orchestrator

**Purpose:** Sequences components, manages cycle state, handles replan triggers. The only component that mutates the StateFactory.

```python
class Orchestrator:
    def __init__(
        self,
        state_factory: StateFactory,
        fire_engine: FireEngine,
        decomposer: UncertaintyDecomposer,
        qubo_builder: QUBOBuilder,
        solver: QUBOSolver,
        queue_builder: MissionQueueBuilder,
        obs_source: ObservationSource,
        assimilator: DataAssimilator,
        config: OrchestratorConfig
    ):
        self._state = state_factory
        self._fire = fire_engine
        self._decomp = decomposer
        self._qubo = qubo_builder
        self._solver = solver
        self._queue_builder = queue_builder
        self._obs = obs_source
        self._assim = assimilator
        self._config = config
        self._cycle_count = 0
        self._last_queue: MissionQueue | None = None

    def run_cycle(self) -> tuple[MissionQueue, SituationPackage]:
        """Full cycle. Returns mission queue and situation package."""
        snapshot = self._state.snapshot()

        # 1. Run ensemble
        ensemble = self._fire.run(snapshot, self._config.ensemble)
        if ensemble.arrival_time_variance.max() < 1e-6:
            return self._empty_queue("Model confident, no measurements needed")

        # 2. Decompose uncertainty
        candidates = self._select_candidates(snapshot)
        uncertainty = self._decomp.decompose(ensemble, snapshot, candidates)

        # 3. Build and solve QUBO
        observability = self._compute_observability(candidates, snapshot)
        qubo = self._qubo.build(uncertainty, observability, self._config.k_drones)
        result = self._solver.solve(qubo, self._config.k_drones)
        baselines = self._run_baselines(uncertainty, self._config.k_drones)

        # 4. Build mission queue
        queue, situation = self._queue_builder.build(
            result, baselines, uncertainty,
            snapshot.forced_targets, self._cycle_count, self._last_queue
        )

        # 5. Simulate/collect observations
        observed_cells = [r.grid_cell for r in queue.requests]
        observations = self._obs.get_observations(observed_cells)

        # 6. Assimilate
        assim_result = self._assim.assimilate(observations, ensemble, snapshot)
        self._state.apply_assimilation(assim_result)

        # 7. Update internal state
        self._last_queue = queue
        self._cycle_count += 1
        self._state.set_previous_queue(queue)

        return queue, situation

    def ingest_observation(self, obs: DroneObservation) -> Optional[MissionQueue]:
        """Process a single streaming observation.
        Returns updated queue if replan threshold met."""
        snapshot = self._state.snapshot()

        # Quick single-observation assimilation
        # (reuses last ensemble — does not re-run fire engine)
        assim_result = self._assim.assimilate([obs], self._last_ensemble, snapshot)
        self._state.apply_assimilation(assim_result)

        if assim_result.wind_shift_detected:
            log.warning("Wind shift detected — triggering full replan")
            return self.run_cycle()

        if assim_result.significant_change and self._last_queue:
            return self._fast_recheck(snapshot)

        return None

    def _fast_recheck(self, snapshot: CycleSnapshot) -> MissionQueue:
        """Recompute w_i at pending target locations using updated
        posterior variance. Does NOT re-solve QUBO — just re-ranks
        existing targets and drops any below 50% of original value."""
        ...

    # Delegation methods for external API
    def add_priority_region(self, region): self._state.add_priority_region(region)
    def remove_priority_region(self, rid): self._state.remove_priority_region(rid)
    def add_exclusion_zone(self, zone): self._state.add_exclusion_zone(zone)
    def remove_exclusion_zone(self, zid): self._state.remove_exclusion_zone(zid)
    def add_forced_target(self, t): self._state._forced_targets.append(t)
    def update_request_status(self, u): ...  # tracking only

    def get_status(self) -> SystemStatus:
        return SystemStatus(
            cycle_count=self._cycle_count,
            last_cycle_time_s=self._last_cycle_time,
            solver_used=self._last_solver_used,
            ensemble_size=self._config.ensemble.n_members,
            observations_ingested=self._obs_count,
            pending_requests=len(self._last_queue.requests) if self._last_queue else 0,
            replan_triggered=self._last_replan_triggered
        )
```

---

## Interface Summary

```
Component                  Input                              Output
──────────────────────── ────────────────────────────────── ──────────────────────────────
StateFactory             Override/exclusion/fire/weather     CycleSnapshot (frozen)
                         updates from Orchestrator

Fire Engine              CycleSnapshot, EnsembleConfig       EnsembleResult (frozen)

Uncertainty Decomposer   EnsembleResult, CycleSnapshot,      UncertaintyMap (frozen)
                         CandidateLocations                  (carries typed index refs)

QUBO Builder             UncertaintyMap, Observability        QUBOMatrix (frozen)

QUBO Solver              QUBOMatrix                          SolverResult (frozen)

Mission Queue Builder    SolverResult, baselines,             MissionQueue, SituationPackage
                         UncertaintyMap, forced targets       (frozen)

Observation Source       observed cells                      list[DroneObservation] (frozen)

Data Assimilator         list[DroneObservation],              AssimilationResult (frozen)
                         EnsembleResult, CycleSnapshot        (includes replan flags)

Orchestrator             All of the above                    MissionQueue (to UTM)
                                                            SituationPackage (to COP)
```

**Every component is a pure function** (input → output, no side effects) except:

- `StateFactory`: mutable, but only the Orchestrator writes to it
- `RealSource`: buffers incoming observations (mutable by design)
- `Orchestrator`: manages cycle state and delegates mutations to StateFactory

---

## Degradation Contracts

|Component|Failure Mode|Behavior|
|---|---|---|
|Fire Engine|Zero variance (all members agree)|Return result with flag. Orchestrator emits empty queue with "model confident" status.|
|Fire Engine|Ensemble timeout (>5 min)|Reduce N_members by half, retry once. If still fails, use previous ensemble with warning.|
|Uncertainty Decomposer|All candidates excluded|Return empty UncertaintyMap. Orchestrator emits empty queue.|
|QUBO Solver (D-Wave)|QPU unreachable / timeout|Fall back to simulated annealing. Log solver switch.|
|QUBO Solver (SA)|SA timeout|Fall back to greedy. Log solver switch.|
|QUBO Solver (greedy)|Always succeeds|O(MK) worst case, milliseconds at hackathon scale.|
|Data Assimilator|No observations received|Return prior unchanged. significant_change=False.|
|Data Assimilator|Observation wildly outside ensemble range|Log warning, apply update (EnKF handles via large innovation + localization).|
|Observation Source (real)|Buffer empty when polled|Return empty list. Assimilator handles gracefully.|

---

## Division of Work (5-person team)

|Person|Components|Day 1|Day 2|Day 3|Day 4|Day 5|
|---|---|---|---|---|---|---|
|A|Fire Engine|Data types + CA implementation|Ensemble perturbation framework|Integration with orchestrator|Scenario tuning|Demo support|
|B|Uncertainty Decomp + QUBO Builder|CandidateLocations + variance decomposition|Correlation estimation + QUBO matrix assembly|Integration with solver|Multi-scenario runs|Demo support|
|C|Solver + EMBER|Ocean SDK setup + SA fallback|D-Wave submission + embedding analysis|Greedy + baselines|Comparison framework|Results + slides|
|D|Obs Source + Path Planner + UTM interface|SimulatedSource + NoiseConfig|Observation→cell mapping + simple path planner|UTM integration|Streaming obs + replan|Demo support|
|E|Orchestrator + Assimilator + Viz|StateFactory + CycleSnapshot + orchestrator skeleton|EnKF implementation|Full loop working|Dashboard + metrics|Demo lead|

**Day 1 shared task (first 2 hours):** All five people agree on data types. Define `TerrainData`, `CycleSnapshot`, `EnsembleResult`, `UncertaintyMap`, `CandidateLocations`, `MissionQueue`, `DroneObservation` in a shared `types.py`. No one writes component code until this file exists and everyone has imported it.

---

## Cut List (if time runs short, cut last first)

1. ~~Transit information optimization in path planner~~ → direct routes
2. ~~Airspace constraints / exclusion zones~~ → assume open airspace
3. ~~D-Wave QPU submission~~ → SA only, show QUBO structure
4. ~~Streaming observation / myopic replan~~ → batch cycles only
5. ~~Multiple fire scenarios~~ → one well-tuned scenario
6. ~~EMBER embedding analysis~~ → defer to slides
7. ~~Situation package / dashboard~~ → terminal output with plots

**Do not cut:** Four-way comparison (QUBO vs. greedy vs. uniform vs. fire-front) across multiple cycles with entropy reduction plots. This is the result.