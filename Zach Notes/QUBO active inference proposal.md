# Entropy-Guided Active Sensing for Wildfire Prediction via Quantum-Optimized Drone Placement

## Core Concept

A closed-loop system that couples ensemble wildfire prediction with information-theoretic drone routing, where the combinatorial sensor placement problem is formulated as a QUBO and solved on a quantum annealer.

The system treats wildfire prediction as an active inference problem: rather than passively ingesting available data, it identifies where prediction uncertainty is highest and most reducible, then allocates sensing resources to those locations. The drone routing optimization — selecting K measurement locations from M candidates to maximize entropy reduction — is solved as a Quadratic Unconstrained Binary Optimization problem on D-Wave hardware.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLASSICAL PIPELINE                        │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │ Data      │───▶│ Ensemble Fire │───▶│ Uncertainty       │  │
│  │ Ingestion │    │ Spread Model  │    │ Decomposition     │  │
│  │ (weather, │    │ (N members)   │    │ (variance by      │  │
│  │ fuel,     │    │               │    │  variable &       │  │
│  │ terrain)  │    │               │    │  location)        │  │
│  └──────────┘    └──────────────┘    └────────┬──────────┘  │
│                                                │             │
│                                    ┌───────────▼──────────┐  │
│                                    │ QUBO Construction    │  │
│                                    │ w_i = marginal info  │  │
│                                    │ J_ij = redundancy    │  │
│                                    └───────────┬──────────┘  │
│                                                │             │
└────────────────────────────────────────────────┼─────────────┘
                                                 │
                                    ┌────────────▼─────────────┐
                                    │   QUANTUM ANNEALER       │
                                    │   (D-Wave / sim. anneal) │
                                    │   Solve placement QUBO   │
                                    └────────────┬─────────────┘
                                                 │
┌────────────────────────────────────────────────┼─────────────┐
│                    OPERATIONAL LAYER            │             │
│                                    ┌───────────▼──────────┐  │
│  ┌──────────────┐                  │ Drone Route          │  │
│  │ Airspace      │◀────────────────│ Planning &           │  │
│  │ Coordination  │                 │ Deconfliction        │  │
│  │ (UTM layer)   │                 └───────────┬──────────┘  │
│  └──────────────┘                              │             │
│                                    ┌───────────▼──────────┐  │
│                                    │ Drone Deployment     │  │
│                                    │ & Data Collection    │  │
│                                    └───────────┬──────────┘  │
│                                                │             │
│                                    ┌───────────▼──────────┐  │
│                                    │ Data Assimilation    │  │
│                                    │ (EnKF update)        │  │
│                                    └───────────┬──────────┘  │
│                                                │             │
│                              ┌─────────────────▼──────┐     │
│                              │ Updated Ensemble ──────┼──▶ LOOP │
│                              └────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## QUBO Formulation

### Decision Variables

Binary variables **x_i ∈ {0,1}** for each candidate drone location i ∈ {1, ..., M}, where M is the set of candidate measurement points on the discretized fire domain.

### Objective Function

**maximize** H(x) = Σᵢ wᵢxᵢ + Σᵢ<ⱼ Jᵢⱼxᵢxⱼ

Subject to cardinality constraint (encoded as penalty):

**minimize** -H(x) + λ(Σᵢ xᵢ - K)²

where K is the number of available drones.

### Coefficient Construction

**Linear terms w_i** (marginal information gain at location i):

w_i = Σ_v σ²_v(i) · S_v(i)

where:

- σ²_v(i) = prior variance of state variable v at location i, computed from ensemble spread
- S_v(i) = sensitivity of fire spread prediction to variable v at location i (from ensemble-based adjoint or finite-difference sensitivity)
- v ∈ {fuel moisture content, wind speed, wind direction, fuel loading}

w_i captures: "How much does uncertainty at this location matter for predicting where the fire goes?"

**Quadratic terms J_ij** (pairwise information redundancy):

J_ij = -Σ_v ρ_v(i,j) · √(σ²_v(i) · S_v(i)) · √(σ²_v(j) · S_v(j))

where:

- ρ_v(i,j) = spatial correlation of variable v between locations i and j

J_ij is negative when measurements at i and j are redundant (correlated in the same variable that matters for prediction). This penalizes placing drones in clusters where they'd learn the same thing.

**Physical origin of the quadratic structure:** The pairwise terms arise from the spatial correlation structure of atmospheric and fuel variables. Nearby fuel moisture measurements sample from a correlated field — the second measurement adds less than the first. This is not an arbitrary encoding; it reflects the actual covariance structure of the environmental state.

### Constraint Encoding

The cardinality constraint Σ xᵢ = K is converted to the penalty term:

λ(Σᵢ xᵢ - K)² = λ[K² - 2K·Σᵢ xᵢ + (Σᵢ xᵢ)²]

Expanding:

- Adds -2λK to each wᵢ (linear shift)
- Adds 2λ to each Jᵢⱼ (quadratic shift)
- Adds λ to each diagonal (from x²ᵢ = xᵢ)

λ must be large enough to enforce feasibility but not so large that it drowns the information-gain signal. Standard practice: λ ≈ max(|wᵢ|).

