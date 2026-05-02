It's extremely well-studied and has a closed-form solution. This is kriging — the foundational method of geostatistics, developed in the 1950s-60s for mining (estimating ore grade between boreholes) and now the standard method across all spatial sciences.

**The exact problem:** You have measurements at known locations (RAWS stations). You want to estimate (a) the value and (b) the uncertainty of a spatial field at every unobserved location. This is Gaussian process regression, and kriging is its geostatistical name.

**The closed-form solution:**

Given observations y at locations X_obs, the posterior mean and variance at any unobserved location x* are:

```
μ(x*) = k(x*, X_obs) × [K(X_obs, X_obs) + σ²_noise I]⁻¹ × y

σ²(x*) = k(x*, x*) - k(x*, X_obs) × [K(X_obs, X_obs) + σ²_noise I]⁻¹ × k(X_obs, x*)
```

Where k is the covariance function (kernel) that encodes how spatially correlated the variable is. That's it. The posterior variance σ²(x*) is your prior uncertainty field. It depends only on the geometry of observation locations and the covariance structure — not on the observed values themselves. You can compute the entire uncertainty map before seeing any data.

**What the terms mean intuitively:**

- k(x*, X_obs): how correlated is the unobserved point with each observed station
- K(X_obs, X_obs): how correlated are the stations with each other
- The matrix inverse figures out: given that stations are correlated with each other (some are redundant), how much independent information do they collectively provide about x*?

Right next to a RAWS station, k(x*, X_obs) is large for that station, so uncertainty drops to nearly zero. Equidistant between two stations, it depends on whether the stations are correlated with each other (if they are, the second station adds less). Far from all stations, k values are small and uncertainty approaches the prior variance.

**The covariance function k encodes the physics:**

For FMC, the correlation between two points depends on:

- Distance (closer = more correlated)
- Whether they share terrain features (same aspect, same elevation band, same fuel type)

A simple isotropic kernel:

```
k(x, x') = σ² × exp(-||x - x'||² / (2ℓ²))
```

where ℓ is the correlation length (100m-2km for FMC depending on terrain). A more realistic kernel could incorporate terrain similarity:

```
k(x, x') = σ² × exp(-d_geographic / ℓ_geo) × exp(-d_terrain / ℓ_terrain)
```

where d_terrain is the difference in elevation, aspect, or canopy cover. This means two points 500m apart on the same slope are more correlated than two points 500m apart on opposite sides of a ridge.

**Implementation — this is a solved problem with mature libraries:**

```python
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel

# RAWS station locations and FMC observations
X_obs = np.array([[lat1, lon1], [lat2, lon2], ...])  # station coordinates
y_obs = np.array([fmc1, fmc2, ...])                   # observed FMC values

# Fit GP
kernel = Matern(length_scale=5000, nu=1.5) + WhiteKernel(noise_level=0.01)
gp = GaussianProcessRegressor(kernel=kernel)
gp.fit(X_obs, y_obs)

# Predict mean and uncertainty at all grid cells
X_grid = np.array([[lat, lon] for lat, lon in all_grid_cells])
fmc_mean, fmc_std = gp.predict(X_grid, return_std=True)

# fmc_std IS your prior uncertainty field
# Shape: (n_grid_cells,) — reshape to (rows, cols)
prior_uncertainty = fmc_std.reshape(rows, cols)
```

Five lines of scikit-learn. The GP handles the matrix algebra, kernel fitting, and prediction internally. The output `fmc_std` is the mathematically exact posterior standard deviation at every grid cell.

**How this connects to your system:**

The GP posterior uncertainty field becomes the σ²_v(i) in your QUBO. Instead of inventing perturbation magnitudes, you compute them from the kriging variance. Cells near RAWS get small σ², cells far from RAWS get large σ². The ensemble perturbations at each cell should be scaled by this GP uncertainty — which makes the ensemble physically consistent with what's actually known vs. unknown.

After a drone observation, you add that measurement to the GP and recompute. The uncertainty field updates: cells near the drone path drop in uncertainty, cells far away are unchanged. The updated GP uncertainty feeds the next QUBO cycle.

**This is also exactly what Vejmelka, Kochanski & Mandel (2013) did for WRF-SFIRE.** They used a trend surface model (a simplified GP) to estimate FMC fields and their uncertainty from sparse RAWS observations, then fed this into a Kalman filter. Your approach is the same concept with a proper GP and targeted drone observations instead of passive RAWS-only assimilation.

**What this means architecturally:**

You might not even need the full EnKF for the spatial uncertainty estimation. The GP gives you the prior uncertainty field directly from observation geometry. The EnKF handles the _dynamic_ update — how observations of FMC at time t constrain fire state at time t+1. But the static spatial uncertainty question ("how well do we know FMC across the landscape given current station locations?") is pure GP regression.

A cleaner architecture might be:

1. **GP layer:** compute prior mean and uncertainty fields for FMC and wind from RAWS + any drone observations so far. This is the spatial interpolation with calibrated uncertainty.
2. **Ensemble layer:** perturb parameters using GP uncertainty as the perturbation scale. Run fire model forward. Compute arrival time variance and sensitivity.
3. **QUBO layer:** use GP uncertainty × fire sensitivity as w_i coefficients. GP spatial correlation as J_ij source.
4. **After drone observation:** update GP with new data point. GP uncertainty field changes. Next ensemble uses updated perturbation scales.

The GP replaces the ad-hoc "perturb FMC by ±20% everywhere" with "perturb FMC by the amount it's actually uncertain at each location given what we've observed." This is more principled and produces a better QUBO.

**Computational cost:** GP regression is O(N³_obs) in the number of observation points for the matrix inverse, and O(N²_obs × N_predict) for prediction at all grid cells. With 10-50 observations (RAWS + drones), this is microseconds. Even with 1,000 observations, it's sub-second. The GP is never the bottleneck.

**For the hackathon:** use scikit-learn's GP. Initialize with RAWS station locations (from the LANDFIRE/RAWS database for your chosen area). Compute the prior uncertainty field. Use it to scale ensemble perturbations. After each drone observation cycle, add the new points and recompute. This is maybe 20 lines of code and it makes the entire system mathematically grounded rather than heuristic.