# IGNIS: Software Component Design

---

## System Overview

Seven components connected by defined interfaces. Data flows as a loop: predict → decompose → allocate → route → observe → assimilate → predict.

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  TERRAIN   │    │  FIRE     │    │ UNCERTAINTY│    │  QUBO     │
│  & STATE   │───▶│  ENGINE   │───▶│  DECOMP   │───▶│  BUILDER  │
│  MANAGER   │    │           │    │           │    │  & SOLVER  │
└─────┬──▲──┘    └───────────┘    └───────────┘    └─────┬─────┘
      │  │                                               │
      │  │                                               ▼
      │  │                                         ┌───────────┐
      │  │                                         │   PATH    │
      │  │                                         │  PLANNER  │
      │  │                                         └─────┬─────┘
      │  │                                               │
      │  │       ┌───────────┐                           │
      │  └───────│   DATA    │◀──────────────────────────┘
      │          │  ASSIM    │       ┌───────────┐
      └─────────▶│           │◀──────│ SIMULATED │
                 └───────────┘       │ OBSERVER  │
                                     └───────────┘
```

---

## Component 1: Terrain & State Manager

**Purpose:** Single source of truth for all static and dynamic state. Every other component reads from and writes to this.

**Owns:**

- Terrain grid (DEM, slope, aspect) — static
- Fuel map (fuel model ID per cell) — static
- Weather state (wind speed, wind direction, temperature, humidity) — updated per cycle
- Fuel moisture field — updated by data assimilation
- Fire state (arrival time per cell, active perimeter) — updated by fire engine
- Ensemble output cache (burn probabilities, variance maps) — updated by fire engine
- Drone positions and status — updated by path planner

**Data structures:**

```
Grid:
  shape: (rows, cols)
  resolution: meters per cell
  origin: (lat, lon)

StaticLayers:
  elevation: float[rows, cols]
  slope: float[rows, cols]
  aspect: float[rows, cols]
  fuel_model: int[rows, cols]

DynamicState:
  wind_speed: float[rows, cols]
  wind_direction: float[rows, cols]
  fuel_moisture: float[rows, cols]
  fire_arrival_time: float[rows, cols]  # NaN = unburned

EnsembleCache:
  burn_probability: float[rows, cols]
  arrival_time_variance: float[rows, cols]
  variance_by_source: dict[str, float[rows, cols]]
    # keys: "fmc", "wind_speed", "wind_direction"
```

**Interface:** All other components receive a reference to the state manager and read/write through it. No component stores its own copy of grid state.

---

## Component 2: Fire Engine

**Purpose:** Run N-member ensemble of fire spread simulations. Produce per-cell burn probabilities and arrival time distributions.

**Input (from State Manager):**

- Current fire state (perimeter or arrival time field)
- Static layers (terrain, fuel)
- Dynamic state (weather, fuel moisture)
- Perturbation parameters (ranges for each uncertain variable)

**Process:**

1. Generate N parameter sets via Latin hypercube sampling over perturbation ranges
2. For each member: run fire spread forward T hours from current state
3. Collect per-cell arrival times across ensemble

**Output (written to State Manager):**

```
EnsembleResult:
  member_arrival_times: float[N, rows, cols]  # per-member arrival times
  burn_probability: float[rows, cols]          # fraction of members that burned each cell
  mean_arrival_time: float[rows, cols]
  arrival_time_variance: float[rows, cols]
```

**Implementation (hackathon):** Cellular automata on the grid. Each cell transitions from unburned to burning based on neighbor states, fuel model, slope, wind, and FMC. Rothermel ROS formula gives transition probability. Each ensemble member uses a different draw of (FMC, wind_speed, wind_direction).

**Key constraint:** Must run full ensemble in < 3 minutes. At 100 members on a 100×100 grid with 15-min timesteps over 6 hours, this is ~2.4M cell updates per member, 240M total. Feasible in NumPy.

---

## Component 3: Uncertainty Decomposition

**Purpose:** Attribute per-cell prediction variance to specific input variables. Produce the uncertainty attribution map that drives QUBO construction.

**Input (from State Manager):**

- `member_arrival_times[N, rows, cols]`
- Perturbation parameter sets used for each member

**Process:**

1. Group ensemble members by perturbation factor (which variable was perturbed most)
2. For each cell, compute between-group variance for each factor (ANOVA-style)
3. Compute sensitivity: S_v(c) = |∂ mean_arrival_time / ∂v| estimated by finite difference across ensemble
4. Compute spatial correlation matrix ρ_v(i,j) from ensemble covariance for each variable v

**Output:**

```
UncertaintyMap:
  total_variance: float[rows, cols]
  fractional_attribution: dict[str, float[rows, cols]]
    # e.g., {"fmc": 0.6, "wind_speed": 0.3, "wind_direction": 0.1} per cell
  sensitivity: dict[str, float[rows, cols]]
  spatial_correlation: dict[str, float[M, M]]
    # M = number of candidate measurement locations
    # One correlation matrix per variable
