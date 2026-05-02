## 1. Existing Implementations

| System            | Physics                                | Propagation                           | FMC Input                                 | Data Source              | Speed                 | Open Source          |
| ----------------- | -------------------------------------- | ------------------------------------- | ----------------------------------------- | ------------------------ | --------------------- | -------------------- |
| FARSITE / FlamMap | Full Rothermel + crown fire + spotting | Huygens wavelet (geometric perimeter) | Continuous, per fuel class                | LANDFIRE                 | Minutes-hours per run | No (Windows desktop) |
| SimFire           | Full Rothermel (Andrews 2018)          | Cellular automata                     | Continuous, per fuel class                | LANDFIRE native          | Seconds per run (CPU) | Yes (MITRE, Python)  |
| PyTorchFire       | Alexandridis (2008) heuristic          | Cellular automata                     | Categorical vegetation density            | Custom                   | Milliseconds (GPU)    | Yes (PyTorch)        |
| Cell2Fire         | Rothermel + fuel consumption           | Cellular automata                     | Continuous                                | Custom CSV               | Seconds (C++/Python)  | Yes                  |
| WRF-SFIRE         | Rothermel + full atmosphere coupling   | Level set                             | Continuous, with fuel moisture model + DA | LANDFIRE + weather model | Hours (HPC)           | Yes                  |

FARSITE/FlamMap is the operational standard but is not callable from Python. WRF-SFIRE is the research gold standard but requires HPC. SimFire is the closest existing tool to what IGNIS needs — Rothermel physics, LANDFIRE integration, Python API. PyTorchFire is fastest but lacks Rothermel's FMC sensitivity.

For IGNIS, we need: Rothermel-level FMC sensitivity, GPU-parallelizable ensemble execution, and programmatic access to per-cell fire arrival times. No existing tool provides all three. We build our own, using SimFire's Rothermel implementation and Andrews (2018) as reference, with PyTorch tensor operations for GPU execution.

---

## 2. What the Fire Model Computes

The model answers one question: given current fuel, weather, and terrain conditions, when does fire arrive at each cell? It does this N times (ensemble) with perturbed inputs.

The computation has two layers:

**Layer 1 — Rate of Spread (per cell, no spatial interaction):** The Rothermel equation computes how fast fire CAN spread at each cell given local conditions. This is pure arithmetic on local properties.

**Layer 2 — Spatial Propagation (cell-to-cell, CA stencil):** Fire actually spreads from burning cells to unburned neighbors. The Rothermel ROS determines the probability or rate of this transition. This is a spatial stencil operation.

---

## 3. Layer 1: Rothermel Rate of Spread

### The Equation

The complete Rothermel surface fire rate of spread (Andrews 2018, RMRS-GTR-371):

```
R = (I_R × ξ × (1 + φ_w + φ_s)) / (ρ_b × ε × Q_ig)
```

where R is rate of spread (ft/min or m/min), and each term is computed from fuel, weather, and terrain inputs as follows.

### Input Parameters

**From fuel model (Anderson 13 or Scott & Burgan 40, via LANDFIRE):**

Each fuel model specifies these parameters. LANDFIRE provides a fuel model ID per 30m cell; the parameters are looked up from a table.

|Parameter|Symbol|Units|Description|
|---|---|---|---|
|1-hr fuel load|w_1|tons/acre|Dead fuel, diameter < 0.25 in|
|10-hr fuel load|w_10|tons/acre|Dead fuel, 0.25-1.0 in diameter|
|100-hr fuel load|w_100|tons/acre|Dead fuel, 1.0-3.0 in diameter|
|Live herbaceous load|w_lh|tons/acre|Live grass/herbs|
|Live woody load|w_lw|tons/acre|Live shrubs|
|1-hr SAV ratio|σ_1|1/ft|Surface area to volume ratio|
|Live herb SAV|σ_lh|1/ft||
|Live woody SAV|σ_lw|1/ft||
|Fuel bed depth|δ|ft||
|Dead fuel moisture of extinction|M_x|fraction|FMC above which fire won't spread|
|Heat content|h|BTU/lb|Typically 8,000 for dead fuel|
|Particle density|ρ_p|lb/ft³|Typically 32 for wood|

