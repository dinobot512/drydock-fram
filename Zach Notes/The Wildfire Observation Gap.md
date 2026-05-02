## What fire models need

Fire spread prediction is dominated by two input variables. Fuel moisture content (FMC) controls whether fire spreads at all and how intensely — a 10% change in FMC can produce up to 1,200% change in predicted rate of spread (Jolly 2007). Local wind fields determine direction and speed of spread. Both vary at spatial scales of 100m–1km, driven by terrain features (ridgelines, valleys, aspect, canopy cover) and shift on timescales of minutes to hours.

Models need these variables at the resolution of the landscape features that drive them — hundreds of meters, updated sub-hourly — to produce operationally useful predictions.
## What fire models actually get

**Ground stations:** ~2,200 RAWS stations serve the entire United States, with the BLM maintaining ~1,700 units. Average spacing in the fire-prone western US is approximately 50 km, with spacing exceeding 80 km in remote mountainous terrain. Most stations are sited for regional fire danger rating, not to coincide with active fire incidents — meaning zero to one stations typically fall within any given fire perimeter. Only 75 portable Incident RAWS (IRAWS) exist for deployment to active fires nationwide. Data is relayed hourly via GOES satellite. FMC is estimated from a single 10-hour fuel moisture stick per station, extrapolated via inverse-distance interpolation to every point in between.

**Satellites:** MODIS/VIIRS active fire detection provides fire _location_ (not FMC or wind) at 375m–1km resolution. Polar-orbiting overpasses occur 2–4 times per day. GOES geostationary provides more frequent coverage but at 2km resolution with significant cloud and smoke interference. No current satellite product delivers the sub-kilometer, sub-hourly FMC or wind data that fire models need.

**Aerial reconnaissance:** Manned aircraft provide visual intelligence during daytime operations only. Flights are intermittent, not instrumented for quantitative FMC measurement, and must be suspended when suppression aircraft are active in the same airspace.

## The gap

Fire behavior varies at 100m scales on minute timescales. Observations exist at 30–50 km scales on hourly timescales. Everything in between — which is where fire models actually need data — is interpolation, assumption, and lookup tables. The prediction system is not model-limited; it is data-limited. The most sophisticated fire model in the world, fed interpolated data from a station 40 km away, cannot predict what a fire will do when it hits a terrain feature that changes fuel moisture and wind in ways the distant station cannot see.

## What targeted drone sensing provides

A fleet of 5–10 drones operating within an active fire incident can collect quantitative FMC (multispectral, R² ~ 0.86) and wind measurements at 20–25 locations per hour across a fire area. Compared to the regional RAWS density of ~1 station per 2,500 km², this represents roughly a 500× increase in data density within the operational area (~2.5 orders of magnitude). But the operationally meaningful comparison is starker: within a typical fire perimeter, current in-situ observations are effectively zero — the nearest RAWS is 20–50 km away. Drones provide 20–25 spatially distributed measurements per hour where none existed before. The shift is not incremental improvement; it is from interpolation to observation. Even uniform drone coverage would transform the data input to fire models. Information-theoretic targeting — routing drones to locations where measurement most reduces predictive uncertainty — extracts maximum value from each flight hour.

## References

- NIFC / Wildland Fire Application Information Portal. "There are nearly 2,200 interagency Remote Automatic Weather Stations (RAWS) strategically located throughout the United States." BLM Remote Sensing Unit maintains ~1,700 units annually, plus 75 portable IRAWS deployable to incidents nationwide.
- Jolly, W.M. (2007). Sensitivity of a surface fire spread model and associated fire behaviour fuel models to changes in live fuel moisture. _International Journal of Wildland Fire_. [10% FMC change → up to 1,200% ROS change]
- Vejmelka, M., Kochanski, A.K., Mandel, J. (2014). Data assimilation of dead fuel moisture observations from remote automated weather stations. [RAWS described as "spatially sparse"; TSM needed to estimate FMC at "locations potentially distant from observational stations"]
- Yebra, M. et al. (2013). A global review of remote sensing of live fuel moisture content for fire danger assessment. _Remote Sensing of Environment_. [Field sampling is locally accurate but not scalable; satellite products provide 250m–33km resolution with revisit times of days]
- NASA SBIR Solicitation FY2025, Subtopic: Nontraditional Aviation Operations for Wildfire Response. ["Surveillance images are captured and disseminated only every 4 hours"; "Intermittent communication can delay effective response"]
- UAV multispectral FMC estimation: Forests (2023), UAV multispectral imagery predicts dead fuel moisture content [deep learning on multispectral imagery]; ResearchGate (2023), LFMC estimation with Phantom 4 Multispectral + Random Forest, R² = 0.86 using VNIR bands.