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