```

**Interface note:** `spatial_correlation` is computed only over candidate measurement locations (not all grid cells) to keep the matrix tractable. Candidate locations are a subsampled grid or terrain-informed set of strategic points (ridgelines, valley floors, fuel transitions).

---

## Component 4: QUBO Builder & Solver

**Purpose:** Construct the QUBO matrix from uncertainty data, solve it, and output selected measurement regions.

**Input (from Uncertainty Decomposition):**

```
- UncertaintyMap (w_i coefficients from variance × sensitivity)
- spatial_correlation (J_ij coefficients from correlation structure)
- K: number of drones available
- observability: dict[str, float[M]]  # D_v(i): can the drone measure variable v at location i?
```

**Process:**

1. Compute linear terms: `w_i = Σ_v σ²_v(i) × S_v(i) × D_v(i)`
2. Compute quadratic terms: `J_ij = -Σ_v ρ_v(i,j) × sqrt(w_i × w_j)`
3. Add cardinality penalty: `λ(Σ x_i - K)²`, λ = max(|w_i|)
4. Assemble QUBO matrix Q (upper triangular, M × M)
5. Submit to solver

**Solvers (run all, compare):**

```
Solvers:
  dwave:
    method: DWaveSampler + EmbeddingComposite (Ocean SDK)
    params: num_reads=1000, annealing_time=20
  simulated_annealing:
    method: neal.SimulatedAnnealingSampler (Ocean SDK)
    params: num_reads=1000
  greedy:
    method: iterative marginal gain maximization
    # Does NOT use QUBO; operates on original submodular objective
  uniform:
    method: regular grid subsample of M locations, select K nearest to grid points
  fire_front:
    method: select K locations evenly spaced along predicted fire perimeter
```

**Output:**

```
PlacementResult:
  selected_locations: list[int]        # indices into candidate location array
  selected_coords: list[(row, col)]    # grid coordinates
  solver_metadata:
    energy: float
    timing: float
    chain_break_fraction: float        # D-Wave only
  baseline_results: dict[str, list[int]]  # results from each baseline solver
```

---

## Component 5: Path Planner

**Purpose:** Convert selected measurement regions into feasible drone flight paths that collect data continuously along transit.

**Input:**

```
- PlacementResult.selected_coords: K target locations
- drone_base: (row, col)             # staging area
- drone_specs:
    max_speed: m/s
    endurance: minutes
    measurement_altitude: meters
- airspace_constraints: list[polygon]  # no-fly zones (TFRs)
- information_field: float[rows, cols] # w_i values for all cells (for transit optimization)
```

**Process:**

1. Assign target locations to drones (if K_targets > K_drones, prioritize by w_i)
2. For each drone, plan path: base → targets → base
3. Transit routing: prefer paths through high-information cells when detour cost is small
    - For each transit segment, compare direct route vs. information-weighted detour
    - Accept detour if: info_gain(detour) / time_cost(detour) > threshold
4. Check all paths against airspace constraints; reroute if intersection
5. Verify endurance feasibility; drop lowest-priority target if infeasible

**Output:**

```
FlightPlan:
  per_drone: list[DronePlan]
    DronePlan:
      waypoints: list[(row, col, altitude, action)]
        # action: "transit" | "loiter_measure" | "return"
      estimated_duration: minutes
      cells_observed: list[(row, col)]  # all cells along path with measurement
      information_collected: float      # integrated w_i along path
```

**Implementation (hackathon):** Simple nearest-neighbor TSP for waypoint ordering. Direct line transit (no detour optimization). Airspace constraints as rectangular exclusion zones. The detour optimization is a Phase I refinement.

---

## Component 6: Simulated Observer

**Purpose:** Generate synthetic observations as if drones flew the planned paths. Hackathon substitute for real drone data.

**Input:**

```
- FlightPlan.cells_observed: list of cells where measurements are taken
- ground_truth: the "true" state used to generate the fire scenario
    # Known to this component only — not visible to fire engine or assimilation
- measurement_noise:
    fmc_sigma: float       # e.g., 0.05 (5% FMC measurement error)
    wind_speed_sigma: float
    wind_direction_sigma: float