**From weather (GP estimate + perturbation):**

|Parameter|Symbol|Units|Source|
|---|---|---|---|
|1-hr dead fuel moisture|M_1|fraction|GP posterior from RAWS + drone obs|
|10-hr dead fuel moisture|M_10|fraction|GP posterior|
|100-hr dead fuel moisture|M_100|fraction|GP posterior|
|Live herbaceous moisture|M_lh|fraction|GP posterior or seasonal estimate|
|Live woody moisture|M_lw|fraction|GP posterior or seasonal estimate|
|Midflame wind speed|U|mi/hr|GP posterior from RAWS + drone obs|
|Wind direction|θ_w|degrees|GP posterior|

**From terrain (LANDFIRE DEM, static):**

|Parameter|Symbol|Units|Source|
|---|---|---|---|
|Slope steepness|tan(φ)|dimensionless|Computed from DEM|
|Aspect|A|degrees|Computed from DEM|

### Intermediate Computations

The full Rothermel equation involves ~20 intermediate quantities. The canonical sequence (from Andrews 2018):

**Step 1: Characteristic SAV ratio**

```
σ' = Σ(f_i × σ_i)
```

Weighted average SAV across all fuel classes, where f_i is the fractional loading of class i.

**Step 2: Packing ratio and relatives**

```
β = (w_total / δ) / ρ_p          # actual packing ratio
β_op = 3.348 × σ'^(-0.8189)     # optimum packing ratio
β_ratio = β / β_op               # relative packing ratio
```

**Step 3: Reaction intensity I_R**

```
Γ' = Γ'_max × (β_ratio)^A × exp(A × (1 - β_ratio))

where:
  Γ'_max = σ'^1.5 / (495 + 0.0594 × σ'^1.5)     # maximum reaction velocity
  A = 133 × σ'^(-0.7913)                           # optimum reaction velocity ratio

η_M = 1 - 2.59×(M/M_x) + 5.11×(M/M_x)² - 3.52×(M/M_x)³   # moisture damping
η_s = 0.174 × S_e^(-0.19)                                     # mineral damping

I_R = Γ' × w_n × h × η_M × η_s                               # BTU/ft²/min
```

**This is where FMC enters.** The moisture damping coefficient η_M goes from 1.0 (bone dry) to 0.0 (at moisture of extinction). The cubic polynomial means sensitivity is nonlinear — small changes near the extinction threshold produce large changes in I_R and therefore in ROS.

**Step 4: Propagating flux ratio**

```
ξ = exp((0.792 + 0.681 × σ'^0.5) × (β + 0.1)) / (192 + 0.2595 × σ')
```

**Step 5: Wind factor**

```
C = 7.47 × exp(-0.133 × σ'^0.55)
B = 0.02526 × σ'^0.54
E = 0.715 × exp(-3.59 × 10⁻⁴ × σ')

φ_w = C × U^B × (β_ratio)^(-E)
```

**Step 6: Slope factor**

```
φ_s = 5.275 × β^(-0.3) × tan(φ)²
```

**Step 7: Effective heating number and heat of preignition**

```
ε = exp(-138 / σ')           # effective heating number
Q_ig = 250 + 1116 × M_f      # BTU/lb, heat of preignition
```

**Step 8: Bulk density**

```
ρ_b = w_total / δ             # lb/ft³
```

**Step 9: Rate of spread**

```
R = (I_R × ξ × (1 + φ_w + φ_s)) / (ρ_b × ε × Q_ig)
```

R is the head fire rate of spread in ft/min (multiply by 0.3048 for m/min).

### What Can Be Precomputed

Many intermediate quantities depend only on fuel model parameters (which are static per cell):

