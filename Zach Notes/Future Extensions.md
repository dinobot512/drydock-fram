## Part 1: Future Extensions

Extensions ordered by impact and feasibility, assuming the core system is working.

### Near-Term (hackathon day 4-5 if ahead of schedule)

**1. Streaming assimilation with myopic replanning.** Process each DroneObservation as it arrives rather than batching per cycle. After each single-observation EnKF update, recompute w_i at pending targets. If a target's value has dropped below 50% of its original, emit an updated MissionQueue. Demonstration: show a drone being redirected mid-flight because another drone's observation made its target redundant. Implementation cost: ~4 hours on top of working batch loop. High demo value.

**2. Innovation logging and model bias detection.** Track the innovation vector (y - Hx_f) at every observation location across cycles. Plot innovation mean and variance by fuel type, terrain feature, and wind regime. If innovations are consistently biased (model always overpredicts FMC on north-facing slopes), surface this as a model calibration signal. Implementation cost: ~2 hours (it's just logging and plotting). Scientifically interesting output.

**3. Drone value curve visualization.** Plot cumulative information gain vs. number of drones deployed. Show the diminishing returns curve and let a user pick the operating point. Helps answer "how many drones do I need?" without hardcoding K. Implementation cost: already implicit in QUBO solution — just need to solve for K=1,2,...,K_max and plot. ~1 hour.

### Short-Term (post-hackathon, pre-submission)

**4. Online fuel adjustment factor calibration.** Add fuel adjustment factors to the ensemble state vector. The EnKF learns per-fuel-type correction coefficients from the gap between predicted and observed fire behavior. This is the approach from the 2016-2017 FARSITE-EnKF fuel adjustment papers, applied to the CA model. Makes predictions improve over time as the system observes how this specific fire behaves in this specific landscape.

**5. Goal-oriented information gain.** Weight the QUBO objective by consequence: uncertainty near structures, evacuation routes, or crew positions matters more than uncertainty in wilderness. Requires a "value-at-risk" layer as input — which cells contain assets? The QUBO linear terms become w_i = σ²_v(i) × S_v(i) × D_v(i) × V(i), where V(i) is the asset value function. This changes which drones go where and connects the sensing system to actual fire management objectives.

**6. Real terrain integration.** Replace synthetic terrain with LANDFIRE data for a real geographic area (e.g., a historical California fire). Use actual fuel model maps, DEM, and historical weather. Run the system on a reconstructed fire scenario and compare IGNIS-guided sensing against what actually happened (satellite observations on a 4-hour cycle). This transforms the demo from "it works in simulation" to "it would have helped in a real fire."

**7. Heterogeneous fleet optimization.** Extend QUBO variables from x_i (location) to x_iv (location × measurement type). Different drones carry different payloads — some specialize in multispectral FMC, others in wind profiling. The QUBO assigns each drone type to locations where its sensor provides maximum marginal gain. Cross-variable correlation terms (from ensemble covariance) handle the interaction between FMC and wind measurements.

### Medium-Term (Phase I / research project)

**8. Path-integrated information gain.** Replace point-based QUBO with hierarchical architecture: QUBO selects target regions, classical IPP planner optimizes drone paths through those regions. Paths accumulate information continuously during transit. Transit routing prefers high-information corridors. This captures the reality that drones are continuous sensors, not point samplers.

**9. DNN surrogate fire engine.** Train a convolutional recurrent network on CA or FARSITE ensemble outputs to produce 15-minute fire state predictions in milliseconds. The surrogate replaces the CA for ensemble generation, enabling 1000-member ensembles in the time currently needed for 100. Alternatively, integrate PyTorchFire directly as the ensemble engine — it already provides GPU-accelerated differentiable CA with millisecond-level performance.

**10. Discrete event layer.** Add a binary crown fire transition model alongside the continuous CA. At each cell, estimate P(crown fire) from fuel structure, wind, and FMC. Weight QUBO terms to prioritize measurements near cells with 20-80% transition probability — the zone where a single observation has maximum binary information value. Addresses the known limitation of the Gaussian pairwise approximation for discrete regime transitions.

**11. Suppression resource allocation.** The same ensemble that drives sensing allocation can drive suppression allocation. Instead of "where should I measure to reduce prediction uncertainty," answer "where should I drop water/retardant to maximally reduce expected damage." This is a different objective function over the same fire model — expected value of intervention rather than expected information gain. Formulation as QUBO is less natural (intervention effects are nonlinear), but the ensemble infrastructure is shared.

### Long-Term (research frontier)

**12. Imitation learning for real-time replanning.** Train an RL agent (or supervised neural network) on QUBO solutions as expert demonstrations. The network learns to approximate the QUBO-optimal placement from the uncertainty map directly, bypassing the QUBO construction and solve steps. Enables sub-second replanning for streaming observations. This follows the approach of Rückin et al. (2021) — RL to approximate expensive information-theoretic planning.

**13. Multi-fire coordination.** When multiple fires are burning simultaneously (common in western US fire seasons), the system allocates a shared drone fleet across fires based on relative information gain. This is a higher-level QUBO: select which fires get how many drones, then per-fire QUBOs handle local placement. Connects to the SBIR solicitation's "concurrent operations" bullet.

**14. Fire-atmosphere coupled ensemble.** Replace the CA fire engine with WRF-SFIRE for physics-based fire-atmosphere coupling. The ensemble captures wind shifts, pyroconvection, and fire-induced weather. This extends the system's operating envelope to more complex fires but requires HPC resources. The active sensing concept is independent of the fire model — the QUBO construction depends only on the ensemble output, not on how the ensemble was generated.

**15. Closed-loop field validation.** Deploy the system on a prescribed burn with real drones. Compare IGNIS-guided sensing against human-directed sensing and uniform coverage. Measure actual prediction improvement. This is the definitive validation and the path to operational adoption.

---

## Part 2: Existing Tools and Libraries

You do not need to build everything from scratch. The following tools cover major components.

### Fire Engine

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**PyTorchFire**|GPU-accelerated differentiable CA wildfire simulator. Open source, pip installable. Millisecond-level runs. Already has perturbation and calibration support via gradient descent.|**Use this.** It's essentially your fire engine pre-built. `pip install pytorchfire`. `model = WildfireModel(); model.cuda(); model.compute()`. You'd wrap it to run N perturbed members and collect arrival times.|
|**FORFIS**|Python CA fire simulator with wind, GUI, GPL v3. Simpler than PyTorchFire but more transparent.|Good fallback if PyTorchFire has dependency issues.|
|**Cell2Fire**|C++/Python wildfire simulator, more physics-complete than simple CA. Includes fuel moisture modeling.|Heavier dependency, but more realistic. Consider for post-hackathon.|

**Recommendation:** Start with PyTorchFire. It's the fastest path to a working ensemble. If GPU isn't available, write a simple NumPy CA (100 lines) and parallelize with multiprocessing.

### Terrain and Fuel Data

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**landfire-python**|Python wrapper around LANDFIRE API. Downloads elevation, slope, aspect, fuel models as GeoTIFF with a few lines of code. 30m resolution, full US coverage. MIT license.|`pip install landfire`. 5 lines to download terrain + fuel for any bounding box. Use for real-scenario demos.|
|**rasterio**|Read GeoTIFF files into NumPy arrays.|Standard geospatial Python. `pip install rasterio`. Needed to load LANDFIRE data into your grid format.|
|**SRTM / OpenTopography**|Global DEM data if LANDFIRE API is slow or unavailable.|Alternative terrain source. Less fire-specific metadata.|

**Recommendation:** Use landfire-python to pull a real terrain tile on day 1. Fall back to synthetic terrain (random fractal DEM + random fuel assignment) if the API is down.

### QUBO Solver

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**D-Wave Ocean SDK**|Full stack: QUBO construction (dimod), embedding (minorminer), QPU submission (dwave-system), SA fallback (neal). Your EMBER work already uses this.|You already know this. `pip install dwave-ocean-sdk`. BinaryQuadraticModel from dimod, EmbeddingComposite + DWaveSampler for QPU, SimulatedAnnealingSampler from neal.|
|**PyQUBO**|Higher-level QUBO construction with constraint handling. Compiles constraint expressions to penalty terms automatically.|Alternative to manual QUBO matrix construction. Might save time on the cardinality constraint encoding. `pip install pyqubo`.|
|**EMBER (your own)**|Embedding benchmarking for the generated QUBOs.|Natural integration point. Run EMBER on the fire-derived QUBO instances to characterize embedding quality.|

**Recommendation:** Use Ocean SDK directly (you already know it). Use neal.SimulatedAnnealingSampler as primary for development; add QPU submission when the pipeline is stable.

### Data Assimilation

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**FilterPy**|EnKF implementation in Python. Well-documented, MIT license. Admits it's a "toy" for large systems but is fine for hackathon scale.|`pip install filterpy`. `from filterpy.kalman import EnsembleKalmanFilter`. Provides predict/update cycle. You'd need to define your state transition (fire model forward step) and observation operator.|
|**ensemblefilters (mchoblet)**|Multiple EnKF variants (stochastic EnKF, ETKF, ESTKF) with localization support built in. Based on Vetra-Carvalho et al. (2018) unified notation.|More sophisticated than FilterPy. Has `cov_loc.py` for distance-based localization — exactly what you need. GitHub repo with clear examples.|
|**Custom implementation**|EnKF is ~50 lines of NumPy. State = ensemble matrix, update = Kalman gain formula.|Honestly the fastest path if your state vector is simple. No library overhead. The Towards Data Science tutorial (2025) provides step-by-step Python with a toy case.|

**Recommendation:** Write your own EnKF. The core update is:

```python
def enkf_update(ensemble, observations, obs_locations, obs_noise):
    N = ensemble.shape[0]  # number of members
    X = ensemble  # (N, state_dim)
    x_mean = X.mean(axis=0)
    A = X - x_mean  # anomalies

    # Observation operator: extract state at obs locations
    HX = X[:, obs_locations]  # (N, n_obs)
    hx_mean = HX.mean(axis=0)
    HA = HX - hx_mean

    # Kalman gain
    R = np.diag(obs_noise ** 2)
    PHT = (A.T @ HA) / (N - 1)
    HPHT = (HA.T @ HA) / (N - 1) + R
    K = PHT @ np.linalg.inv(HPHT)

    # Update each member with perturbed observations
    for n in range(N):
        y_perturbed = observations + np.random.multivariate_normal(np.zeros(len(observations)), R)
        X[n] += K @ (y_perturbed - HX[n])

    return X
```

This is the entire data assimilation component. Add localization (taper K entries beyond a radius) as a refinement.

### Uncertainty Decomposition

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**SALib**|Sensitivity analysis library. Sobol indices, Morris method, ANOVA.|`pip install SALib`. Could use for formal global sensitivity analysis if you have time. Overkill for hackathon — a simple variance decomposition by parameter group is faster to implement.|
|**Custom ANOVA**|Group ensemble members by which parameter was perturbed. Between-group variance = attribution.|~20 lines of NumPy. This is what you should build.|

**Recommendation:** Custom ANOVA. SALib is designed for running new simulations to estimate sensitivity; you already have the ensemble output and just need to partition variance.

### Spatial Correlation

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**NumPy / SciPy**|`np.corrcoef` on ensemble members at candidate locations gives the spatial correlation matrix directly.|Zero additional dependencies. Extract ensemble values at M candidate locations → (N, M) matrix → `np.corrcoef` on columns → (M, M) correlation matrix.|

### Visualization

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**Matplotlib**|Fire maps, uncertainty maps, drone placement overlays, entropy reduction curves.|Standard. Sufficient for hackathon.|
|**Plotly / Dash**|Interactive dashboard if you want a live demo.|More setup but better for presentation. Consider only if Person E has bandwidth on day 5.|
|**Folium / Leaflet**|Overlay results on real maps if using LANDFIRE terrain.|Nice-to-have for real-terrain demos.|

### Path Planning

|Tool|What it gives you|Effort to integrate|
|---|---|---|
|**scipy.spatial.distance**|Distance matrices between candidate locations.|For nearest-neighbor TSP waypoint ordering.|
|**python-tsp**|Simple TSP solvers.|`pip install python-tsp`. Gives you waypoint ordering in one function call. Overkill — nearest-neighbor is fine for hackathon.|
|**Custom**|Sort selected locations by angular position from base, or nearest-neighbor chain.|10 lines. Do this.|

---

## Part 3: Dependency Stack

```
# Core
numpy
scipy
matplotlib

# Fire engine (pick one)
pytorchfire          # GPU-accelerated CA — preferred
# OR: custom CA in NumPy (no dependency)

# Terrain data
landfire             # LANDFIRE API wrapper
rasterio             # GeoTIFF reading

# QUBO
dwave-ocean-sdk      # includes dimod, neal, dwave-system, minorminer

# Optional
filterpy             # EnKF (or write your own)
pyqubo               # higher-level QUBO construction
SALib                # sensitivity analysis (probably skip)
plotly                # interactive viz (if time)
```

Install command:

```bash
pip install numpy scipy matplotlib pytorchfire landfire rasterio dwave-ocean-sdk
```

---

## Part 4: What You Must Build From Scratch

Despite the available tools, these components have no off-the-shelf solution:

1. **The QUBO construction logic** — translating uncertainty maps into w_i and J_ij coefficients with observability weighting. This is the novel contribution. ~100 lines.
    
2. **The orchestrator** — sequencing components, managing cycle state, handling replan triggers. ~200 lines.
    
3. **The uncertainty decomposition** — ANOVA on ensemble output with spatial correlation estimation at candidate locations. ~50 lines.
    
4. **The mission queue builder** — converting solver output to ranked requests with substitutes. ~80 lines.
    
5. **The comparison framework** — running all four placement strategies on the same scenario and computing PERR. ~100 lines.
    
6. **The integration glue** — data type definitions, snapshot factory, configuration. ~150 lines.
    

Total custom code estimate: ~700 lines of Python, excluding visualization. This is buildable in 5 days by 5 people.