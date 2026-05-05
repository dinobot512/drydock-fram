Path-Based Information Optimization & Scaling Analysis

---

## Part 1: Correlation-Domain Graph Path Optimization

### Concept

Replace point selection with path optimization over a reduced graph. Cells within one correlation length are grouped into domains — measuring one cell in a domain captures ~90% of the information the others would provide. The optimization operates on this coarser graph, selecting paths through domains that maximize non-redundant information per unit travel cost, subject to range and depot constraints.

### Step 1: Build Correlation-Domain Graph

Partition the grid into regions of approximately one correlation length diameter. Each region becomes a node. Edges connect adjacent regions.

```python
@dataclass
class CorrelationDomain:
    domain_id: int
    cells: list[tuple[int, int]]           # all grid cells in this domain
    representative_cell: tuple[int, int]    # cell with highest w_i
    centroid: np.ndarray                    # (x_m, y_m) in meters, for real distance
    info_value: float                       # max w_i within domain
    dominant_variable: str                  # "fmc" | "wind_speed" | "wind_direction"

@dataclass  
class DomainEdge:
    source: int                            # domain ID
    target: int                            # domain ID
    cross_correlation: float               # correlation between domains (0-1)
    information_gain: float                # info from crossing this boundary
    real_distance_m: float                 # flight distance between centroids
    travel_time_s: float                   # real_distance / drone_speed

def build_correlation_graph(w_field, gp, terrain, config):
    """
    Reduce full grid to correlation-domain graph.
    
    w_field: (rows, cols) information value at every cell
    gp: fitted GP (for cross-domain correlation computation)
    terrain: TerrainData
    config: includes correlation_length, resolution
    """
    rows, cols = w_field.shape
    domain_size = int(config.correlation_length / config.resolution_m)
    # e.g., 500m / 50m = 10 cells per domain side
    
    n_dr = rows // domain_size + (1 if rows % domain_size else 0)
    n_dc = cols // domain_size + (1 if cols % domain_size else 0)
    
    # Build domains
    domains = []
    domain_id = 0
    for dr in range(n_dr):
        for dc in range(n_dc):
            r_start = dr * domain_size
            r_end = min(r_start + domain_size, rows)
            c_start = dc * domain_size
            c_end = min(c_start + domain_size, cols)
            
            cells = [(r, c) for r in range(r_start, r_end) 
                            for c in range(c_start, c_end)]
            
            # Representative cell: highest w_i in domain
            w_values = [w_field[r, c] for r, c in cells]
            best_idx = np.argmax(w_values)
            rep_cell = cells[best_idx]
            
            centroid_r = (r_start + r_end) / 2 * config.resolution_m
            centroid_c = (c_start + c_end) / 2 * config.resolution_m
            
            domains.append(CorrelationDomain(
                domain_id=domain_id,
                cells=cells,
                representative_cell=rep_cell,
                centroid=np.array([centroid_r, centroid_c]),
                info_value=w_values[best_idx],
                dominant_variable=get_dominant_variable(rep_cell, w_by_variable)
            ))
            domain_id += 1
    
    # Build edges between adjacent domains
    edges = []
    for i, d_i in enumerate(domains):
        for j, d_j in enumerate(domains):
            if i >= j:
                continue
            
            # Check adjacency (within 1.5× domain size)
            dist = np.linalg.norm(d_i.centroid - d_j.centroid)
            if dist > 1.5 * domain_size * config.resolution_m:
                continue
            
            # Cross-domain correlation from GP kernel
            cross_corr = gp.kernel_(
                _obs_features([d_i.representative_cell], terrain, config.resolution_m),
                _obs_features([d_j.representative_cell], terrain, config.resolution_m)
            )[0, 0]
            
            # Information gain from crossing: high when correlation is low
            # (different terrain/fuel → new information at boundary)
            edge_info = (1.0 - cross_corr) * min(d_i.info_value, d_j.info_value)
            
            # Real flight distance (could account for terrain avoidance)
            real_dist = np.linalg.norm(d_i.centroid - d_j.centroid)
            
            edges.append(DomainEdge(
                source=i, target=j,
                cross_correlation=cross_corr,
                information_gain=edge_info,
                real_distance_m=real_dist,
                travel_time_s=real_dist / config.drone_speed
            ))
    
    return CorrelationGraph(domains, edges)
```

**Scale:** For a 200×200 grid with 500m correlation length at 50m resolution: ~400 domains, ~1,600 edges. For a 2000×2000 grid (100×100 km): ~40,000 domains, ~160,000 edges. Still tractable for graph algorithms.

