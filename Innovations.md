**Spatial estimation:**

- Terrain-aware Matérn 3/2 GP kernel (geostatistics) — distance augmented by elevation + aspect to model microclimate correlation
- Nelson dead fuel moisture model (fire science) — physics-based prior mean the GP corrects around
- Regression kriging (geostatistics) — GP fits residuals to Nelson, not raw FMC
- Temporal decay calibrated to fuel timelags (fire weather science) — observation sigma inflation at physically derived rates

**Uncertainty quantification:**

- Ensemble fire simulation with GP-scaled perturbations (numerical weather prediction) — members diverge proportionally to local data scarcity
- Global sensitivity via ensemble correlation (sensitivity analysis) — measures downstream fire trajectory impact, not local self-referencing
- Binary entropy for regime transitions (information theory) — captures discrete crown fire / burn-no-burn uncertainty the Gaussian framework misses
- Per-member fire state persistence (particle filtering) — ensemble carries joint distribution over environment AND fire location

**Targeting:**

- Information field: variance × sensitivity × observability (Bayesian experimental design) — three fields from three disciplines multiplied into one drone routing signal
- Submodular greedy with GP conditional variance (machine learning) — near-optimal sensor placement with (1-1/e) guarantee
- Prognostic vs diagnostic sensing distinction (original) — measure conditions ahead of fire, not the fire itself
- QUBO formulation with physically-derived quadratic terms (quantum computing) — spatial correlation creates natural quadratic redundancy structure

**Path planning:**

- Felzenszwalb segmentation on terrain features (computer vision) — reduces grid to correlation domains matching GP kernel structure
- Sequential GP conditional variance path scoring (informative path planning / robotics) — exact non-redundant information integral along drone trajectory
- Range + depot constrained orienteering (operations research) — greedy path maximizes info/meter while guaranteeing return to base
- Multi-drone redundancy avoidance via sequential GP update (multi-agent planning) — each drone's plan accounts for what previous drones will observe

**Data assimilation:**

- EnKF with localization and inflation (numerical weather prediction) — spatial information propagation with ensemble stability
- Particle filter for binary fire observations (sequential Monte Carlo) — reweights members rather than averaging across modes
- Consistency checker with hard reset (data assimilation) — reconstructs fire state via fast marching when ensemble drifts from observations
- Multi-modal observation interface (software engineering) — every sensor type implements one ABC, GP sees only DataPoints

**Fire simulation:**

- GPU-batched Rothermel + Van Wagner + level-set (computational physics) — full FARSITE physics stack parallelized across ensemble members
- CFL-adaptive timestepping (numerical methods) — stable under extreme ROS without wasting compute on slow cells
- Correlated perturbation fields via circulant embedding / FFT (stochastic simulation) — spatially smooth ensemble diversity in O(D log D)

**System architecture:**

- Closed-loop active inference (computational neuroscience / Friston) — predict → uncertainty → sense → update → repeat
- Observation store with temporal decay + cycle locking (systems engineering) — thread-safe real-time data management
- Dynamic prior separated from observations (Bayesian methodology) — model-derived baseline vs sensor-derived corrections, cleanly decoupled
- Oracle-free fire state estimation (original) — system bootstraps from single satellite pixel, no ground truth ever enters the model





# BASED ON SECTION:
**Load terrain, weather and satellite data**

Mathematical: Regression kriging — the Nelson dead fuel moisture model provides a physics-informed spatial FMC estimate at every cell (not just interpolation from sparse stations). The GP fits corrections to Nelson rather than fitting raw FMC. This means the prior already knows south-facing slopes are drier before any drone flies. Standard geostatistics, never applied to wildfire drone planning.

Engineering: Multi-modal data fusion at ingestion. Every data source (LANDFIRE 30m terrain, RAWS point weather, GOES 2km fire detection, VIIRS 375m fire detection, HRRR 3km wind forecast) enters through a unified observation interface. Each observation type defines its own spatial footprint, measurement noise, and decay behavior. A 2km GOES pixel automatically emits thinned DataPoints across its footprint with degraded confidence at the edges. The system doesn't distinguish data sources downstream — the GP sees DataPoints with locations and sigmas.

**Generate initial estimate (prior)**

Mathematical: Terrain-aware Matérn 3/2 kernel where distance is augmented by elevation difference and aspect difference. Two cells 500m apart on opposite sides of a ridge are treated as further apart than two cells 500m apart on the same slope. The kernel encodes the physical reality that terrain features break FMC correlation. This is the same feature space used for the Felzenszwalb domain segmentation — one consistent definition of "similarity" throughout the system.

Mathematical: Temporal decay calibrated to fuel physics timelags. Observation sigma inflates by exp(age/tau) where tau comes from the Nelson timelag classification (1 hour for fine dead fuel, 2 hours for wind speed, 1 hour for wind direction). These aren't tuned parameters — they're published physical constants of the fuel classes. The GP automatically deprioritizes stale observations and the information field automatically re-routes drones to re-measure areas where observations have aged out.

Engineering: Separation of static prior (LANDFIRE terrain, loaded once), dynamic prior (Nelson FMC recomputed each cycle from current weather, HRRR wind field updated on forecast arrival), and observations (drone/satellite data accumulating with decay). The GP consumes all three but they're managed independently.

**Identify uncertain and sensitive regions**

Mathematical: Global sensitivity — the correlation between local FMC perturbation and total weighted fire impact across the entire domain, not just local arrival time at that cell. This captures terrain chokepoints where one cell's FMC determines whether fire reaches an entire valley. Local sensitivity misses these bottleneck effects. The computation is one matrix-vector multiply across the ensemble — same cost as local sensitivity, fundamentally different answer.

