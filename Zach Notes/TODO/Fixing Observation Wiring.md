Sure. Here's a concise inventory of the real discrepancies between the spec and the implementation:

---

**1. Two parallel buffer systems doing the same job**

- `IngestionBuffer` (in `observations.py`) — implemented, wired to nothing. Designed for thread-safe staging when the store is locked.
- `ObservationBuffer` (in `simulation/observation_buffer.py`) — what's actually used everywhere. Handles thinning + accumulation.
- These overlap substantially. `IngestionBuffer` is dead code.

**2. Three separate thinning implementations**

- `ObservationBuffer.flush_thinned()` → `thin_observations()` — runs before observations enter the store
- `ObservationStore._thin()` → inside `get_data_points(min_spacing_cells=...)` — runs at query time
- `aggregate_drone_observations()` in `assimilation.py` — runs at cycle assimilation time
- The spec intends thinning to live in one place (the store query). Currently observations are thinned twice before the GP sees them.

**3. `lock()` / `unlock()` implemented but never called**

- `ObservationStore.lock()` / `unlock()` exist and raise on violation, but nothing in the orchestrator or runner calls them. The spec's orchestrator integration example wraps the whole cycle in `lock()`/`finally: unlock()`.

**4. `fit()` called twice per `predict()` in the orchestrator**

- `orchestrator.run_cycle()` now calls `gp.fit(start_time)` explicitly, then `gp.predict(shape)`, which itself calls `fit(self._current_time)` again. Redundant but harmless — the second fit just re-reads the store with the same time.

**5. `types.DroneObservation` vs `observations.DroneObservation` — two classes, same name**

- `types.DroneObservation` is the raw telemetry struct (from SimulatedObserver)
- `observations.DroneObservation` is the store observation class
- Everywhere they coexist, one is aliased as `DroneObs`. Confusing and fragile.

**6. Old-API compat detection in `assimilate_observations()` uses type-sniffing**

- The function inspects whether arg 2 is an `ObservationStore` or `EnsembleResult` to decide which calling convention was used. This is a hack that should be removed once the tests are updated to the new signature.

**7. LiveEstimator forks the store rather than reading from the buffer**

- The spec intends the live estimate to read from main store + `IngestionBuffer` (pending obs)
- The actual implementation deep-copies the GP and its store, adds buffer observations to the copy, and predicts from that
- Functionally equivalent but more expensive and bypasses the intended buffer abstraction

**8. `prune()` called outside the lock**

- `_run_ignis_cycle()` calls `obs_store.prune(current_time)` before acquiring the lock. The spec shows pruning inside the lock to avoid a race where an observation arrives between prune and cycle computation.