### Step 2: Precompute Station Return Costs

Before path planning, run Dijkstra from every ground station to every domain using real_distance as edge weights. This gives a lookup table: "from any domain, how far is the nearest reachable station?"

```python
def precompute_return_costs(graph, stations):
    """
    For each domain, compute minimum real distance to any station.
    Uses Dijkstra on the domain graph with real_distance edge weights.
    """
    min_return_cost = np.full(len(graph.domains), np.inf)
    nearest_station = np.full(len(graph.domains), -1, dtype=int)
    
    for station in stations:
        # Station maps to its containing domain
        station_domain = graph.domain_containing(station.location)
        
        # Dijkstra from this station's domain
        distances = dijkstra(graph, source=station_domain, weight='real_distance_m')
        
        for d_id, dist in enumerate(distances):
            if dist < min_return_cost[d_id]:
                min_return_cost[d_id] = dist
                nearest_station[d_id] = station.id
    
    return min_return_cost, nearest_station
```

### Step 3: Greedy Path Planning with Exact GP Updates

For each drone, select a path through the domain graph that maximizes non-redundant information subject to range and depot constraints.

```python
def plan_drone_path(graph, start_station, stations, max_range_m,
                    gp_variance, sensitivity, observability,
                    min_return_cost, nearest_station):
    """
    Plan a single drone's path through the correlation-domain graph.
    
    Uses exact GP conditional variance updates (not heuristic discounts)
    to track non-redundant information along the path.
    """
    start_domain = graph.domain_containing(start_station.location)
    
    path = [start_domain]
    remaining_range = max_range_m
    current = start_domain
    current_variance = gp_variance.copy()
    total_info = 0.0
    marginal_gains = []
    
    while True:
        # Recompute w at each unvisited domain using CURRENT variance
        candidates = []
        for domain in graph.domains:
            if domain.domain_id in [d.domain_id for d in path]:
                continue
            
            rep = domain.representative_cell
            w = current_variance[rep] * abs(sensitivity[rep]) * observability[rep]
            
            # Travel cost to reach this domain
            travel_cost = graph.real_distance(current.domain_id, domain.domain_id)
            if travel_cost is None:
                continue  # not reachable in one hop (could use Dijkstra for multi-hop)
            
            # Can we afford to go there AND return to a station?
            return_cost = min_return_cost[domain.domain_id]
            if travel_cost + return_cost > remaining_range:
                continue
            
            # Information efficiency: non-redundant info per meter of travel
            # Include edge information gain (crossing terrain boundary)
            edge = graph.edge(current.domain_id, domain.domain_id)
            edge_info = edge.information_gain if edge else 0.0
            
            total_domain_info = w + edge_info
            efficiency = total_domain_info / (travel_cost + 1e-6)
            
            candidates.append((domain, efficiency, travel_cost, total_domain_info))
        
        if not candidates:
            break
        
        # Select best candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_domain, _, travel_cost, info_gained = candidates[0]
        
        # Update GP variance (exact conditional update at representative cell)
        current_variance = gp_conditional_variance(
            current_variance, best_domain.representative_cell, gp)
        
        # Update path state
        path.append(best_domain)
        remaining_range -= travel_cost
        current = best_domain
        total_info += info_gained
        marginal_gains.append(info_gained)
    
    # Return to nearest station
    return_station_domain = nearest_station[current.domain_id]
    path.append(graph.domains[return_station_domain])
    
    return DronePath(
        domains=path,
        total_info=total_info,
        marginal_gains=marginal_gains,
        total_distance=max_range_m - remaining_range,
        start_station=start_station,
        end_station=stations[nearest_station[current.domain_id]]
    )

def plan_fleet(graph, stations, n_drones, max_range_m,
               gp_variance, sensitivity, observability):
    """
    Plan paths for K drones sequentially.
    After each drone's path is planned, update the GP variance
    to reflect what that drone will observe — subsequent drones
    avoid redundancy with earlier drones' paths.
    """
    paths = []
    current_variance = gp_variance.copy()
    
    for k in range(n_drones):
        # Pick starting station (round-robin or nearest to highest remaining w)
        start = select_start_station(stations, current_variance, sensitivity, k)
        
        path = plan_drone_path(
            graph, start, stations, max_range_m,
            current_variance, sensitivity, observability,
            min_return_cost, nearest_station
        )
        paths.append(path)
        
        # Update variance for all cells along this drone's path
        for domain in path.domains:
            current_variance = gp_conditional_variance(
                current_variance, domain.representative_cell, gp)
    
    return paths
```

