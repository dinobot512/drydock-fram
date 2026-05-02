## 1. Wildfire Spread Modeling: State of the Art and Limitations

### 1.1 The Rothermel Model and Its Descendants

The foundational operational fire spread model remains Rothermel (1972), a quasi-empirical model computing steady-state rate of spread and intensity from fuel, weather, and terrain inputs. Fifty years later, it remains embedded in all major US operational systems — BEHAVE, FARSITE, FlamMap, BehavePlus — and is the global default for fire behavior prediction (USFS Fire Sciences Lab, 2022).

The model's known limitations are well-documented. It assumes steady-state spread through homogeneous fuel beds with constant wind, simplifying spatial heterogeneity into discrete fuel model categories (originally Anderson's 13, later expanded to Scott & Burgan's 40). A 2023 study examining the Rothermel model in Karst ecosystems found relative prediction errors as high as 50% when applied outside its calibration range (Forests, 2023). Critically, Cruz & Alexander (2013) and subsequent validation studies have shown systematic underprediction of rate of spread in high-intensity fires — precisely the conditions where prediction matters most.

The most significant structural deficiency, identified by multiple authors (Sullivan 2009; Mandel et al. 2009; Coen et al. 2013), is the simplistic treatment of wind. Operational models take wind as an external input and do not represent the fire-atmosphere feedback loop. This means they cannot capture fire-induced winds, pyroconvection, or the plume-dominated behavior that characterizes extreme fires. Technosylva's 2023 California validation study confirmed that prediction accuracy degrades systematically under high wind speeds and low fuel moisture — the conditions of greatest operational concern.

### 1.2 Coupled Fire-Atmosphere Models

The gap between semi-empirical and physics-based approaches is addressed by coupled models, primarily WRF-SFIRE (Mandel et al. 2011) and FIRETEC (Linn et al. 2002). WRF-SFIRE couples the Weather Research and Forecasting mesoscale atmospheric model with a level-set fire spread implementation, allowing two-way fire-atmosphere interaction: weather drives fire behavior, and fire heat/moisture fluxes perturb the atmosphere. Similar models include MesoNH-ForeFire (Filippi et al. 2011) and CAWFE (Clark et al. 2004), from which WRF-SFIRE evolved.

These models capture phenomena invisible to Rothermel-based systems — fire-induced circulations, erratic wind shifts, and convective column dynamics. However, they are computationally expensive (requiring HPC resources), sensitive to initial conditions, and not currently operational for real-time forecasting. Ciri et al. (2021) performed uncertainty quantification on coupled fire-atmosphere simulations and found that atmospheric grid resolution is the primary source of forecast error, with the forecast time horizon becoming dominant during the strongly coupled initial fire development phase. This creates an inherent tension: the resolution needed for accurate fire-atmosphere coupling is computationally prohibitive for ensemble methods.

### 1.3 The Uncertainty Quantification Gap

A critical gap in the field is the absence of calibrated uncertainty quantification in operational systems. Current tools produce deterministic outputs — a single predicted fire perimeter — despite massive uncertainty in inputs. The few studies addressing this gap reveal the scale of the problem:

Ujjwal et al. (2020, 2021) demonstrated that ensemble fire simulations can produce probabilistic burn maps, but noted the computational expense of running sufficient ensemble members. Grieshop & Wikle (2023) proposed a Bayesian stochastic cellular automata framework with formal uncertainty quantification, showing that the Bayesian construction enables meaningful posterior uncertainty estimates — but applied it only to controlled burns, not operational wildfires. Chakravarty (2025) performed the first systematic spatial analysis of ML-based wildfire forecast uncertainty, finding that high-uncertainty regions form coherent 20-60 meter buffer zones around predicted firelines. This spatial structure in uncertainty is exactly what an active sensing system could exploit.

Global sensitivity analysis of fire spread models (Ujjwal et al. 2021) establishes that relative humidity (via fuel moisture) is consistently the highest-influence parameter, with wind speed second. Temperature contributes least. This ranking directly informs which variables an active sensing system should prioritize measuring.