```

**Process:**

1. For each observed cell, extract ground truth values
2. Add Gaussian noise calibrated to literature measurement accuracy
3. Optionally: degrade accuracy near fire front (increase noise for cells within N cells of active fire)

**Output:**

```
ObservationSet:
  observations: list[Observation]
    Observation:
      location: (row, col)
      fmc: float ± uncertainty
      wind_speed: float ± uncertainty
      wind_direction: float ± uncertainty
  observation_noise_covariance: R matrix
```

---

## Component 7: Data Assimilation

**Purpose:** Update ensemble state using drone observations. Produce updated fire state for next cycle.

**Input:**

```
- EnsembleResult.member_arrival_times (prior ensemble from fire engine)
- Current ensemble parameter fields: FMC[N, rows, cols], wind[N, rows, cols]
- ObservationSet from simulated observer
```

**Process (EnKF):**

1. Construct observation operator H: extracts state variables at observation locations
2. Compute ensemble mean and covariance of H(x) (predicted observations)
3. Compute Kalman gain: K = P_f H^T (H P_f H^T + R)^{-1}
4. For each member n: x_a^(n) = x_f^(n) + K (y + ε^(n) - H x_f^(n))
5. Apply localization: taper K to zero beyond correlation length (prevents spurious distant updates)

**Output (written to State Manager):**

```
Updated fields:
  fuel_moisture: float[rows, cols]       # ensemble mean of updated FMC
  wind_speed: float[rows, cols]          # ensemble mean of updated wind
  Updated ensemble parameter sets for next fire engine run
```

**The loop closes here.** The updated state feeds back to the Fire Engine for the next cycle.

---

## Interface Summary

```
Component               Reads From                  Writes To
─────────────────────── ─────────────────────────── ──────────────────────
1. State Manager        (all components)             (all components)
2. Fire Engine          State Manager                State Manager (ensemble cache)
3. Uncertainty Decomp   State Manager (ensemble)     UncertaintyMap → QUBO Builder
4. QUBO Builder/Solver  UncertaintyMap               PlacementResult → Path Planner
5. Path Planner         PlacementResult, State Mgr   FlightPlan → Sim Observer
6. Simulated Observer   FlightPlan, ground truth     ObservationSet → Data Assim
7. Data Assimilation    ObservationSet, ensemble     State Manager (updated state)
```

---

## Cycle Orchestrator

A main loop that sequences the components:

```python
def run_cycle(state, config):
    ensemble = fire_engine.run(state, config.N_members, config.horizon)
    state.update_ensemble(ensemble)

    uncertainty = decompose(ensemble, config.candidate_locations)

    qubo_result = build_and_solve(uncertainty, config.K_drones, config.solvers)
    baseline_results = run_baselines(uncertainty, config.K_drones)

    flight_plan = plan_paths(qubo_result, state, config.drone_specs)
    baseline_plans = {name: plan_paths(bl, state, config.drone_specs)
                      for name, bl in baseline_results.items()}

    observations = simulate_observations(flight_plan, state.ground_truth, config.noise)
    baseline_obs = {name: simulate_observations(bp, state.ground_truth, config.noise)
                    for name, bp in baseline_plans.items()}

    assimilate(observations, ensemble, state)

    metrics = evaluate(state, observations, baseline_obs)
    return metrics

# Main loop
for cycle in range(config.n_cycles):
    metrics = run_cycle(state, config)
    log(cycle, metrics)
```

---

## Division of Work (5-person team, 5 days)

|Person|Components|Notes|
|---|---|---|
|A|Fire Engine (2)|Core simulation. Needs strong NumPy/computational skills.|
|B|Uncertainty Decomp (3) + QUBO Builder (4)|Math-heavy. Needs to understand variance decomposition and QUBO structure.|
|C|QUBO Solver integration + EMBER connection|D-Wave Ocean SDK, embedding analysis. Closest to existing EMBER work.|
|D|Path Planner (5) + Simulated Observer (6)|Geometry, routing, synthetic data generation.|
|E|Data Assimilation (7) + Orchestrator + Visualization|EnKF implementation, main loop, dashboard.|

State Manager (1) is built incrementally by whoever needs it first (likely A on day 1), then shared.

---

## Minimum Viable Demo

If time runs short, cut in this order (last = cut first):

1. ~~Transit information optimization in path planner~~ → use direct routes
2. ~~Airspace constraints~~ → assume open airspace
3. ~~D-Wave QPU submission~~ → use simulated annealing only, show QUBO structure
4. ~~Multiple fire scenarios~~ → run one scenario well
5. ~~EMBER embedding analysis~~ → defer to poster/slides

**Do not cut:** The comparison between QUBO/greedy/uniform/fire-front placements across multiple cycles. This is the central result.