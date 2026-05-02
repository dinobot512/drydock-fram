
**1. Whether the information-gain differential is large enough to matter**

The adjacent-field evidence is encouraging but not conclusive for fire. Krause et al.'s empirical results on real environmental monitoring data (temperature, precipitation) showed mutual-information-optimized placement significantly outperformed entropy-based, geometric, and random placement — often achieving comparable prediction accuracy with 2-3× fewer sensors. Mobile sensor networks for GP learning (Xu et al. 2011) showed adaptive sampling outperforms random sampling on advection-diffusion fields, which is structurally similar to fire spread.

But here's the specific gap: all of these results are on fields with **stationary or slowly varying correlation structure**. Fire has two properties that could erode the differential. First, the UBC thesis (2017) found that _daytime_ fuel moisture and fire danger exhibited **low spatial variability** regardless of weather — variability was higher at night and under cool/moist conditions. If fuel moisture is relatively homogeneous during peak fire hours, the marginal value of spatial targeting drops because any measurement tells you nearly the same thing. Second, fire spread is strongly directional and discontinuous (spot fires), so the prediction-relevant uncertainty may concentrate narrowly along the fire front rather than distributing across a field where spatial optimization helps.

**What we can say specifically:** the information-gain differential will be largest when (a) the landscape is heterogeneous (mixed fuel types, complex terrain), (b) the fire is in moderate conditions where prediction is possible but nontrivial, and (c) you're predicting over 2-6 hour horizons. The approach probably adds less for homogeneous grassland fires in flat terrain or for extreme plume-dominated fires where the dominant uncertainty is atmospheric, not fuel.

**Remaining gap:** No one has computed the information-gain landscape over a fire ensemble. This is your hackathon deliverable.

---

**2. Gaussian/pairwise approximation validity**

The news here is mixed. Krause's foundational result — mutual information is submodular under GPs, greedy gives (1-1/e) — holds for your formulation _if_ you're optimizing mutual information directly. But Malings & Pozzi (2019, _Reliability Engineering & System Safety_) demonstrated explicitly that **value of information (VoI) is NOT submodular**, and greedy optimization can produce genuinely suboptimal results when measurements have correlated noise or when the decision problem is nonlinear. Their examples involve structural health monitoring, but the mechanism applies to fire: if the "value" of information is measured by its impact on a nonlinear fire management decision (where to deploy resources) rather than by variance reduction, the submodularity guarantee breaks.

For the QUBO formulation specifically, the pairwise approximation truncates higher-order mutual information. Alexanderian & Maio (2025) proved submodularity of EIG in infinite-dimensional settings, but only for **uncorrelated sensor data** — once measurement errors correlate (which drone sensors will, since nearby measurements share atmospheric conditions), the theory is less clean.

**What we can say specifically:** the Gaussian pairwise approximation is defensible for the _prototype_ because (a) fire ensemble distributions under moderate conditions are approximately Gaussian, (b) the pairwise QUBO captures the dominant spatial correlation structure, and (c) the greedy baseline provides a comparison that doesn't require this approximation. The breakdown case is discrete regime transitions — crown fire initiation, spot fire ignition — where the uncertainty is binary, not continuous. Your prototype should ideally include at least one scenario where the dominant risk is a discrete transition, to see if the continuous optimization still captures it indirectly.

**Remaining gap:** Whether the pairwise QUBO solution quality degrades gracefully or catastrophically relative to full submodular greedy when applied to fire-specific covariance structures. This is characterizable in simulation.

---

**3. Loop closure time vs. fire evolution**

This is where the research most concretely narrows the uncertainty. A 2025 geospatial monitoring system reported that ensemble fire spread + uncertainty computation runs in **10-15 minutes** per issuance. DNN surrogates for FARSITE produce 15-minute-increment predictions orders of magnitude faster than physics-based models (Hodges & Lattimer, 2022). The FARSITE-EnKF polyline simplification (Yoo et al. 2023) was explicitly designed to achieve "near-real-time" data assimilation speed.

On the fire evolution side: for moderate surface fires, rate of spread is order 0.5-2 m/s. Over a 30-minute decision cycle, that's 1-3.6 km of front advance. The spatial scale over which fuel moisture and wind vary meaningfully is 100m-1km (driven by terrain and vegetation transitions). So the _spatial structure_ of optimal placement should be relatively stable over 30-60 minutes — the fire moves, but the relative ranking of "where is uncertainty highest" depends on landscape features that don't move.

The critical exception is **wind shifts**. A wind direction change invalidates the entire spatial priority map instantly. The sensitivity analysis literature consistently identifies wind as the fastest-changing variable. Your system would need to detect wind shifts (from drone anemometry or weather model updates) and trigger replanning outside the normal cycle.

**What we can say specifically:** a 15-30 minute cycle is probably achievable with surrogate models and is probably fast enough for surface fires in complex terrain. It is definitely NOT fast enough for plume-dominated fires with fire-induced wind shifts. The approach is most valuable in the "moderate complexity" regime — which is also where it's most operationally useful, since extreme fires overwhelm any management strategy.