A neural emulator approach (2023) noted that ensemble-based uncertainty quantification is desirable but that the parameter space grows exponentially with the number of uncertain variables, motivating surrogate model approaches. A diffusion-model-based surrogate (2025) demonstrated that probabilistic ensemble generation via generative models can capture distributional characteristics of fire spread more effectively than deterministic methods.

The overarching finding: **the field knows uncertainty quantification is essential for operational decision-making, but current operational systems do not provide it, and research systems that do are not computationally tractable for real-time use.**

---

## 2. Fuel Moisture: The Critical Measurement Gap

### 2.1 Sensitivity and Importance

Fuel moisture content — both live (LFMC) and dead (DFMC) — is the single most influential variable in fire behavior prediction. Jolly (2007) demonstrated that a 10% difference in LFMC can produce up to a 1200% difference in predicted rate of spread in the Rothermel model. This extreme sensitivity means that fuel moisture measurement errors propagate and amplify through the entire prediction pipeline.

### 2.2 Current Measurement Methods and Their Limitations

**Field sampling:** The only direct measurement of FMC is destructive gravimetric sampling — collecting vegetation, weighing it wet and dry. This is locally accurate but costly, slow, and impossible to scale spatially (Lawson & Hawkes 1989; Yebra et al. 2013).

**Remote Automated Weather Stations (RAWS):** Operational DFMC estimation relies on the Nelson model applied to weather observations from RAWS stations. However, RAWS are sparsely distributed, and FMC is interpolated between stations using simple spatial methods. Vejmelka, Kochanski & Mandel (2013) directly addressed this gap in WRF-SFIRE, developing a trend surface model to estimate fuel moisture fields from sparse RAWS observations combined with Kalman filtering — but noted that the spatial interpolation introduces significant uncertainty between stations.

**Satellite remote sensing:** Multiple satellite-based approaches exist for FMC estimation. MODIS and VIIRS reflectance bands have been used for DFMC estimation (Dragozi et al.; VIIRS-based ML approaches in 2023). For LFMC, Rao et al. (2020) developed a physics-assisted RNN model at 250m resolution using Sentinel-1 and Landsat-8. More recent work (2025) has pushed to 10m resolution using pretrained remote sensing foundation models (Galileo). The SMAP satellite's microwave observations have been used to derive vegetation water content as a proxy for live fuel moisture (Cho et al. 2025).

**The persistent gap:** Despite advances, remote sensing of FMC remains insufficiently accurate and temporally resolved for operational fire behavior prediction. Yebra et al. (2013) conducted a comprehensive global review and found that while satellite approaches have addressed many constraints, significant challenges remain in temporal frequency, spatial resolution, and validation across vegetation types. The fundamental problem is that fire behavior models need FMC at scales of tens of meters and update frequencies of hours, while satellite products provide data at 250m-33km resolution with revisit times of days.

**This measurement gap is precisely what targeted drone-based sensing could address.** Drones can measure fuel moisture proxies (thermal imagery correlated with moisture status, multispectral indices) at the spatial and temporal resolution fire models actually need — but only if deployed to locations where the measurement matters most for prediction.

---

## 3. Data Assimilation for Wildfire

### 3.1 Ensemble Kalman Filter Approaches

The application of EnKF to wildfire prediction was pioneered by Mandel et al. (2007, 2009), who demonstrated that ensemble Kalman filters could modify running fire simulations to track observations even when started with erroneous ignition locations. This work appears to be the first wildland fire model with data assimilation.

Subsequent developments include:

- **FARSITE-EnKF integration** (2016, 2017): Extended FARSITE with data assimilation for fire perimeters and fuel adjustment factors, demonstrated on the 2014 Cocos fire. Showed that assimilating limited spatial resolution perimeter observations meaningfully improved predictions.
- **Polyline simplification for rapid DA** (Yoo et al. 2023): Introduced computational acceleration of the EnKF by representing fire perimeters as simplified polylines, addressing the computational bottleneck of running ensemble methods with complex fire simulators.
- **Front-tracking with EnKF** (Rochoux et al. 2015): Implemented EnKF for a front-tracking fire simulator, finding that the assimilation window size must be matched to the temporal variability of environmental conditions — too large a window fails to track sudden changes in fire behavior.