- σ', β, β_op, β_ratio, Γ'_max, A, Γ', ξ, ε, ρ_b, η_s

These are computed ONCE during initialization and stored as grid tensors.

Quantities that depend on dynamic inputs (recomputed each timestep or per ensemble member):

- η_M (depends on FMC)
- φ_w (depends on wind speed)
- φ_s (depends on slope — static but directional component depends on wind-slope interaction)
- Q_ig (depends on FMC)
- I_R (depends on η_M)
- R (depends on all dynamic terms)

### Directional Spread

Rothermel computes head fire ROS (maximum spread rate, in the direction of wind + slope). Fire spreads in all directions but at different rates. The spread shape is typically modeled as an ellipse with the major axis aligned with the effective wind direction.

For a CA, this means each of the 8 neighbors has a different effective ROS depending on the angle between the wind+slope vector and the direction to that neighbor:

```
R_neighbor = R_head × (1 - ε_eccentricity) / (1 - ε_eccentricity × cos(θ_neighbor - θ_wind))
```

where ε_eccentricity is computed from wind speed (higher wind = more elongated ellipse, higher ratio between head fire and backing fire ROS).

---

## 4. Layer 2: Spatial Propagation (CA)

### State Machine

Each cell has three states:

- **Unburned** (0): can be ignited by burning neighbors
- **Burning** (1): actively on fire, can ignite neighbors
- **Burned** (2): fuel consumed, fire extinguished

### Transition Rules

**Unburned → Burning:** Probability of ignition in one timestep Δt from a single burning neighbor in direction d:

```
P_ignite(d) = 1 - exp(-R_d × Δt / cell_size)
```

where R_d is the directional ROS toward this neighbor (from the elliptical spread model). With multiple burning neighbors, the probability of remaining unburned is:

```
P_survive = Π_d (1 - P_ignite(d))^{neighbor_burning(d)}
P_catch_fire = 1 - P_survive
```

Ignition is stochastic: draw a uniform random number; if < P_catch_fire, the cell ignites.

**Burning → Burned:** After a residence time τ (determined by fuel load and intensity):

```
τ = 384 / σ'    (minutes)
```

When time-since-ignition exceeds τ, the cell transitions to burned.

### Timestep Selection

Δt must be small enough that fire cannot skip cells:

```
Δt < cell_size / R_max
```

For 50m cells and a maximum ROS of ~100 m/min (extreme conditions), Δt < 0.5 min. A safe default is Δt = 0.25-0.5 min (15-30 seconds).

### Recording Arrival Times

At each timestep, cells that transition from unburned to burning are stamped with the current simulation time. This produces the fire arrival time map T(i,j) — the primary output used by the uncertainty decomposition.

---

## 5. Fuel Model Parameter Table

The Anderson 13 fuel models, with parameters needed for Rothermel. This table is a static lookup in the code.