Mathematical: Binary entropy augmentation for discrete regime transitions. Cells where the ensemble disagrees about burn/no-burn or surface/crown fire transition get an additional information term derived from binary entropy H(p) = -p log p - (1-p) log(1-p). This captures the information value of measurements that resolve yes/no questions rather than narrowing continuous estimates. Normalized against the continuous variance term so neither dominates.

Mathematical: Three-variable information field combining FMC uncertainty, wind speed uncertainty, and wind direction uncertainty, each weighted by its own global sensitivity and observability. Wind direction is arguably the most important variable for fire trajectory (determines WHERE fire goes, not just how fast) and was missing from initial implementations. The multiplicative structure w = variance × sensitivity × observability means a cell only gets high information value if it's uncertain AND that uncertainty matters AND a drone can measure it. Any zero factor kills the value.

Engineering: Bimodal detection separates the unimodal regime (Gaussian variance decomposition works well) from the bimodal regime (burn/no-burn disagreement, crown fire transition uncertainty) and applies different mathematical treatments. The standard EnKF handles unimodal cells. A particle filter handles bimodal cells by reweighting members rather than averaging across modes.

**Optimize drone paths**

Mathematical: Correlation-domain graph reduction via Felzenszwalb segmentation. The full 40,000-cell grid is reduced to ~400 terrain-adaptive domains where domain boundaries follow ridgelines, fuel type transitions, and aspect changes. The segmentation uses the same multi-channel feature space (elevation, slope, aspect, fuel model, canopy cover) as the GP kernel, guaranteeing that domains align with the GP's correlation structure. Path optimization on 400 nodes is tractable; on 40,000 cells it's not.

Mathematical: Sequential GP conditional variance for exact path scoring. Each cell the drone overflies is scored for its marginal non-redundant information conditioned on every cell previously observed along the path. This is a discrete path integral where the integrand changes at each step because previous observations reduce variance at upcoming cells. Two cells on the same slope provide redundant information — the sequential update captures this exactly, not through a heuristic discount. Cost: ~10ms per path evaluation because each GP update is one vectorized subtraction.

Engineering: Range and depot constraints in the path planner. Every candidate path is checked against drone endurance and guaranteed ability to reach a ground station. Precomputed Dijkstra return costs from every domain to every station ensure the drone can always get home. The greedy path selector maximizes information per meter of travel while respecting physical constraints — no path is planned that strands a drone.

Engineering: Multi-drone sequential allocation with inter-drone redundancy avoidance. After planning drone 1's path, the GP variance is updated to reflect what drone 1 will observe. Drone 2's path planning operates on the residual uncertainty. Drone 2 automatically avoids drone 1's coverage because the GP variance there has already dropped.

**Reroute drones**

Mathematical: The system answers "should we hard-reset or continue?" each cycle using a consistency checker that compares new fire observations against ensemble consensus. If >20% of satellite/thermal detections disagree with the ensemble prediction, the fire state has drifted — trigger a full arrival time reconstruction from observations using fast marching with Rothermel ROS, then reinitialize the ensemble around the reconstruction. If disagreement is <20%, apply particle filter reweighting to gently correct without discarding ensemble diversity. The threshold controls the tradeoff between correction aggressiveness and ensemble stability.

Mathematical: Fire state estimation without oracle. The system starts from a single coarse satellite detection (GOES 2km pixel) and progressively sharpens fire location through drone thermal observations and ensemble forward propagation. No ground truth is ever passed to the model. The fire location emerges from Bayesian inference on observations. Each ensemble member carries its own fire state forward between cycles — members disagree about where the fire is, and that disagreement drives drones to confirm the perimeter at strategically important locations.

Engineering: Per-member fire state persistence across cycles. Each ensemble member carries its fire arrival time field forward — member 47's fire advances from where member 47's fire was last cycle, not from a shared consensus perimeter. The ensemble is a joint distribution over environmental parameters AND fire state simultaneously. Fire observations select members (particle filter), FMC/wind observations update fields (EnKF). Both mechanisms operate on the same ensemble.

**Collect observations and assimilate**

Mathematical: EnKF with localization and inflation on a joint state vector. The ensemble state includes FMC, wind speed, and wind direction at every cell. The Kalman gain propagates information spatially — observing FMC at cell A reduces FMC uncertainty at correlated cells within the localization radius. Because the ensemble's fire trajectories are coupled to the environmental fields, a fire perimeter observation implicitly constrains FMC and wind estimates (members consistent with the observed perimeter had specific FMC/wind values that produced that trajectory). The cross-variable covariance is captured automatically by the ensemble.

Mathematical: Multiplicative covariance inflation after each EnKF update prevents ensemble collapse. Without it, the ensemble variance shrinks to zero after 3-4 cycles and the information field goes dark. The inflation factor (1.02-1.10) works in tandem with temporal decay — inflation prevents intra-cycle collapse, temporal decay on observations prevents inter-cycle collapse by allowing variance to regrow as old measurements lose weight.

Engineering: Observation interface polymorphism. Every observation type (RAWS, drone multispectral, drone anemometer, drone thermal, GOES, VIIRS, satellite FMC) implements the same Observation ABC. Each converts itself to DataPoints with appropriate decay, footprint expansion, and confidence degradation. The GP and EnKF consume DataPoints without knowing what sensor produced them. Adding a new sensor type (LiDAR fuel structure, gas detection) means implementing one class — nothing else in the pipeline changes.

Engineering: Observation store with cycle locking. External data sources (drone telemetry, satellite passes) push to an ingestion buffer. The orchestrator locks the store during cycle computation, preventing mid-cycle state mutation. After unlock, the buffer flushes. Pruning removes observations that have decayed beyond usefulness. Time-parameterized queries allow historical probing without mutating stored data.