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