```python
ANDERSON_13 = {
    # model: (w_1, w_10, w_100, w_lh, w_lw, σ_1, σ_lh, σ_lw, δ, M_x, h)
    # loads in tons/acre, SAV in 1/ft, depth in ft, M_x as fraction, h in BTU/lb
    1:  (0.74, 0.00, 0.00, 0.00, 0.00, 3500, 1500, 1500, 1.0, 0.12, 8000),  # Short grass
    2:  (2.00, 1.00, 0.50, 0.50, 0.00, 3000, 1500, 1500, 1.0, 0.15, 8000),  # Timber grass
    3:  (3.01, 0.00, 0.00, 0.00, 0.00, 1500, 1500, 1500, 2.5, 0.25, 8000),  # Tall grass
    4:  (5.01, 4.01, 2.00, 0.00, 5.01, 2000, 1500, 1500, 6.0, 0.20, 8000),  # Chaparral
    5:  (1.00, 0.50, 0.00, 0.00, 2.00, 2000, 1500, 1500, 2.0, 0.20, 8000),  # Brush
    6:  (1.50, 2.50, 2.00, 0.00, 0.00, 1750, 1500, 1500, 2.5, 0.25, 8000),  # Dormant brush
    7:  (1.13, 1.87, 1.50, 0.00, 0.37, 1550, 1500, 1500, 2.5, 0.40, 8000),  # Southern rough
    8:  (1.50, 1.00, 2.50, 0.00, 0.00, 2000, 1500, 1500, 0.2, 0.30, 8000),  # Compact timber
    9:  (2.92, 0.41, 0.15, 0.00, 0.00, 2500, 1500, 1500, 0.2, 0.25, 8000),  # Hardwood litter
    10: (3.01, 2.00, 5.01, 0.00, 2.00, 2000, 1500, 1500, 1.0, 0.25, 8000),  # Timber understory
    11: (1.50, 4.51, 5.51, 0.00, 0.00, 1500, 1500, 1500, 1.0, 0.15, 8000),  # Light slash
    12: (4.01, 14.03, 16.53, 0.00, 0.00, 1500, 1500, 1500, 2.3, 0.20, 8000), # Medium slash
    13: (7.01, 23.04, 28.05, 0.00, 0.00, 1500, 1500, 1500, 3.0, 0.25, 8000), # Heavy slash
}
```

Note: values here are representative. The definitive source is Andrews (2018) Table 1 and Albini (1976). Some implementations use slightly different values. Verify against RMRS-GTR-371 before finalizing.

---

## 6. Data Requirements Summary

### Static (loaded once from LANDFIRE)

|Data|Source|Resolution|Format|
|---|---|---|---|
|Elevation (DEM)|LANDFIRE ELEV2020|30m|GeoTIFF|
|Slope|Derived from DEM or LANDFIRE SLPD2020|30m|GeoTIFF|
|Aspect|Derived from DEM or LANDFIRE ASP2020|30m|GeoTIFF|
|Fuel model ID|LANDFIRE FBFM13 (Anderson 13)|30m|GeoTIFF (integer)|

Downloaded via `landfire-python` with bounding box specification.

### Dynamic (per cycle, from GP + perturbation)

|Data|Source|Update Rate|
|---|---|---|
|1-hr dead FMC|GP posterior (RAWS + drone)|Per cycle (~20 min)|
|10-hr dead FMC|GP posterior|Per cycle|
|100-hr dead FMC|GP posterior (less variable)|Per cycle|
|Live herbaceous FMC|Seasonal estimate or GP|Daily|
|Live woody FMC|Seasonal estimate or GP|Daily|
|Midflame wind speed|GP posterior (RAWS + drone + forecast)|Per cycle|
|Wind direction|GP posterior|Per cycle|

### Initial Condition

|Data|Source|
|---|---|
|Fire perimeter / ignition point|Satellite (MODIS/VIIRS) or manual|

---

## 7. GPU Implementation

### Architecture

Every Rothermel computation is per-cell with no inter-cell dependencies. The CA stencil is a fixed-size neighbor convolution. Both are native GPU operations. The ensemble adds a batch dimension.

**Tensor shapes:**

```
Static terrain:
  slope:       (rows, cols)           float32
  aspect:      (rows, cols)           float32
  fuel_params: (n_params, rows, cols) float32  # precomputed from fuel model lookup

Dynamic state:
  fire_state:  (N, rows, cols)        int8     # 0/1/2 per member
  arrival_time:(N, rows, cols)        float32  # NaN = unburned
  time_burning:(N, rows, cols)        float32  # for residence time tracking

Dynamic inputs (perturbed per member):
  fmc:         (N, rows, cols)        float32
  wind_speed:  (N, rows, cols)        float32  # can be (N,) if spatially uniform
  wind_dir:    (N, rows, cols)        float32
```

N is the ensemble size (batch dimension). All PyTorch operations broadcast over N automatically.

### Initialization (runs once)