## Component Specifications

### 1. Ensemble Fire Spread Model

**Inputs:** Terrain (DEM), initial fire perimeter, weather (wind, temperature, humidity), fuel map (Anderson 13 or Scott & Burgan 40 fuel models).

**Method:** N-member ensemble (N = 50–200) with perturbed initial conditions and parameters. Each member runs a Rothermel-based rate-of-spread calculation on a gridded domain. Perturbations applied to: fine dead fuel moisture (±20%), wind speed (±30%), wind direction (±15°), fuel model parameters.

**Output:** Ensemble of predicted fire perimeters at T+1h, T+2h, ..., T+6h. Per-cell probability of burning. Per-cell variance decomposition by input variable.

**Prototype simplification:** Cellular automata with Rothermel-derived transition probabilities. 100-member ensemble on a 100×100 grid. Sufficient to generate meaningful variance structure.

### 2. Uncertainty Decomposition

**Method:** Variance-based sensitivity analysis (Sobol indices or simpler ANOVA decomposition) on the ensemble output.

For each grid cell, decompose Var(fire arrival time) into contributions from each uncertain input:

Var(T_arrival) ≈ Var_FMC + Var_wind + Var_fuel + Var_interaction

**Output:** Maps of: total predictive uncertainty, fractional contribution of each measurable variable, sensitivity of spread rate to local conditions.

### 3. QUBO Construction Module

**Input:** Uncertainty maps, spatial correlation estimates (from ensemble covariance), candidate measurement locations, number of drones K.

**Processing:**

1. Compute w_i for each candidate location from variance × sensitivity product
2. Compute J_ij for each pair from correlation × geometric mean of marginal gains
3. Add penalty terms for cardinality constraint
4. Format as QUBO matrix Q where Q_ii = w_i + penalty diagonal, Q_ij = J_ij + penalty off-diagonal

**Output:** Upper-triangular QUBO matrix Q, ready for submission to D-Wave or classical solver.

### 4. Quantum/Classical Solver

**Primary:** D-Wave Advantage (5000+ qubits, Pegasus topology). Submit QUBO via Ocean SDK.

**Fallback:** Simulated annealing (Neal sampler in Ocean SDK) for comparison and when QPU access is unavailable.

**Benchmark:** Greedy submodular maximization as classical baseline. At hackathon scale (M ≤ 200 candidate locations), greedy is fast and near-optimal (1 - 1/e guarantee). The quantum advantage argument is about scaling to operational sizes (M ~ 10⁴) and real-time constraints.

### 5. Data Assimilation

**Method:** Ensemble Kalman Filter (EnKF). After drone observations are collected (or simulated), update ensemble members:

x_a = x_f + K(y - Hx_f)

where K is the Kalman gain, y is the observation vector, H is the observation operator.

**Effect:** Reduces ensemble spread in observed regions, propagates information to correlated unobserved regions, produces updated prior for next QUBO construction cycle.

### 6. Airspace Coordination Layer

The drone routing solution must be deconflicted with:

- Manned suppression aircraft (air tankers, helicopters)
- Other UAS operations (reconnaissance, mapping)
- Temporary flight restrictions (TFRs) around the fire

This layer consumes the QUBO solution (optimal measurement locations) and produces feasible flight plans that respect airspace constraints. This is the component most directly responsive to the NASA SBIR solicitation scope.

## Key Technical Claims

1. **The QUBO formulation is natural, not forced.** The quadratic structure arises from the spatial correlation of environmental variables, not from an arbitrary encoding of a non-quadratic problem.
    
2. **The active sensing loop provides measurable advantage over passive/uniform monitoring.** Targeted measurement should reduce predictive entropy faster per drone-hour than grid survey or fire-front-following strategies.
    
3. **The system produces actionable uncertainty maps, not just point predictions.** Decision-makers see where the model is confident and where it isn't — and the system is actively working to reduce the latter.
    
4. **The airspace coordination problem is intrinsic.** Dynamic drone routing in active fire airspace _is_ the multi-vehicle coordination challenge NASA is soliciting solutions for.
    

## Hackathon Deliverables

1. **Simplified fire spread simulator** with ensemble capability (cellular automata, Rothermel-derived)
2. **Uncertainty decomposition and QUBO construction pipeline**
3. **D-Wave integration** for solving placement QUBO (with simulated annealing fallback)
4. **Closed-loop demonstration** showing iterative uncertainty reduction over multiple sensing cycles
5. **Comparison** of QUBO-optimized placement vs. greedy vs. uniform baseline
6. **Visualization** of evolving uncertainty maps, drone placements, and fire predictions

## Theoretical Grounding

- **Bayesian Optimal Experimental Design** (Lindley 1956, Chaloner & Verdinelli 1995): selecting experiments to maximize expected information gain
- **Submodular Optimization** for sensor placement (Krause et al. 2008): information gain is submodular, greedy gives (1-1/e) approximation
- **Ensemble Kalman Filter** (Evensen 1994): sequential data assimilation for nonlinear geophysical systems
- **Active Inference / Predictive Processing** (Friston 2010): resource allocation driven by prediction error minimization — conceptual analog to the active sensing loop