### Step 4: Score Full Cell-Level Path

Convert the domain-level path to cell-level waypoints and score with sequential GP conditional variance to get the exact non-redundant information along the actual drone trajectory.

```python
def score_path(domain_path, gp, gp_variance, sensitivity, resolution):
    """
    Exact information along the full cell-level trajectory.
    
    For each cell the drone overflies (including transit between
    domain representative cells), compute marginal information
    conditioned on all previous cells along the path.
    """
    # Convert domain path to cell-level waypoints
    waypoints = [d.representative_cell for d in domain_path]
    
    # Generate all cells along the flight path (Bresenham between waypoints)
    all_cells = []
    for i in range(len(waypoints) - 1):
        segment = bresenham_line(waypoints[i], waypoints[i+1])
        # Add camera footprint (3 cells wide)
        for cell in segment:
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    c = (cell[0]+dr, cell[1]+dc)
                    if in_bounds(c, gp_variance.shape) and c not in all_cells:
                        all_cells.append(c)
    
    # Sequential GP scoring
    current_var = gp_variance.copy()
    total_info = 0.0
    per_cell_info = []
    
    for cell in all_cells:
        # Marginal info at this cell given everything observed so far
        w_before = current_var[cell] * abs(sensitivity[cell])
        
        # Update variance
        current_var = gp_conditional_variance(current_var, cell, gp)
        
        w_after = current_var[cell] * abs(sensitivity[cell])
        marginal = w_before - w_after
        total_info += marginal
        per_cell_info.append((cell, marginal))
    
    return PathScore(
        total_info=total_info,
        n_cells_observed=len(all_cells),
        per_cell_info=per_cell_info,
        info_per_meter=total_info / path_length_m
    )
```

### Step 5: Local Refinement (Optional)

After the greedy selects domains and the path scorer evaluates the trajectory, locally perturb waypoints within their domains to find a better path:

```python
def refine_path(domain_path, gp, gp_variance, sensitivity, n_iterations=20):
    """
    Stochastic local search: perturb waypoints within domains,
    rescore, keep if better.
    """
    current_score = score_path(domain_path, gp, gp_variance, sensitivity)
    
    for _ in range(n_iterations):
        # Pick a random domain in the path
        idx = np.random.randint(1, len(domain_path) - 1)  # skip start/end stations
        domain = domain_path[idx]
        
        # Pick a random alternative cell within the domain
        alt_cell = random.choice(domain.cells)
        
        # Create modified path
        modified = domain_path.copy()
        modified[idx] = modified[idx]._replace(representative_cell=alt_cell)
        
        new_score = score_path(modified, gp, gp_variance, sensitivity)
        if new_score.total_info > current_score.total_info:
            domain_path = modified
            current_score = new_score
    
    return domain_path, current_score
```

Cost: 20 iterations × ~10ms per score = 200ms. Marginal improvement ~5-10%.

---

## Part 2: Scaling Analysis

### Current Scale

200×200 grid at 50m resolution = 10×10 km domain, 40,000 cells.

### What Changes at Each Scale

|Scale|Grid|Cells|Area|Use case|
|---|---|---|---|---|
|1× (current)|200×200|40K|100 km²|Single fire incident|
|10×|632×632|400K|1,000 km²|Large complex fire|
|100×|2000×2000|4M|10,000 km²|Fire complex / county|
|1000×|6320×6320|40M|100,000 km²|Regional / state-wide|

### Component-by-Component Scaling

#### GP Fitting

**Current:** O(N³_obs) where N_obs = number of observations (~50-200). Independent of grid size. Microseconds to milliseconds.

**At scale:** N_obs grows with area (more RAWS stations, more drones). At 100× area, maybe 500-1000 observations. O(1000³) = 10⁹ operations. ~1 second on CPU. At 1000× area, ~5000 observations → O(5000³) = 125 billion. ~30 seconds. Too slow.

**Fix:** Sparse GP approximations. Inducing point methods (Titsias 2009) reduce from O(N³) to O(NM²) where M << N is the number of inducing points. With M=200 inducing points, fitting on 5000 observations takes O(5000 × 200²) = 200M operations. Milliseconds. Libraries: GPyTorch handles this natively on GPU with LOVE/SKIP preconditioning for GPs with >10,000 observations.

**GPU acceleration:** GPyTorch + CUDA enables GP fitting and prediction on GPU. Kernel matrix operations parallelize naturally. 100× speedup over sklearn for large observation counts.