```python
def precompute_fuel_params(fuel_model_grid, fuel_table):
    """Lookup fuel model parameters for every cell. Returns static tensors."""
    # For each cell, index into ANDERSON_13 table
    w1 = fuel_table['w1'][fuel_model_grid]     # (rows, cols)
    sav = fuel_table['sav'][fuel_model_grid]   # (rows, cols)
    depth = fuel_table['depth'][fuel_model_grid]
    mx = fuel_table['mx'][fuel_model_grid]
    # ... all fuel params

    # Precompute static intermediates
    sigma_prime = compute_characteristic_sav(w1, w10, w100, sav1, sav10, sav100)
    beta = compute_packing_ratio(w_total, depth, rho_p)
    beta_op = 3.348 * sigma_prime ** (-0.8189)
    beta_ratio = beta / beta_op
    gamma_max = sigma_prime**1.5 / (495 + 0.0594 * sigma_prime**1.5)
    A_coeff = 133 * sigma_prime ** (-0.7913)
    gamma = gamma_max * beta_ratio**A_coeff * torch.exp(A_coeff * (1 - beta_ratio))
    xi = torch.exp((0.792 + 0.681*sigma_prime**0.5)*(beta+0.1)) / (192+0.2595*sigma_prime)
    epsilon = torch.exp(-138.0 / sigma_prime)
    rho_b = w_total / depth

    # Wind factor coefficients (static parts)
    C_wind = 7.47 * torch.exp(-0.133 * sigma_prime**0.55)
    B_wind = 0.02526 * sigma_prime**0.54
    E_wind = 0.715 * torch.exp(-3.59e-4 * sigma_prime)

    return StaticFuelParams(gamma, xi, epsilon, rho_b, mx, C_wind, B_wind, E_wind, ...)
```

All outputs are (rows, cols) tensors on GPU. Computed once.

### Per-Timestep Computation (runs every Δt, for all N members simultaneously)

