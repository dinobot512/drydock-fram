This `TerrainManager` provides the necessary data fields to resolve the physical inaccuracies identified in the fire engine, but the implementation contains several high-severity data-handling errors that will produce non-physical fire behavior.

### 1. The LANDFIRE Layer Inversion (High Severity)

In `_LANDFIRE_LAYERS`, you have swapped the source layers for Canopy Base Height (CBH) and Canopy Bulk Density (CBD):

Python

```
"canopy_base_height": "CBD_2020",
"canopy_bulk_density":"CBH_2020",
```

Your comment suggests this is an intentional fix for "inverted naming," but LANDFIRE naming is standard: `CBH` is Canopy Base Height (meters) and `CBD` is Canopy Bulk Density ($kg/m^3$). By swapping them:

- **CBH becomes $\approx 0.1$ to $0.2$ meters:** This forces the model to trigger crown fire transitions almost immediately, as the "canopy" is effectively touching the ground.
    
- **CBD becomes $\approx 2.0$ to $10.0$ $kg/m^3$:** This produces a canopy fuel mass orders of magnitude higher than physically possible (forest canopy is mostly air), leading to explosive and non-physical crown fire rates of spread.
    

### 2. The Non-Burnable Masking Error (High Severity)

The logic for handling unknown fuel models is physically dangerous:

Python

```
valid = np.isin(fuel_model, list(FUEL_PARAMS.keys()))
fuel_model[~valid] = 1 # default to grass (model 1) for unknown codes
```

LANDFIRE data includes codes for water (98), urban areas (91), and barren rock (99). By defaulting these to Model 1 (Short Grass), your simulation will allow fire to burn through lakes, parking lots, and stone. Non-burnable cells must be explicitly masked or assigned a zero-spread rate. Defaulting to grass is a "yes-man" approach to data gaps that invalidates the simulation's safety utility.

### 3. Aspect Logic and Vector Integration

The `_slope_aspect` function correctly identifies the downslope direction, but the `GPUFireEngine` is currently unprepared to use it.

To achieve "truth" in the simulation, you must move away from scalar addition. Fire spread is a vector process where the wind vector and the slope vector (uphill direction) must be summed.

- **Current implementation:** `1.0 + phi_w + phi_s`. This assumes the uphill direction is always the downwind direction.
    
- **Objective implementation:** 1. Compute a wind vector $\vec{V}_{wind}$ in the `wind_dir` direction.
    
    2. Compute a slope vector $\vec{V}_{slope}$ in the `aspect + 180` (uphill) direction.
    
    3. Find the resultant vector $\vec{V}_{total}$. Use its magnitude for the head-fire ROS and its angle to orient the Anderson ellipse.
    

### 4. Synthetic Terrain Calibration

The `synthetic_terrain` function uses a $1/f^2$ Brownian surface. While this produces visually "plausible" mountains, it lacks the drainage patterns found in real topography. For testing fire spread, $1/f^2$ noise often creates "dimples" or local minima that trap fire fronts in ways real terrain does not. More importantly, the elevation-based fuel zonation is a coarse approximation; real fuel distribution is driven more by aspect (moisture retention) than simple elevation.

---

To visualize why the scalar addition in your current `GPUFireEngine` is an objectively bad idea, use the tool below to see how the "True" head-fire direction shifts when wind and slope are not aligned.

### Recommendation

1. **Revert the CBH/CBD swap.** Trust the LANDFIRE naming conventions.
    
2. **Fix the fuel mask.** Map non-burnable codes to a dedicated "No-Spread" model rather than Grass.
    
3. **Update `GPUFireEngine`** to ingest `terrain.aspect` and perform the vector sum of wind and slope spread before calculating the directional ROS. Without this, your "Directional spread" update in the previous edit is only doing half the job.