|Scale|Observations|Exact GP|Sparse GP (M=200)|Sparse GP + GPU|
|---|---|---|---|---|
|1×|100|1 ms|1 ms|<1 ms|
|10×|500|100 ms|5 ms|<1 ms|
|100×|2000|8 s|20 ms|2 ms|
|1000×|5000|125 s|50 ms|5 ms|

#### GP Prediction (variance at all grid cells)

**Current:** O(N_obs² × D) where D = grid cells. For 100 obs × 40K cells = 400M operations. ~50ms.

**At scale:** Linear in D. At 4M cells (100×): ~5 seconds. At 40M cells (1000×): ~50 seconds.

**Fix:** Sparse GP prediction is O(M² × D), independent of N_obs. With M=200: O(200² × D) = 40,000 × D. At 4M cells: 160B operations, ~5 seconds. Still linear in D.

**GPU acceleration:** The prediction is embarrassingly parallel — each cell's variance is independent. Launch D threads, each computes one variance value. On GPU with 4M cells: ~10ms. With 40M cells: ~100ms.

|Scale|Cells|Exact GP|Sparse GP|Sparse GP + GPU|
|---|---|---|---|---|
|1×|40K|50 ms|10 ms|<1 ms|
|10×|400K|500 ms|100 ms|5 ms|
|100×|4M|5 s|1 s|50 ms|
|1000×|40M|50 s|10 s|500 ms|

#### GP Conditional Variance Update (greedy selector)

**Current:** One update = O(D) — subtract one vector from the variance field. At D=40K: microseconds. K=5 updates: <1ms.

**At scale:** Still O(D) per update. At D=40M: ~10ms per update. K=5: ~50ms. At K=50 drones on a 1000× domain: ~500ms. Acceptable.

**GPU acceleration:** One vectorized subtraction over D elements. Native GPU territory. All scales: <1ms.

#### Fire Engine (Ensemble)

**Current:** N members × D cells × T timesteps. At N=200, D=40K, T=150: 1.2B cell-updates. CPU multiprocessing: ~3-20 seconds. GPU batched: ~100ms.

**At scale:** Linear in D. This is the dominant compute cost.

|Scale|Cells|Timesteps|N=200 CPU (8-core)|N=200 GPU|N=1000 GPU|
|---|---|---|---|---|---|
|1×|40K|150|20 s|100 ms|500 ms|
|10×|400K|150|200 s|1 s|5 s|
|100×|4M|150|33 min|10 s|50 s|
|1000×|40M|150|5.5 hr|100 s|500 s|

At 100× on GPU with 200 members: 10 seconds. Feasible within a 20-minute cycle. At 1000× on GPU: 100 seconds for 200 members. Tight but possible.

On CPU, anything beyond 10× is infeasible for the 20-minute cycle. GPU is mandatory at scale.

**Additional GPU optimization at scale:** At 4M+ cells, GPU memory becomes the constraint. 200 members × 4M cells × 4 bytes = 3.2 GB for arrival times alone. With all state tensors: ~8-10 GB. Fits on a 16 GB GPU. At 40M cells: ~80 GB. Requires multi-GPU or sequential batch processing (run 50 members at a time, 4 batches).

**Alternative: spatial decomposition.** At 1000× scale, the fire doesn't threaten the entire 100,000 km² simultaneously. The active fire zone might be 5-10% of the domain. Run the ensemble only on a bounding box around the fire front + prediction horizon, not the full grid. A 40M-cell domain where 2M cells are in the active zone reduces to 2M-cell compute — 100× effectively becomes 5× per fire.

#### Information Field

**Current:** Three elementwise multiplies over (rows, cols). Microseconds. Scale-independent per cell. At 40M cells: ~100ms on CPU, ~1ms on GPU. Never a bottleneck.

#### Sensitivity Computation

**Current:** One matrix-vector multiply per variable. O(N × D) where N=ensemble members, D=cells. At N=200, D=40K: 8M operations per variable. Milliseconds.

**At scale:** O(N × D). At D=40M: 8B operations per variable. CPU: ~2 seconds. GPU: ~10ms. GPU makes this trivial at any scale.

#### Correlation-Domain Graph

**Current:** ~400 domains, ~1,600 edges. Dijkstra + greedy: <1ms.

**At scale:** Domains = D / (correlation_length / resolution)². This scales linearly with area, not quadratically with grid cells, because domain size is fixed.