```python
def compute_ros_batch(static, fmc, wind_speed, wind_dir, slope, aspect):
    """
    Compute ROS for all cells and all ensemble members.

    static: StaticFuelParams — (rows, cols) tensors, broadcast over N
    fmc: (N, rows, cols) — perturbed FMC per member
    wind_speed: (N, rows, cols) or (N, 1, 1)
    Returns: ros (N, rows, cols), wind_dir_effective (N, rows, cols)
    """
    # Moisture damping — THIS IS THE KEY FMC SENSITIVITY
    moisture_ratio = fmc / static.mx.unsqueeze(0)  # (N, rows, cols)
    eta_M = torch.clamp(
        1 - 2.59*moisture_ratio + 5.11*moisture_ratio**2 - 3.52*moisture_ratio**3,
        min=0.0, max=1.0
    )
    # eta_M = 0 when FMC >= moisture of extinction → no spread

    # Reaction intensity
    w_n = static.w_total * (1 - static.S_T)  # net fuel load (static)
    I_R = static.gamma * w_n * static.h * eta_M * static.eta_s
    # I_R shape: (N, rows, cols) — varies by member through eta_M

    # Wind factor
    phi_w = static.C_wind * wind_speed**static.B_wind * static.beta_ratio**(-static.E_wind)
    # phi_w shape: (N, rows, cols)

    # Slope factor (static, but direction matters)
    phi_s = 5.275 * static.beta**(-0.3) * torch.tan(slope)**2
    # phi_s shape: (rows, cols) — broadcast over N

    # Heat of preignition
    Q_ig = 250.0 + 1116.0 * fmc  # (N, rows, cols)

    # Rate of spread
    ros = (I_R * static.xi * (1 + phi_w + phi_s)) / (static.rho_b * static.epsilon * Q_ig)
    # ros shape: (N, rows, cols)

    return ros


def step_batch(fire_state, arrival_time, time_burning, ros, wind_dir,
               aspect, cell_size, dt, residence_time, t_current):
    """
    One CA timestep for all N members simultaneously.

    fire_state: (N, rows, cols) int8
    ros: (N, rows, cols) from compute_ros_batch
    Returns: updated fire_state, arrival_time, time_burning
    """
    burning = (fire_state == 1).float()  # (N, rows, cols)

    # Directional ignition probability for each of 8 neighbors
    # Compute angle from each cell to each neighbor direction
    neighbor_angles = torch.tensor([225, 270, 315, 180, 0, 135, 90, 45],
                                    dtype=torch.float32)  # degrees, 8-connected

    # Effective wind+slope direction per cell
    eff_dir = wind_dir  # simplified; full model combines wind and slope vectors

    # Eccentricity of spread ellipse (function of wind speed)
    LB = 0.936 * torch.exp(0.2566 * wind_speed) + 0.461 * torch.exp(-0.1548 * wind_speed) - 0.397
    eccentricity = torch.sqrt(1 - 1/LB**2)

    p_survive = torch.ones_like(ros)  # (N, rows, cols)

    for d, angle in enumerate(neighbor_angles):
        # Directional ROS adjustment
        cos_diff = torch.cos(torch.deg2rad(angle - eff_dir))
        R_d = ros * (1 - eccentricity) / (1 - eccentricity * cos_diff)
        R_d = torch.clamp(R_d, min=0)

        # Ignition probability from this direction
        p_ign_d = 1 - torch.exp(-R_d * dt / cell_size)

        # Shift burning mask to get "is neighbor in direction d burning?"
        # Use torch.roll with appropriate shifts for each direction
        shifts = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
        dy, dx = shifts[d]
        neighbor_burning = torch.roll(burning, shifts=(dy, dx), dims=(1, 2))

        # Zero out wrapped edges
        if dy == -1: neighbor_burning[:, -1, :] = 0
        if dy == 1:  neighbor_burning[:, 0, :] = 0
        if dx == -1: neighbor_burning[:, :, -1] = 0
        if dx == 1:  neighbor_burning[:, :, 0] = 0

        # Accumulate survival probability
        p_survive *= (1 - p_ign_d) ** neighbor_burning

    # Stochastic ignition
    p_catch = 1 - p_survive
    ignite = (torch.rand_like(p_catch) < p_catch) & (fire_state == 0)

    # Burnout: cells that have been burning longer than residence time
    burnout = (time_burning > residence_time) & (fire_state == 1)

    # State transitions
    new_state = fire_state.clone()
    new_state[burnout] = 2    # burning → burned
    new_state[ignite] = 1     # unburned → burning

    # Update tracking
    new_arrival = arrival_time.clone()
    new_arrival[ignite] = t_current

    new_time_burning = time_burning.clone()
    new_time_burning[fire_state == 1] += dt
    new_time_burning[ignite] = 0.0

    return new_state, new_arrival, new_time_burning
```

### Full Ensemble Run

```python
def run_ensemble(terrain, fuel_params, fmc_fields, wind_fields,
                 ignition_cells, n_steps, dt, device='cuda'):
    """
    Run complete ensemble.

    terrain: TerrainData
    fmc_fields: (N, rows, cols) — perturbed FMC per member
    wind_fields: dict with 'speed': (N, rows, cols), 'dir': (N, rows, cols)
    ignition_cells: list of (row, col) — initial fire location(s)

    Returns: EnsembleResult
    """
    N = fmc_fields.shape[0]
    rows, cols = terrain.elevation.shape

    # Initialize state
    fire_state = torch.zeros(N, rows, cols, dtype=torch.int8, device=device)
    arrival_time = torch.full((N, rows, cols), float('nan'), device=device)
    time_burning = torch.zeros(N, rows, cols, device=device)

    # Set ignition
    for r, c in ignition_cells:
        fire_state[:, r, c] = 1
        arrival_time[:, r, c] = 0.0

    # Precompute static params (on GPU)
    static = precompute_fuel_params(terrain.fuel_model, ANDERSON_13)
    static = static.to(device)
    slope = torch.tensor(terrain.slope, device=device)
    aspect = torch.tensor(terrain.aspect, device=device)

    # Move dynamic inputs to GPU
    fmc = torch.tensor(fmc_fields, device=device)
    ws = torch.tensor(wind_fields['speed'], device=device)
    wd = torch.tensor(wind_fields['dir'], device=device)

    # Time integration
    for step in range(n_steps):
        t_current = step * dt

        ros = compute_ros_batch(static, fmc, ws, wd, slope, aspect)

        fire_state, arrival_time, time_burning = step_batch(
            fire_state, arrival_time, time_burning,
            ros, wd, aspect, terrain.resolution_m, dt,
            static.residence_time, t_current
        )

    # Compute ensemble statistics
    burn_prob = (fire_state >= 1).float().mean(dim=0)        # (rows, cols)
    arrival_mean = torch.nanmean(arrival_time, dim=0)         # (rows, cols)
    arrival_var = torch.nanvar(arrival_time, dim=0)           # (rows, cols)

    return EnsembleResult(
        member_arrival_times=arrival_time.cpu().numpy(),
        burn_probability=burn_prob.cpu().numpy(),
        mean_arrival_time=arrival_mean.cpu().numpy(),
        arrival_time_variance=arrival_var.cpu().numpy()
    )
```