**Remaining gap:** Nobody has measured how fast the _optimal sensor placement_ changes as a fire evolves. This is the specific unknown. It's different from asking "how fast does the fire change" — the placement depends on the covariance structure, which may be more stable than the fire state itself. Characterizable in simulation.

---

**4. Ensemble variance structure at tractable sizes**

The evidence here is stronger than I initially suggested. Fire-EnSF (2025) ran FARSITE ensembles on 40km × 40km domains at 30m resolution for real wildfires. The computational bottleneck was noted but the ensembles were feasible. FireBench (2024) ran 117 high-fidelity LES simulations (1.35 billion mesh points each) for ensemble analysis on TPUs — demonstrating that computational constraints are being actively pushed back. The global sensitivity analyses (Ujjwal 2021) established parameter importance rankings that are consistent across multiple SA methods, suggesting the variance decomposition is robust.

For the spatial differentiation question — whether you get meaningfully _different_ variance drivers at different locations — the fuel moisture research helps. The heathland/peatland study (Fire Ecology, 2024) demonstrated that FMC is "highly spatially variable at the landscape level" driven by soil texture, canopy age, aspect, and slope. The UBC study found that variability is terrain-driven and structured, not random. This means the variance decomposition _should_ produce spatially differentiated maps: near a ridge, wind dominates; in a sheltered valley with dense canopy, fuel moisture dominates.

**What we can say specifically:** 50-200 member ensembles with simplified fire models produce usable variance structure. The spatial differentiation needed for targeted sensing is supported by the known spatial structure of the underlying variables. The real question is whether the ensemble captures the _correct_ variance structure — if the fire model has systematic biases (and Rothermel-based models do), the variance decomposition points you to the wrong locations.

**Remaining gap:** Model structural uncertainty (is the fire model wrong in ways the ensemble doesn't capture?) vs. parametric uncertainty (are the inputs uncertain but the model structure adequate?). The ensemble approach handles the latter but not the former.

---

**5. Drone measurement → model state variable mapping**

This is where the most concrete new evidence emerged. A 2023 study (Forests) used UAV multispectral imagery with deep learning to predict dead fuel moisture content, demonstrating feasibility of drone-based FMC estimation. A separate study using a Phantom 4 Multispectral UAV with Random Forest achieved R² = 0.86 for live fuel moisture using only visible and near-infrared bands. Another used UAV thermal infrared with an apparent thermal inertia (ATI) proxy to estimate soil moisture with R² = 0.83. The grasslands study (PMC 2021) used SWIR and multispectral cameras on a DJI M600 to estimate fuel moisture in grasslands.

For wind, drone-mounted anemometry is less studied but feasible — sonic anemometers can be integrated, and several studies have used drone-derived turbulence measurements in atmospheric boundary layer research. The bigger issue is that wind _at the surface_ where fire spreads differs from wind at drone flight altitude, and this relationship depends on canopy structure.

**What we can say specifically:** R² of 0.83-0.94 for moisture proxies means drone measurements have useful but imperfect correlation with the model state variable. A 10-15% residual error in FMC measurement, given Jolly's finding that 10% FMC difference produces up to 1200% ROS difference, means measurement noise is significant but still far better than the current approach of interpolating from RAWS stations 50+ km apart. The question is not "are drone measurements perfect?" but "are they better than what the model currently uses?" — and the answer is almost certainly yes.

**Remaining gap:** No study has measured FMC from a drone _during an active wildfire_ near a fire front. The thermal environment near a fire (radiative heating, convective updrafts, smoke) could degrade multispectral and thermal measurements. Flight safety constraints may force measurements at distances where the measurement is less useful. This is a practical barrier that simulation can't fully address.

---

**Synthesis: what's actually unknown vs. what just hasn't been applied to fire**

|Uncertainty|Status|Action|
|---|---|---|
|Information gain differential|Unknown — no one has computed it for fire; adjacent-field results suggest 2-3× but the fire-specific correlation structure could erode this|**Your hackathon deliverable**|
|Gaussian/pairwise approximation|Theoretically bounded for the continuous case; known to break for VoI with correlated noise and discrete events|Acknowledge; test with discrete-transition scenarios|
|Loop closure time|Probably feasible (~15-30 min) for moderate fires; definitely infeasible for extreme fires|Characterize in simulation how fast optimal placement changes|
|Ensemble variance structure|Well-supported at moderate scales; concern is model structural bias, not ensemble size|Known risk; mitigatable with ML surrogates|
|Drone → model variable mapping|R² of 0.83-0.94 from multiple studies; untested near active fire fronts|Practical barrier; acknowledge for operational system|

The one thing I'd flag that came out of the Vanderbilt connection: the Kazma & Taha paper on submodular sensor scheduling for nonlinear networks is from _your department at Vanderbilt_. That's a potential collaboration or at least a citation that grounds your work locally.