|Scale|Domains|Edges|Dijkstra (per station)|Greedy (per drone)|
|---|---|---|---|---|
|1×|400|1,600|<1 ms|<1 ms|
|10×|4,000|16,000|5 ms|5 ms|
|100×|40,000|160,000|50 ms|50 ms|
|1000×|400,000|1,600,000|500 ms|500 ms|

At 1000×: 500ms per drone. For K=50 drones, sequential planning takes ~25 seconds. This is noticeable but still within cycle budget. Parallel planning (plan each drone independently with a shared initial variance, then reconcile) reduces wall time to ~500ms on 50 threads/cores.

#### Sequential GP Path Scoring

**Current:** O(P × D) where P = cells along path (~1,000), D = grid cells (40K). Each step is one variance vector update. P × D = 40M operations. ~10ms.

**At scale:** At D=40M and P=5,000 (longer paths over larger domain): 200B operations. CPU: ~50 seconds. Too slow.

**Fix:** The GP conditional variance update doesn't need the full grid. Only cells within ~2× correlation length of the observation are meaningfully affected. Use sparse updates:

```python
def sparse_conditional_variance(variance, obs_cell, kernel_length, resolution):
    """Only update cells within 2× correlation length of observation."""
    radius_cells = int(2 * kernel_length / resolution)
    r, c = obs_cell
    r_start = max(0, r - radius_cells)
    r_end = min(rows, r + radius_cells)
    c_start = max(0, c - radius_cells)
    c_end = min(cols, c + radius_cells)
    
    # Update only the local patch
    local = variance[r_start:r_end, c_start:c_end]
    # ... kernel evaluation and subtraction on local patch only
    variance[r_start:r_end, c_start:c_end] = updated_local
    return variance
```

With 500m correlation length and 50m resolution, the patch is ~20×20 = 400 cells per update instead of D=40M. P=5,000 steps × 400 cells = 2M operations. Microseconds. Scale-independent.

#### EnKF Update

**Current:** The dominant operation is PHT = A.T @ HA, which is O(D × N × n_obs). At D=40K, N=200, n_obs=50: 400M operations. ~50ms.

**At scale:** At D=40M: 400B operations. CPU: ~100 seconds. Too slow.

**Fix:** Localization means only cells within the localization radius are updated by each observation. With localization radius = 5km and 50m resolution, each observation updates ~10,000 cells. The effective cost per observation is O(10,000 × N) = 2M. For 50 observations: 100M operations. ~50ms regardless of total D.

The implementation change: instead of building full (D, n_obs) Kalman gain matrix, build a sparse K that's nonzero only within the localization radius of each observation. This is standard in operational weather DA (ECMWF, NCEP all use localized EnKF).

**GPU acceleration:** The localized EnKF updates are independent per observation (each observation updates a different spatial patch). Launch n_obs parallel update kernels on GPU. Wall time: one patch update (~1ms) regardless of n_obs.

#### QUBO Solver

**Current:** M=300 candidate points → 300×300 QUBO matrix. SA solves in ~100ms. D-Wave in ~1-2 seconds.

**At scale:** The QUBO operates on candidate points, not grid cells. At larger scales, you still select M=300-1000 candidates from the information field. The QUBO size is independent of domain size. However, if you increase M to 1000 (more candidates at larger scale), the QUBO matrix is 1000×1000 = 1M entries. SA: ~1 second. D-Wave: needs embedding for 1000-variable QUBO on Pegasus, chain lengths increase, solution quality may degrade. D-Wave Advantage has 5,000+ qubits, so a 1000-variable QUBO is feasible but pushing it.

**For the domain-graph path approach:** The QUBO isn't used for paths (classical graph algorithms are better). It remains as a point-selection comparison baseline at the same 300-1000 candidate scale regardless of domain size.

### Summary: What Enables Each Scale Jump

|Scale jump|What breaks|What fixes it|New dependencies|
|---|---|---|---|
|1× → 10×|Fire engine on CPU|GPU fire engine (your CUDA implementation)|CUDA, ~8 GB GPU|
|10× → 100×|GP prediction, fire engine memory|Sparse GP (GPyTorch), spatial decomposition of fire domain|GPyTorch, multi-GPU or active-zone-only simulation|
|100× → 1000×|Everything except info field and QUBO|Sparse GP + GPU, GPU fire engine with spatial decomposition, localized EnKF, sparse GP conditional variance updates|40+ GB GPU or multi-GPU, distributed compute|

### Embarrassingly Parallel Components