### 3.2 Data Assimilation in Coupled Models

Mandel's group has extended data assimilation to coupled fire-atmosphere models (WRF-SFIRE), addressing a unique challenge: when the fire model state is changed by data assimilation, the fire and atmosphere are no longer compatible. Their solution uses fire arrival time as the state representation and replays fire history to spin up compatible atmospheric states (Mandel et al. 2012, 2014).

Recent work has applied generative models (conditional WGANs) to infer fire arrival times from satellite active fire detections, trained on WRF-SFIRE simulations (2023, 2025). This provides a learned surrogate for the data assimilation inverse problem, potentially enabling faster state estimation.

Mandel et al. (2023) have also explored replacing the Kalman filter's fuel moisture model with recurrent neural networks, seeking to improve both the accuracy of the FMC model and the data assimilation quality.

### 3.3 The Missing Piece: Active Data Collection

All existing data assimilation work for wildfire is **passive** — it assimilates whatever observations happen to be available (satellite overpasses, RAWS stations, occasional aerial reconnaissance). No published system actively decides _where_ to collect the next observation to maximally reduce prediction uncertainty. This is the core gap the proposed approach addresses.

---

## 4. Bayesian Optimal Experimental Design and Sensor Placement

### 4.1 Theoretical Foundations

Bayesian optimal experimental design (BOED) provides the mathematical framework for selecting experiments (or sensor locations) to maximize expected information gain (EIG), also known as mutual information between observations and parameters of interest (Lindley 1956; Chaloner & Verdinelli 1995). The EIG criterion naturally balances exploration and exploitation — it favors measurements that are both highly uncertain and highly informative about quantities of interest.

For sensor placement in PDE-constrained inverse problems, the field has matured significantly:

- **Wu, Chen & Ghattas (2020, 2021)** developed fast, scalable computational frameworks for large-scale BOED with PDE constraints. Their goal-oriented OED formulation (GOOED) directly optimizes for uncertainty reduction in predicted quantities of interest rather than parameters — directly analogous to optimizing for fire spread prediction accuracy rather than fuel moisture estimation accuracy.
- **Alexanderian & Maio (2025)** proved formally that EIG is submodular in infinite-dimensional linear Gaussian Bayesian inverse problems with uncorrelated sensor data, extending the finite-dimensional result that enables greedy algorithms with guaranteed approximation ratios.
- **Attia & Constantinescu (2020)** extended OED to handle correlated observation errors — critical for remote sensing platforms where measurement correlations are unavoidable.

### 4.2 Submodular Optimization

Krause, Singh & Guestrin (2008) proved that maximizing mutual information for sensor placement in Gaussian processes is NP-complete but that greedy algorithms achieve a (1-1/e) ≈ 63% approximation ratio by exploiting the submodularity of mutual information. This result is foundational: it means that even without solving the placement problem exactly, a greedy algorithm provides a guaranteed near-optimal solution.

The submodularity property means: adding a sensor to a small set gives more marginal information gain than adding it to a larger set (diminishing returns). This property holds for mutual information under Gaussian assumptions and extends to the wildfire setting where the state variables (fuel moisture, wind) follow approximately Gaussian ensemble distributions.

### 4.3 Computational Challenges at Scale

Despite theoretical elegance, computing EIG for large-scale problems remains expensive. Each candidate sensor location requires evaluating how much the posterior uncertainty would change, which in turn requires running (or approximating) the forward model. For wildfire with M candidate locations and N ensemble members, this creates O(M × N) computational cost per decision step.

Approaches to manage this include: Laplace approximation of the posterior (avoiding full ensemble integration), low-rank approximation of prior-preconditioned Hessians, polynomial chaos surrogates, and neural network surrogates for the parameter-to-observable map (Wu et al. 2022). The most relevant for the wildfire setting is the **greedy algorithm with lazy evaluations** — exploiting submodularity to skip re-evaluation of low-gain candidates — which is simple to implement and effective in practice.

---

## 5. QUBO Formulation for Sensor Placement

### 5.1 Direct Precedent