### Computational Cost

Per timestep per member: 8 neighbor directions × ~20 FLOPs per direction + ~50 FLOPs for ROS = ~210 FLOPs per cell.

|Grid|Members|Steps|Total FLOPs|GPU time (est.)|
|---|---|---|---|---|
|100×100|200|720 (6hr @ 30s)|300 billion|~1 sec|
|200×200|500|720|3 trillion|~5 sec|
|200×200|2000|720|12 trillion|~20 sec|
|400×400|500|720|12 trillion|~20 sec|

These are rough estimates. Actual GPU throughput depends on memory bandwidth (the stencil is memory-bound, not compute-bound). A modern GPU (RTX 3080+) should achieve the lower estimates; older hardware may be 3-5× slower.

---

## 8. Simplifications for Hackathon vs. Full Implementation

|Feature|Hackathon|Full|
|---|---|---|
|Fuel moisture classes|1-hr dead only|1-hr, 10-hr, 100-hr dead + live herb + live woody|
|Wind field|Spatially uniform per member|Spatially varying (GP field)|
|Spread shape|Isotropic (same ROS all directions)|Elliptical (directional)|
|Fuel models|Anderson 13|Scott & Burgan 40|
|Crown fire|Not modeled|Van Wagner transition model|
|Spotting|Not modeled|Stochastic ember transport|
|Fuel consumption|Instantaneous|Time-dependent based on loading|
|Terrain wind adjustment|None|Wind Adjustment Factor (WAF) for canopy sheltering|

The hackathon simplifications reduce implementation effort substantially while preserving the critical FMC sensitivity through the moisture damping η_M. The isotropic simplification loses directional spread accuracy but preserves the variance decomposition — which is what IGNIS needs.

---

## 9. Testing the Fire Engine

Before integrating with IGNIS, verify independently:

1. **Smoke test:** single member, flat terrain, uniform fuel model 1 (short grass), constant wind. Fire should spread elliptically downwind. Compare headfire ROS to BehavePlus output for same inputs.
    
2. **FMC sensitivity:** run two members identical except FMC (e.g., 5% vs 15%). Arrival times should differ dramatically. If they don't, the η_M computation is wrong.
    
3. **Terrain effect:** single member on sloped terrain, no wind. Fire should spread faster uphill. Compare with Rothermel φ_s prediction.
    
4. **Ensemble spread:** 100 members with ±20% FMC perturbation. Arrival time variance should be spatially structured — higher in cells where the fire passes through fuel with high sensitivity, lower in cells where the fire path is robust.
    
5. **Comparison with SimFire:** run the same scenario in SimFire and your implementation. Arrival time maps should be qualitatively similar. Quantitative differences are expected due to implementation details (stochastic seeding, timestep, neighbor handling).