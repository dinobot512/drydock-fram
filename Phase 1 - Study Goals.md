---
id: Phase 1 - Study Goals
aliases: []
tags: []
---

##### 1. Terrain & Environment Characterization Study

- [ ] **1.1 Wildfire-Prone Terrain Taxonomy**
    - Categorize terrain types: coastal chaparral, mountain/canyon, high desert plateau, forested ridge, urban-wildland interface
    - For each: typical slope gradients, elevation ranges, vegetation density, historical fire frequency
- **1.2 Communications Performance by Terrain Type**
    - RF propagation analysis (line-of-sight blockage, multipath) for each terrain class
    - Performance characterization by comm type: cellular LTE/5G, satellite (Starlink, Iridium), 900 MHz radio, 4.9 GHz public safety band, mesh radio
    - Quantify: dropout frequency, latency under load, range limits, degradation under smoke/atmospheric ducting
    - Output: terrain-comm compatibility matrix with red/yellow/green ratings
- **1.3 GPS Degradation Mapping**
    - Canyon/valley masking effects on GPS constellation geometry (PDOP degradation)
    - Identify terrain classes where GPS-dependent autonomous operations are unreliable
    - Candidate alternative PNT sources: inertial, visual odometry, terrestrial ranging

---

##### 2. Existing UAS Systems Survey

- **2.1 Platform Inventory**
    - Fixed-wing vs. multirotor vs. VTOL — endurance, payload capacity, operational ceiling
    - Systems currently deployed or trialed in wildfire ops (e.g., AeroVironment Vapor, General Atomics Predator B/FireGuard, senseFly eBee)
- **2.2 Terrain-Platform Mapping**
    - Which platforms are operationally validated in which terrain classes
    - Minimum safe operating altitude by terrain type
- **2.3 Communications Architecture of Existing Systems**
    - What datalinks each system uses (C2 link, payload downlink, UTM connectivity)
    - Whether onboard processing exists or all processing is ground-side
- **2.4 Capability Gap Analysis**
    - Night operation capability (IR sensor integration)
    - Degraded comms behavior — does the platform hold position, return to home, or continue mission?
    - Integration status with any existing UTM or airspace coordination system

---

##### 3. Existing UTM Algorithms & Standards Review

- **3.1 Algorithm & Protocol Inventory**
    - ASTM F3548 UTM standard — current capabilities and assumptions
    - Strategic deconfliction (pre-flight) vs. tactical deconfliction (in-flight) approaches
    - Specific algorithms: geofencing enforcement, dynamic resegmentation, intent-based separation, detect-and-avoid (DAA)
- **3.2 Failure Mode Analysis**
    - Terrain-induced failures: LOS blockage breaking ground-to-UAS C2, geofence updates not reaching aircraft in canyon
    - Weather-induced failures: convective turbulence invalidating planned corridors faster than replanning cycle
    - Scale failures: algorithm latency vs. number of simultaneous aircraft — at what fleet size does coordination degrade?
    - Connectivity-assumption failures: what happens when the UTM ground server loses contact with one or more aircraft
- **3.3 Performance Benchmarking**
    - Replanning latency for dynamic geofence updates across candidate algorithms
    - Separation assurance success rate under high-density, dynamic airspace scenarios
    - Identify which algorithms have open-source implementations or published validation data
- **3.4 Suitability Scoring**
    - Rate each algorithm/protocol against wildfire-specific requirements: disconnected operation, dynamic perimeter, mixed crewed/uncrewed traffic, night ops

---

##### 4. Novel Algorithm Concepts

- **4.1 Distributed/Onboard Deconfliction**
    - Concepts for conflict detection and resolution that execute onboard without continuous ground server connectivity
    - Evaluate: velocity obstacle methods, ORCA (Optimal Reciprocal Collision Avoidance), onboard intent broadcasting
- **4.2 Dynamic Airspace Resegmentation**
    - Algorithms that ingest fire perimeter updates and automatically regenerate operational volumes in near-real-time
    - Triggering logic: how large a perimeter change warrants a full replan vs. local adjustment
- **4.3 Priority & Preemption Schemes**
    - How the algorithm handles a water drop tanker (safety-critical, crewed) vs. a surveillance UAS (expendable, uncrewed) competing for the same corridor
    - Incident command hierarchy mapping to airspace priority levels
- **4.4 Concept Downselect**
    - Score concepts against: computational feasibility onboard, latency, safety assurance tractability, compatibility with existing ASTM standards
    - Select 1–2 concepts for prototype development in Phase II