Nakano & Uno (2024) formulated mutual information-based sensor placement directly as a QUBO and solved it on quantum annealing hardware. Their approach defines mutual information between selected and unselected sensor positions under multivariate normal assumptions and proposes an original method to express it as a QUBO. They validated the formulation on D-Wave and confirmed reasonable results, noting that "the advantage of quantum annealing emerges as the number of sensors increases." This is the most direct precedent for the proposed approach.

### 5.2 Related QUBO Sensor Placement Work

- **Water distribution networks** (2021): Formulated pressure sensor placement as QUBO/Ising model, solved on D-Wave via PyQUBO. Demonstrated that both simulated annealing and hybrid quantum-classical approaches produce valid solutions for real-world network topologies.
- **Structural health monitoring** (2023): Applied quantum-based combinatorial optimization for sensor placement in structural systems, comparing quantum annealing with classical approaches.
- **QUBO for Gaussian process variance reduction** (listed in the QUBO formulation registry): Directly relevant as the wildfire state can be modeled as a Gaussian process.
- **Sparse sensor placement for classification** (2024): Used QUBO inspired by Quadratic Programming Feature Selection to select sparse sensors minimizing redundancy. Found that QUBO with simulated annealing achieved accuracy between random and ML-based placement, with significantly shorter runtime.

### 5.3 Gap: No Application to Dynamic Environmental Monitoring

All existing QUBO sensor placement work addresses **static** placement — where to permanently install sensors in a fixed infrastructure. The proposed approach is fundamentally different: it addresses **dynamic, sequential** placement where the optimal locations change as the fire evolves and as new data is assimilated. This dynamic replanning dimension is novel in the QUBO sensor placement literature.

---

## 6. UAS/Drone-Based Wildfire Monitoring

### 6.1 Current State of Practice

Drone deployment for wildfire monitoring has advanced rapidly. US Forest Service and Department of Interior have integrated crewed and uncrewed operations since approximately 2015. Current operational uses include thermal hotspot detection, fire perimeter mapping, night surveillance, and post-fire assessment. The Wikipedia entry on drones in wildfire management (2025) documents operational programs in the US, Greece, and elsewhere.

Key capabilities relevant to active sensing:

- **Thermal imagery** from drones can detect hotspots and map fire perimeters at much higher resolution than satellites (Chen et al. 2022, USFS)
- **Persistent nighttime surveillance** fills a critical gap — fire behavior monitoring has historically been limited to visual conditions (Advexure 2025)
- **On-demand deployment** at low altitude provides temporal resolution satellites cannot match

### 6.2 UAV Path Planning for Fire Monitoring

Existing work on drone path planning for wildfire falls into several categories:

- **Fire perimeter tracking:** Autonomous fire-front following using vision-based algorithms (multiple studies). These methods track the _known_ fire boundary but do not optimize for uncertainty reduction.
- **Cooperative coverage:** Multi-UAV systems distributing over the fire area to maximize spatial coverage. Leader-follower frameworks (2020), heat-intensity-based distributed control, and cooperative prediction using Kalman estimation and deep learning (2022).
- **Human-centered active sensing** (2020): Proposed UAV coordination focused on supporting firefighters at specific areas of activity rather than autonomous area coverage. Identified the absence of human-centric approaches as a gap in the literature.
- **Hierarchical surveillance-suppression coordination** (Al-Husseini, Wray & Kochenderfer, Stanford, 2024): Formulated the wildfire initial attack as a multi-agent POMDP with hierarchical planners. Claimed to be the first work optimizing both surveillance and suppression using human-autonomous teaming. This is the closest existing work to the proposed approach in terms of operational concept.

### 6.3 Gap: No Information-Theoretic Optimization of Drone Sensing

**No published work uses Bayesian experimental design or information-theoretic criteria to determine where drones should observe during an active wildfire.** Existing approaches either track the fire front, maximize area coverage, or follow prescribed flight plans. The concept of routing drones to locations that maximally reduce _predictive uncertainty about future fire behavior_ — rather than simply observing the current fire state — does not exist in the wildfire drone literature.

---

## 7. Informative Path Planning for Environmental Monitoring

### 7.1 General IPP Framework

Informative path planning (IPP) for environmental monitoring is a mature robotics research area. Key developments:

- **Adaptive IPP with Gaussian processes:** Popović et al. (2017, 2020) developed IPP frameworks for terrain monitoring using UAVs, trading off sensor resolution, field of view, and information value.
- **Deep RL for IPP** (Rückin, Jin & Popović, 2021): Combined Monte Carlo tree search with learned neural networks for online replanning, achieving 8-10× runtime reduction over classical methods.
- **Multi-UAV adaptive IPP** (2023): Extended to cooperative multi-agent settings with constrained communication.
- **IA-TIGRIS** (Suvarna et al., CMU, 2026): Incremental and adaptive sampling-based planner validated on physical UAV hardware, demonstrating real-world applicability of online IPP.

### 7.2 Connection to Wildfire

The IPP literature provides methods for adaptively routing sensing platforms to maximize information — but has been applied primarily to static or slowly evolving spatial fields (temperature, pollution, terrain). Wildfire presents a fundamentally harder problem: the field being monitored (fire risk / state variables) evolves rapidly and nonlinearly, and the consequences of measurement are not just scientific but operationally critical. Transferring IPP methods to wildfire requires coupling them with fire spread models that generate the predictive distributions over which information gain is computed.

---

## 8. Airspace Coordination for Wildfire UAS Operations

### 8.1 NASA UTM and Wildfire Extensions

NASA's UAS Traffic Management (UTM) program developed air traffic management for low-altitude unmanned operations and has been explicitly adapted for wildfire. The FAA established the Wildland Fire Airspace Operations Research Transition Team in 2023 in collaboration with NASA. Successful shared-airspace tests were conducted in California (Spring 2023), demonstrating that information sharing across communication systems is feasible during simulated wildfire operations.

### 8.2 Existing SBIR Work

A prior SBIR award (Aeris) proposed a wildfire UTM system using graph analytics and ML for dynamic route planning and airspace deconfliction, ingesting fire conditions, traffic demands, and weather. This system would accommodate on-demand coordination regardless of whether aircraft are crewed or uncrewed.

### 8.3 Integration Point

The proposed active sensing system requires airspace coordination as an intrinsic component — dynamically routing sensing drones through airspace shared with suppression aircraft. This positions the QUBO-optimized drone routing as a natural extension of the UTM framework: the information-theoretic placement algorithm generates mission requirements, which the airspace coordination layer translates into feasible, deconflicted flight plans.

---

## 9. Summary of Critical Gaps

|Domain|Current State|Gap|
|---|---|---|
|Fire prediction|Deterministic, single-perimeter output|No operational uncertainty quantification|
|Fuel moisture|Sparse RAWS + coarse satellite|No high-resolution, temporally adaptive measurement|
|Data assimilation|Passive assimilation of available data|No active/targeted data collection|
|Sensor placement|Static infrastructure optimization|No dynamic, sequential replanning for evolving systems|
|QUBO sensor placement|Validated for static networks|Not applied to dynamic environmental monitoring|
|Drone wildfire monitoring|Fire-front tracking, area coverage|No information-theoretic measurement optimization|
|IPP for environmental monitoring|Mature for static/slow fields|Not applied to rapidly evolving wildfire scenarios|
|Airspace coordination|UTM extensions for wildfire proposed|Not coupled with information-driven sensing objectives|

The proposed approach sits precisely at the intersection of these gaps. Each component has validated precedent in its own domain; the novelty is their integration into a closed-loop system where ensemble fire prediction drives QUBO-optimized drone placement via information-theoretic criteria, with the combinatorial optimization solved on quantum hardware.

---

## 10. Key References

### Fire Spread Modeling

- Rothermel, R.C. (1972). A mathematical model for predicting fire spread in wildland fuels. USDA Forest Service Research Paper INT-115.
- Sullivan, A.L. (2009). Wildland surface fire spread modelling. _International Journal of Wildland Fire_, 18(4), 369-386.
- Mandel, J., Beezley, J.D., Coen, J.L., Kim, M. (2009). Data assimilation for wildland fires. _IEEE Control Systems Magazine_, 29(3).
- Ciri, U. et al. (2021). Uncertainty quantification of forecast error in coupled fire-atmosphere wildfire spread simulations. _International Journal of Wildland Fire_, 30(10), 790-806.