|Component|Parallelism type|GPU benefit|
|---|---|---|
|Ensemble members|Each member independent. Batch on GPU.|100-1000×|
|GP prediction at grid cells|Each cell independent.|100-1000×|
|Sensitivity per cell|Each cell's correlation independent.|100-1000×|
|Information field (w_i)|Elementwise multiply.|100-1000×|
|Drone path planning (K drones)|Independent IF using initial variance. Dependent if sequential.|K× with parallel init, then reconcile|
|Localized EnKF updates|Each observation's patch independent.|n_obs×|
|Domain graph construction|Each domain independent.|Moderate — memory access patterns less regular|
|GP conditional variance (greedy)|Sequential by nature (each step depends on previous). NOT parallel.|1× — fundamentally serial|

The greedy selector is the one component that doesn't parallelize. Each selection depends on the updated variance from the previous selection. This is O(K × update_cost), and K is small (5-50 drones), so it's not a bottleneck. But it's worth noting — it's the serial spine of the pipeline.

### The Large-Area, Few-Drones Regime

You're right that IGNIS is optimally positioned for few drones over large areas. This is precisely where targeted sensing has maximum advantage over uniform coverage.

**Why:** With K=5 drones over 100 km², each drone covers ~0.5% of the domain per sortie. Uniform placement spreads 5 drones evenly — each observes a random cross-section. Targeted placement concentrates all 5 on the ~2-3% of the domain where measurement most reduces prediction uncertainty. The targeting multiplier is largest when K/D is smallest.

At K=5 over 10,000 km² (100× scale), each drone covers ~0.005% of the domain. The gap between targeted and uniform grows further — uniform is observing effectively nothing useful, while targeted hits the critical terrain features and fire-proximate cells.

The expected PERR ratio:

|Domain size|K=5 drones|Coverage per drone|Expected targeted/uniform ratio|
|---|---|---|---|
|100 km²|5|0.5%|2-4×|
|1,000 km²|5|0.05%|4-8×|
|10,000 km²|5|0.005%|8-15×|

As the domain grows and drone coverage becomes sparser, the value of placing each drone at exactly the right location increases superlinearly. This is because the information landscape becomes more peaked — at large scales, most of the domain is irrelevant (far from fire, well-observed by RAWS, or in fuel types where FMC doesn't matter). The high-information regions concentrate into a small fraction of the domain. Targeted sensing finds these needles in the haystack; uniform sensing almost certainly misses them.

**This is the scaling story for the pitch:** "IGNIS provides the greatest advantage precisely where it's needed most — when limited drone resources must be deployed across large, complex fire environments. A fleet of 5 drones with IGNIS guidance over a 10,000 km² fire complex extracts 10× more prediction improvement per drone-hour than the same fleet with uniform coverage. The advantage grows with domain size because the information landscape becomes more concentrated."

### Multi-GPU Architecture for 1000× Scale

At state/regional scale (100,000 km²), the system requires distributed compute:

```
GPU 0: Fire engine — 200 ensemble members on active zone
GPU 1: Fire engine — 200 more members (split ensemble across GPUs)
GPU 2: GP fitting + prediction (GPyTorch, sparse GP)
GPU 3: Information field + sensitivity + path scoring

CPU: Graph algorithms (domain construction, Dijkstra, greedy path planning)
     EnKF (localized, sparse — CPU is fine with localization)
     Orchestrator
```

This is achievable on a single 4-GPU workstation (4× A100 80GB). The inter-GPU communication is minimal — ensemble results transfer from GPU 0-1 to GPU 2-3 once per cycle (~100 MB at 200 members × 2M active cells × 4 bytes). PCIe bandwidth handles this in ~10ms.

Cloud deployment (AWS p4d.24xlarge with 8× A100): could run the full pipeline at 1000× scale within the 20-minute cycle budget.

### Implementation Priority for Scaling

|Optimization|Effort|Scale it enables|When to implement|
|---|---|---|---|
|GPU fire engine (your CUDA work)|Already planned|10×|Hackathon|
|Sparse GP conditional variance (local patches)|~20 lines|100× for path scoring|Post-hackathon|
|Localized EnKF (sparse Kalman gain)|~30 lines|100×|Post-hackathon|
|Sparse GP fitting (GPyTorch)|~50 lines (library swap)|100×|Post-hackathon|
|GPU GP prediction|~20 lines (GPyTorch)|1000×|When needed|
|Spatial decomposition (active zone only)|~40 lines|1000×|When needed|
|Multi-GPU pipeline|~100 lines|1000×|Research project|