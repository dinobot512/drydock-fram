
FlamMap - existing wildfire propagation simulator
https://research.fs.usda.gov/firelab/products/dataandtools/flammap

Data that FlamMap uses - has a bunch of geospatial data 
https://www.landfire.gov/

Mathematical Models
- Rothermel's (1972) surface fire spread model,
- Van Wagner's (1977) crown fire initiation model,
- Rothermel's (1991) crown fire spread model,
- Albini's (1979) spotting model,
- Finney’s (1998) or Scott and Reinhardt’s (2001) crown fire calculation method, and
- Nelson's (2000) dead fuel moisture model. This allows conditioning of dead fuels in each pixel based on slope, shading, elevation, aspect, and weather.


COMMS BLACKOUTS DURING FIRES RESEARCH:

2023 Maui fires — a telecommunications blackout kept many residents in the dark, hampering both evacuation orders and first responders' emergency communications. All cellphones and landlines in Lahaina went down, along with commercial electrical service for days. [Chronicle Journal](https://www.chroniclejournal.com/business/national_business/no-network-is-flawless-wildfires-underscore-resiliency-challenges-for-telecoms/article_bf9b90d0-a193-5472-aa69-48b7ba4ccad4.html)

More broadly, firefighters often find themselves in remote locations with unreliable connectivity. In a communication blackout, teams risk isolation — conveying critical information like changes in fire behavior, team locations, or urgent resource requests becomes nearly impossible. [3AM Innovations](https://3aminnovations.com/post/navigating-the-threat-of-communication-blackout-on-the-fireground/)

The FCC has also acknowledged this, noting that wildfires can cause damage to wireline and mobile communications systems, making it difficult to communicate about fast-changing fire conditions, and that informal ad-hoc networks can play an important role when traditional methods aren't available. [Federal Communications Commission](https://www.fcc.gov/wildfire-communications-advisory)


EXISTING SOLUTIONS:

1. HetNet
https://arxiv.org/pdf/2508.16761
   incorporates LEO satellites, high (HAPS) and low altitude (LAPS) drones into a single robust network
2. NASA PAMS
https://ntrs.nasa.gov/api/citations/20250005969/downloads/20250005969_Aviation2025.pdf
- field test demonstrated feasibility of coordinated drone operations (~90% transmission success rate) but needs refining to improve connectivity, ground station management, and decrease latency.


FIRE SPREAD MODEL

C2FK
https://github.com/fire2a/C2FK