### Data Assimilation for Wildfire

- Mandel, J. et al. (2007/2009). Data assimilation for wildland fires: Ensemble Kalman filters in coupled atmosphere-surface models. arXiv:0712.3965.
- Rochoux, M. et al. (2015). Towards predictive data-driven simulations of wildfire spread – Part II: EnKF for front-tracking simulator. _Natural Hazards and Earth System Sciences_, 15, 1721-1739.
- Vejmelka, M., Kochanski, A.K., Mandel, J. (2013). Data assimilation of fuel moisture in WRF-SFIRE.
- Mandel, J. et al. (2023). Building a fuel moisture model for WRF-SFIRE from data: From Kalman filters to recurrent neural networks.
- Farguell, A. et al. (2023/2025). Generative algorithms for fusion of physics-based wildfire spread models with satellite data.

### Uncertainty Quantification

- Grieshop, N. & Wikle, C.K. (2023). Data-driven modeling of wildfire spread with stochastic cellular automata and latent spatio-temporal dynamics.
- Ujjwal, K.C. et al. (2021). Global sensitivity analysis for uncertainty quantification in fire spread models.
- Chakravarty, A. (2025). Spatial uncertainty quantification in wildfire forecasting for climate-resilient emergency planning.

### Fuel Moisture

- Yebra, M. et al. (2013). A global review of remote sensing of live fuel moisture content for fire danger assessment. _Remote Sensing of Environment_.
- Cho, E. et al. (2025). Remote sensing of live fuel moisture for wildfires using SMAP satellite observations. _Geophysical Research Letters_.
- Jolly, W.M. (2007). Sensitivity of a surface fire spread model and associated fire behaviour fuel models to changes in live fuel moisture.

### Bayesian Optimal Experimental Design

- Lindley, D.V. (1956). On a measure of the information provided by an experiment. _Annals of Mathematical Statistics_.
- Chaloner, K. & Verdinelli, I. (1995). Bayesian experimental design: A review. _Statistical Science_.
- Wu, K., Chen, P., Ghattas, O. (2020/2021). Fast and scalable computational framework for large-scale BOED / Goal-oriented BOED.
- Alexanderian, A. & Maio, S. (2025). Submodularity of the expected information gain in infinite-dimensional linear inverse problems.

### Submodular Optimization & Sensor Placement

- Krause, A., Singh, A., Guestrin, C. (2008). Near-optimal sensor placements in Gaussian processes. _JMLR_, 9, 235-284.
- Eswar, S., Rao, V., Saibaba, A.K. (2024). Bayesian D-optimal experimental designs via column subset selection.
- Attia, A. & Constantinescu, E. (2020). Optimal experimental design for inverse problems with observation correlations.

### QUBO Sensor Placement

- Nakano, Y. & Uno, S. (2024). Quadratic formulation of mutual information for sensor placement optimization using Ising and quantum annealing machines. arXiv:2407.14747.
- Araz, A. et al. (2021). Solving sensor placement problems in real water distribution networks using adiabatic quantum computation. arXiv:2108.04075.

### Drone-Based Wildfire Monitoring

- Chen, X. et al. (2022). Wildland fire detection and monitoring using a drone-collected RGB/IR image dataset. _IEEE Access_, 10.
- Al-Husseini, M., Wray, K.H., Kochenderfer, M.J. (2024). Hierarchical framework for optimizing wildfire surveillance and suppression using human-autonomous teaming. Stanford.
- Yang, T. et al. (2021). Optimized deployment of unmanned aerial vehicles for wildfire detection and monitoring.

### Informative Path Planning

- Popović, M. et al. (2017/2020). An informative path planning framework for UAV-based terrain monitoring.
- Rückin, J., Jin, L., Popović, M. (2021). Adaptive informative path planning using deep reinforcement learning for UAV-based active sensing.
- Suvarna, N. et al. (2026). IA-TIGRIS: An incremental and adaptive sampling-based planner for online informative path planning. _IEEE TRO_.

### Wildfire Airspace Management

- NASA AOSP / UTM Program documentation.
- FAA Wildland Fire Airspace Operations Research Transition Team (2023).