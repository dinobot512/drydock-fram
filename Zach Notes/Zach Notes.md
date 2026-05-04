ASA's history of contributions to wildfire and other disaster management efforts includes remote sensing, instrumentation, mapping, data fusion, and prediction.
 Current applications of aviation to wildfire management include deployment of smoke jumpers to a fire; transport of firefighters, equipment, and supplies; fire retardant or water drop; reconnaissance of fire locations and fire behavior; and supervision of air tactical operations.

The Phase I outcome should establish the scientific, technical, and commercial feasibility of the proposed innovation in fulfillment of NASA objectives and broader aviation community needs. Phase I should demonstrate advancement of a specific technology or technique, supported by analytical and/or experimental studies that are documented in final report

We need:
- Software for modelling
Consequently, Phase II efforts are strengthened when they include a partnership with a potential end-user of the technology

QUESTIONS:
- multi-modality...? How to combine disparate data? 
- Characterize computational requirements 

Important data:
- FMC (fuel moisture content)
- wind speed / direction / flow
- Add Myopic replanning
- Ensure the EnKF update uses localization

Measurements have different densities:
- FMC cameras can update across swathes of grid tiles while anemometer only gives point data so current tiles. 


**1. How to calibrate τ (temporal degradation rate) — not arbitrary, physically grounded**

The fire science literature gives you τ directly. It's called the "timelag" and it's one of the most studied quantities in fire weather. Dead fuels are classified by their timelag:

- **1-hour fuels** (fine twigs, grass): reach 63% of equilibrium moisture in ~1 hour. τ ≈ 1 hour.
- **10-hour fuels** (small branches): τ ≈ 10 hours.
- **100-hour fuels** (larger branches): τ ≈ 100 hours.

The Nelson model (2000), used operationally in the US National Fire Danger Rating System, computes diurnal FMC variation from hourly weather observations. It explicitly models how FMC drifts from a measured value back toward equilibrium over time, driven by temperature, humidity, and solar radiation. The timelag IS the temporal correlation parameter for your GP.

For wind, the autocorrelation is much shorter. Surface wind speed decorrelates on timescales of 10-30 minutes in complex terrain (gusts, channeling effects). Wind direction can shift in seconds during fire-driven convection events but has longer autocorrelation under stable synoptic conditions (~1-3 hours).

So the GP temporal kernel parameters aren't tunable hyperparameters you optimize — they're physical constants of the fuel class and atmospheric regime:

python

```python
tau = {
    "fmc_1hr": 1.0,      # hours
    "fmc_10hr": 10.0,     # hours  
    "wind_speed": 0.5,    # hours (conservative for complex terrain)
    "wind_direction": 1.0  # hours (stable conditions)
}
```

You can also let the GP learn τ from data by including it as a kernel hyperparameter and fitting to RAWS time series. RAWS stations report hourly, giving you direct empirical temporal autocorrelation for each variable at each station. This is a one-time calibration step — fit the temporal kernel to a few days of RAWS data, extract τ per variable, use those values in your operational GP.


Drone 


To do:
- How are past fire measuremnts and current measurements integrated?  
- From the ensemble, selecting 

- Build in Dino's Fire Simulation code

- Information field?? Right now it seems to just be a binary? It should be more granular and uncertain. 

- Add real topography and initial prior data etc. Proper prior and ground truth loading. Better simulation candidates. 

- Get an opus agent to check what the current code is implementing and outline what needs to be fixed or adjusted. Compare it to the v3 and see how different it is.  
- Update path finding so single drones visit multiple points


 The main entry point is scripts/run_sim.py. It wires together all the components:                

    - **angrybird/simulation/scenarios.py** — terrain + ground truth factories (e.g. hilly_heterogeneous)                                    

    - **scripts/demo_sim.py** — SimpleFire (the fire engine) and make_gp helper                                                              

    - **angrybird/gp.py** — IGNISGPPrior (FMC + wind estimation)                                                                             

    - **angrybird/orchestrator.py** — IGNISOrchestrator (sequences the IGNIS cycle: GP → ensemble → info field → select → assimilate)

    - **angrybird/simulation/runner.py** — SimulationRunner (the clock loop: moves drones, collects observations, triggers IGNIS cycles,

    renders frames)

    Run it with:

    python scripts/run_sim.py --scenario hilly_heterogeneous --hours 2




Missing:
- Wind pertubation 
- Current fire? 
	- Estimation 


# To do:
- 



## Data types:

- Where is terrain data recieved from? 

GPPrior:
- How does current fire position itnerface with the GP Prior? 

**IMPORTANT**: Add wind direction to:
- Ensemble result
- Information field (direction should have uncertainty and sensitivity)

Add generic Observation data class:
- Specifics for different types
- RAWS, drone, Sat, what else...?
- Add RAWS replacement frequency...? 
	- Just there should be one RAWS data, and 
	- Hashmap of RAWS? If exists just replace old one, otherwise add new RAWS. 

This includes:
- Hashmap of Unique RAWS towers
- List of drone observations (prune upon every merge / decay application) 
- 

Drone Observation:
- time
- types of FMC or no? (types just effect how FMC propagates?).

Mission request:
- Useful or unused? 
DronePlan:
- Unused
- Implement pathfinding
- Combine with above?

Strategy Evaluation:
- Move to subclass

CycleReport: 
- Add a GPPrior
- Add information field
- Add selection result

## Config
Remove time step (deprecate) (is this True???)
Remove Observation Noise
Review GP hyper parameters
Review EnKF
Review / implement replan triggers 

Raws frequency: 
- Only need to add if Hash Map with live update isn't used.
- Satellite paremeters? 

BIG QUESTIONS:
- What are all other modalities of observation?
	- E.g Satellite, others?? 
	- Weather Forecast
	- Specific limitations or confinements of observation types and specific data 



TODO:
- Add Windspeed 
- Add terrain data loading


- Refactor observations to generic observation class. There should be an observation container class that has: a hash map of Unique RAWS towers. Each is identified by a unique ID that should be related to real identifiers for RAWS. There should be a list of drone observations (a list? What makes most sense for the type? This should be )
	- This class should be interacted from other classes. 
	- It should store each observation type in a unique corresponding structure (e.g RAWs are hashmaps because new data will override old data);
	- It should have functions such as: return decayed, or prune, which calls individual general functions for each observation within the data structure.
	- Observation should be a generic dataClass. Differnet observation types extend this, but override the decay methods. Each container stores these observations. 
	- Also methods to add new observations as soon as they arrive (tho this shiuld probably be locked when a prior creation is initiated within a cycle so that observations midway don't mess with it)
	- What else should this class have? 
- 
- Plug in REAL FireSim 
	- What exact data is passed to FireSim and out of it? 
	- Right now we just have a basic simulation 
	- We need to plug into the real ElmFire simulation or our rewrite of it
	- And plug into a GPU accelerated version 
- Agent: Review Dino code Tigetter


### ONGOING:
- Agent: Review Dino code Tigetter

- Refactor observations to generic observation class. There should be an observation container class that has: a hash map of Unique RAWS towers. Each is identified by a unique ID that should be related to real identifiers for RAWS. There should be a list of drone observations (a list? What makes most sense for the type? This should be )
- Add terrain data loading


## Done:
- Add wind direction