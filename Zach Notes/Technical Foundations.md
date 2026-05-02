# IGNIS: Technical Foundations

## The Problem in One Paragraph

Wildfire spread prediction depends critically on fuel moisture content and local wind fields — variables that vary at scales of hundreds of meters but are currently observed only at stations spaced ~50 km apart. Within an active fire perimeter, in-situ observations are effectively zero. The result: models interpolate from distant stations, treating complex terrain as smooth, and produce deterministic predictions with no uncertainty quantification. Drones can observe fuel moisture and wind at the resolution models need, but current drone operations survey uniformly or track the fire front — with no principled method for deciding where to measure. IGNIS answers that question: given what the model already knows, where would a new measurement most reduce uncertainty about where the fire will go?

---

## Part 1: Quantifying What We Don't Know

### Gaussian Process Prior

Before any drone flies, we need a map of how uncertain we are about fuel moisture (and wind) at every point in the landscape. This is a spatial estimation problem with a closed-form solution from geostatistics.

We model fuel moisture content as a Gaussian process (GP) — a spatial field where the value at any point is a random variable, and any collection of points follows a multivariate normal distribution. The correlation between two points is governed by a kernel function k(x, x') that encodes how similarity decays with distance and terrain difference.

Given observations **y** at RAWS station locations **X**_obs, the posterior mean and variance at any unobserved location x* are:

$$\mu(x^_) = \mathbf{k}(x^_, \mathbf{X}_{obs}) \left[\mathbf{K}(\mathbf{X}_{obs}, \mathbf{X}_{obs}) + \sigma_n^2 \mathbf{I}\right]^{-1} \mathbf{y}$$

$$\sigma^2(x^_) = k(x^_, x^_) - \mathbf{k}(x^_, \mathbf{X}_{obs}) \left[\mathbf{K}(\mathbf{X}_{obs}, \mathbf{X}_{obs}) + \sigma_n^2 \mathbf{I}\right]^{-1} \mathbf{k}(\mathbf{X}_{obs}, x^*)$$

Here **k**(x*, **X**_obs) is the vector of covariances between the prediction point and each station, **K**(**X**_obs, **X**_obs) is the covariance matrix among stations, and σ²_n is observation noise.

The posterior variance σ²(x*) depends only on the geometry of observations and the covariance structure — not on the observed values. This is the key property: we can map where we are uncertain before seeing any fire. Near a RAWS station, σ² approaches σ²_n (measurement noise). Far from all stations, σ² approaches the prior variance. Between stations, the reduction depends on how much independent information each station provides about x*.

This gives us a spatially varying uncertainty field for each variable: σ²_fmc(x), σ²_wind(x). These fields are high where observations are sparse (far from RAWS, complex terrain) and low where observations constrain the estimate.

### Why This Matters for Fire Prediction

Knowing that FMC is uncertain at a point is necessary but not sufficient. We need to know whether that uncertainty _matters_ — whether a measurement there would change the predicted fire trajectory. A cell with highly uncertain FMC in a lake bed is irrelevant. A cell with moderately uncertain FMC directly in the fire's predicted path is critical.

This requires coupling the spatial uncertainty with a fire spread model.

---

## Part 2: Propagating Uncertainty Through Fire Prediction

### Ensemble Fire Simulation

We run the fire model not once but N times (N = 200–1,000), each time with slightly different inputs drawn from the GP posterior. These perturbations are not arbitrary — they are spatially correlated random fields scaled by the GP uncertainty at each location.

For ensemble member n, the fuel moisture field is:

$$\text{FMC}_n(x) = \mu_{fmc}(x) + \delta_n(x)$$

where δ_n is drawn from a Gaussian process with zero mean and covariance proportional to σ²_fmc(x). This means cells where FMC is well-known (near RAWS) get small perturbations, and cells where FMC is poorly known get large perturbations. Crucially, the perturbations are spatially correlated — adjacent cells on the same slope get similar perturbations, reflecting the physical reality that FMC varies smoothly within similar terrain.

Each member runs a fire spread simulation using the Rothermel rate-of-spread equation:

$$R = \frac{I_R , \xi , (1 + \phi_w + \phi_s)}{\rho_b , \varepsilon , Q_{ig}}$$

where I_R is reaction intensity (from fuel properties), ξ is the propagating flux ratio, φ_w and φ_s are wind and slope factors, ρ_b is bulk density, ε is the effective heating number, and Q_ig = 250 + 1116 × FMC is the heat of preignition. The critical dependence on FMC enters through Q_ig — higher moisture requires more energy to ignite, reducing spread rate. This sensitivity is extreme: Jolly (2007) showed a 10% change in FMC can produce up to 1,200% change in predicted rate of spread.

The Rothermel equation computes rate of spread per cell. We propagate fire across the grid using cellular automata: each cell's ignition probability depends on its neighbors' fire state, the local ROS, and the time step. After running all N members forward for T hours, we have N different fire arrival time maps.

### What the Ensemble Tells Us

At each grid cell c, the N arrival times form a distribution. Their spread IS the prediction uncertainty at that cell:

$$\text{Var}(T_{arrival}(c)) = \frac{1}{N-1} \sum_{n=1}^{N} \left(T^{(n)}_{arrival}(c) - \bar{T}_{arrival}(c)\right)^2$$

Cells where all members agree (fire arrives at the same time regardless of perturbation) have low variance — the prediction there is robust. Cells where members disagree have high variance — the prediction is sensitive to the uncertain inputs.

But total variance alone doesn't tell us _which_ variable to measure. For that we need variance decomposition.

### Variance Attribution

We decompose the prediction variance at each cell into contributions from each uncertain input variable. The method: compute the correlation between each member's arrival time at cell c and that member's input perturbation for variable v.

The sensitivity of fire arrival time at cell c to variable v is:

$$S_v(c) = \text{Corr}\left(T_{arrival}^{(1..N)}(c), , \delta_v^{(1..N)}\right)$$

The variance attributable to variable v at cell c is then:

$$\sigma^2_v(c) = S_v(c)^2 \times \text{Var}(\delta_v) \times \text{Var}(T_{arrival}(c))$$

This gives us, at every cell, a breakdown: "62% of the arrival time uncertainty here is due to FMC uncertainty, 31% to wind speed uncertainty, 7% to wind direction uncertainty."

The precision of this attribution depends on the ensemble size. Each sensitivity estimate S_v(c) is a sample correlation from N points, with standard error ~1/√N. With N=200, a true correlation of 0.3 is estimated with ±0.07 uncertainty. With N=1,000, the estimate tightens to ±0.03. This is why larger ensembles improve QUBO quality: the coefficients being optimized are more precisely estimated.

---

## Part 3: Deciding Where to Measure

### The Information Value of a Measurement

At each candidate drone measurement location i, we can now compute how much a measurement there would reduce prediction uncertainty. This is the information value:

$$w_i = \sum_{v} \sigma^2_v(i) \times S_v(i) \times D_v(i)$$

where:

- σ²_v(i) is the GP prior variance of variable v at location i (how uncertain we are)
- S_v(i) is the sensitivity of fire prediction to variable v at location i (how much it matters)
- D_v(i) is the drone's ability to measure variable v at location i (can the sensor actually observe this?)

w_i integrates three questions: _Is this variable unknown here?_ × _Does it matter for fire prediction?_ × _Can we measure it?_ A location scores high only if all three answers are yes.

### The Redundancy Between Measurements

If we send two drones to nearby locations with the same fuel type and aspect, the second measurement adds little — the first already told us what FMC is in that terrain class. The GP covariance structure quantifies this redundancy directly.

The spatial correlation between candidate locations i and j for variable v is:

$$\rho_v(i,j) = \text{Corr}\left(\delta_v^{(1..N)}(i), , \delta_v^{(1..N)}(j)\right)$$

computed from the ensemble: across the N members, how correlated are the perturbations of variable v between these two locations? High correlation means high redundancy — measuring both adds little over measuring one.

The pairwise redundancy term is:

$$J_{ij} = -\sum_{v} \rho_v(i,j) \times \sqrt{w_i \cdot w_j}$$

J_ij is negative when measurements are redundant (high spatial correlation in variables that matter). It is near zero when measurements are complementary — either because they're spatially distant, or because different variables dominate the uncertainty at each location (one measures FMC-driven uncertainty, the other wind-driven uncertainty).

This pairwise structure arises from the physics of spatial correlation, not from a mathematical convenience. Adjacent fuel moisture measurements sample from a correlated field — the correlation IS the redundancy.

### Formulation as Quadratic Optimization

We want to select K locations from M candidates to maximize total information gain while minimizing redundancy. Define binary variables x_i ∈ {0,1} (send a drone to location i or not). The objective is:

$$\text{maximize} \quad H(\mathbf{x}) = \sum_{i} w_i , x_i + \sum_{i<j} J_{ij} , x_i , x_j$$

subject to the constraint that exactly K locations are selected: ∑ x_i = K.

This is a Quadratic Unconstrained Binary Optimization (QUBO) problem. The cardinality constraint is absorbed into the objective as a penalty term:

$$\text{minimize} \quad -H(\mathbf{x}) + \lambda\left(\sum_i x_i - K\right)^2$$

The penalty weight λ ≈ max(|w_i|) ensures feasibility without drowning the information-gain signal.

The resulting QUBO matrix Q has entries:

- Q_ii = -w_i + λ (diagonal: marginal value minus penalty)
- Q_ij = -J_ij + 2λ for i ≠ j (off-diagonal: redundancy plus penalty coupling)

### Why QUBO / Why Quantum Annealing

The QUBO is NP-hard in general, but the specific structure — clustered high-value regions with internal redundancy, complementary pairs across different terrain — is well-suited to annealing. Quantum annealers (D-Wave) solve QUBO by exploiting quantum tunneling to escape local minima in the energy landscape. At hackathon scale (M ≤ 300), classical solvers (simulated annealing, greedy) find near-optimal solutions quickly. The quantum advantage argument is about scaling: at operational sizes (M ~ 10,000 candidates, K ~ 50 drones), greedy requires O(MK) evaluations while the QUBO enables flat submission to the QPU.

The greedy alternative exploits a separate theoretical guarantee: mutual information over Gaussian processes is submodular (Krause et al. 2008), meaning the greedy algorithm — iteratively selecting the highest marginal-gain location — achieves at least 63% of optimal (the (1-1/e) bound). This provides a strong classical baseline and theoretical lower bound on achievable performance.

---

## Part 4: Collecting Data and Closing the Loop

### From Locations to Paths

The QUBO selects K high-value target regions. A path planner converts these into feasible drone flight plans. Because drones collect data continuously along their trajectory (a multispectral camera observes every cell it overflies, crossing a new 50m cell every ~3 seconds at 15 m/s cruise speed), a single 20-minute sortie generates observations over ~1,000 cells — not a single point.

The path planner optimizes the route through selected regions to maximize unique cell coverage, preferring paths that cross terrain boundaries (ridgelines, fuel type transitions) where the GP correlation breaks and each new cell provides non-redundant information.

### Data Assimilation: Updating What We Know

When observations arrive, we update the model state using the Ensemble Kalman Filter (EnKF). The EnKF is the standard method for assimilating observations into ensemble-based predictions in geophysical systems.

For each ensemble member n, the update is:

$$\mathbf{x}_a^{(n)} = \mathbf{x}_f^{(n)} + \mathbf{K}\left(\mathbf{y} + \boldsymbol{\varepsilon}^{(n)} - \mathbf{H}\mathbf{x}_f^{(n)}\right)$$

where:

- x_f^(n) is the forecast state of member n (FMC field, wind field)
- y is the observation vector (drone measurements)
- H is the observation operator (extracts model state at observation locations)
- ε^(n) is perturbed observation noise (stochastic EnKF)
- K is the Kalman gain matrix

The Kalman gain balances trust in the model versus trust in the observations:

$$\mathbf{K} = \mathbf{P}_f \mathbf{H}^T \left(\mathbf{H}\mathbf{P}_f\mathbf{H}^T + \mathbf{R}\right)^{-1}$$

P_f is the forecast error covariance (estimated from the ensemble spread) and R is the observation error covariance (measurement noise from the drone sensors).

The key property: the EnKF doesn't just update the observed cells. The ensemble covariance P_f encodes which unobserved cells covary with the observed ones. If cell (50, 73) and cell (52, 75) consistently covary across ensemble members (because they share terrain features), observing (50, 73) updates (52, 75) proportionally. Information propagates through covariance structure, not through spatial proximity. Two cells on the same slope 2 km apart may be more tightly coupled than two cells 200m apart on opposite sides of a ridge.

Localization prevents spurious long-range updates that arise from finite ensemble size. The Kalman gain is tapered to zero beyond a physical correlation radius using a Gaspari-Cohn function, ensuring that observations only influence cells within a physically plausible range.

### The GP Also Updates

Independently of the EnKF, the GP prior can be updated by adding the drone observation to the conditioning set. This is computationally trivial — it adds one row and column to the GP's covariance matrix. The posterior uncertainty field σ²(x) drops near the observation and is unchanged far away. This updated GP uncertainty feeds the next cycle's ensemble perturbation generation, ensuring that future perturbations reflect what's now known.

### Closing the Loop

After assimilation:

1. The GP has updated uncertainty fields reflecting new observations
2. The ensemble has updated state fields reflecting assimilated data
3. Both feed back into the fire engine for the next prediction cycle

The next ensemble uses tighter perturbations where drones observed (lower GP uncertainty) and maintains wide perturbations where they didn't. The fire prediction's variance map changes — some regions are now well-constrained, others remain uncertain. The QUBO for the next cycle produces different drone targets, directing sensing to the remaining high-uncertainty, high-sensitivity regions.

Over successive cycles, the system progressively reduces prediction uncertainty in the regions that matter most for fire trajectory forecasting.

---

## Part 5: How Everything Connects

```
RAWS stations + terrain data
        │
        ▼
    Gaussian Process
    Compute prior uncertainty σ²(x) for FMC, wind
    at every grid cell from observation geometry
        │
        ▼
    Ensemble Generation
    Draw N spatially correlated perturbation fields
    scaled by GP uncertainty at each cell
        │
        ▼
    Ensemble Fire Simulation
    Run N Rothermel CA members forward T hours
    Each member uses different (FMC, wind) fields
        │
        ▼
    Variance Decomposition
    Per cell: total prediction variance + attribution
    to each input variable via ensemble correlations
        │
        ▼
    QUBO Construction
    w_i = σ²_v × sensitivity × observability (linear)
    J_ij = -spatial correlation × √(w_i·w_j)  (quadratic)
    Constraint: exactly K drones
        │
        ▼
    QUBO Solve (D-Wave / SA / greedy)
    Select K measurement regions
        │
        ▼
    Path Planning + Drone Deployment
    Route drones through selected regions
    Collect swath observations along path
        │
        ▼
    Data Assimilation (EnKF)
    Update ensemble state using observations
    Covariance propagates info to unobserved cells
        │
        ▼
    Update GP with new observation points
    σ² drops near observed locations
        │
        ▼
    RETURN TO ENSEMBLE GENERATION
    Next cycle uses tighter perturbations where
    observed, wide perturbations where not
```

Each component has established mathematical foundations:

- GP regression: Matheron (1963), Rasmussen & Williams (2006)
- Ensemble Kalman filter: Evensen (1994)
- Rothermel fire spread: Rothermel (1972), Andrews (2018)
- Submodular sensor placement: Krause, Singh & Guestrin (2008)
- QUBO for sensor placement: Nakano & Uno (2024)
- Bayesian optimal experimental design: Lindley (1956), Chaloner & Verdinelli (1995)

The novel contribution is their integration into a closed loop where fire prediction uncertainty drives targeted data collection, and targeted data collection reduces fire prediction uncertainty. No existing system connects these components.

---

## Part 6: What We Test

The central empirical question: does information-theoretic targeting outperform naive strategies?

We compare four drone placement strategies across multiple sensing cycles on the same fire scenario:

1. **QUBO-optimized:** placement selected by solving the information-gain QUBO
2. **Greedy submodular:** iteratively select the highest marginal-gain location (theoretical baseline with 63% optimality guarantee)
3. **Uniform grid:** place drones on a regular spatial grid (the naive "cover everything" approach)
4. **Fire-front following:** place drones along the predicted fire perimeter (the current operational heuristic)

The primary metric is Predictive Entropy Reduction Rate: the decrease in fire arrival time variance per drone per unit flight time. If QUBO-optimized placement consistently reduces entropy faster than uniform placement across scenarios, the information-theoretic approach is justified.

A secondary test: does a simpler fire model with QUBO-targeted data collection outpredict a more accurate fire model with only RAWS data? If yes, the field is data-limited, not model-limited — which validates the entire premise.