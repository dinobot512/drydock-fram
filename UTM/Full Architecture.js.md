const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  TableOfContents, UnderlineType
} = require('docx');
const fs = require('fs');

// ─── Color palette ───────────────────────────────────────────────────────────
const C = {
  navy:      "1B3A5C",
  blue:      "2E75B6",
  lightBlue: "D5E8F0",
  midBlue:   "BDD7EE",
  orange:    "C55A11",
  green:     "375623",
  lightGray: "F2F2F2",
  midGray:   "D9D9D9",
  darkGray:  "595959",
  white:     "FFFFFF",
  black:     "000000",
  accent:    "E8F4FC",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
const border = (color = C.midGray) => ({ style: BorderStyle.SINGLE, size: 1, color });
const cellBorders = (color = C.midGray) => ({
  top: border(color), bottom: border(color),
  left: border(color), right: border(color)
});
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function hRule(color = C.blue, thickness = 6) {
  return new Paragraph({
    spacing: { before: 0, after: 0 },
    border: { bottom: { style: BorderStyle.SINGLE, size: thickness, color, space: 1 } },
    children: [],
  });
}

function spacer(pts = 120) {
  return new Paragraph({ spacing: { before: 0, after: pts }, children: [] });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: C.navy })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 100 },
    children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: C.blue })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 24, bold: true, color: C.navy })],
  });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 0, after: 160 },
    children: [new TextRun({
      text,
      font: "Arial",
      size: opts.size || 22,
      bold: opts.bold || false,
      italics: opts.italic || false,
      color: opts.color || C.black,
    })],
  });
}

function bullet(text, level = 0, ref = "bullets") {
  return new Paragraph({
    numbering: { reference: ref, level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Arial", size: 22 })],
  });
}

function numbered(text, level = 0) {
  return bullet(text, level, "numbers");
}

function codeBlock(lines) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: cellBorders(C.midGray),
            width: { size: 9360, type: WidthType.DXA },
            shading: { fill: "F4F4F4", type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 180, right: 180 },
            children: lines.map(line =>
              new Paragraph({
                spacing: { before: 0, after: 0 },
                children: [new TextRun({ text: line, font: "Courier New", size: 18, color: "1A1A1A" })],
              })
            ),
          }),
        ],
      }),
    ],
  });
}

function infoBox(title, lines, fillColor = C.lightBlue, borderColor = C.blue) {
  const rows = [];
  // Header row
  rows.push(new TableRow({
    children: [new TableCell({
      borders: cellBorders(borderColor),
      width: { size: 9360, type: WidthType.DXA },
      shading: { fill: borderColor, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 160, right: 160 },
      children: [new Paragraph({
        children: [new TextRun({ text: title, font: "Arial", size: 22, bold: true, color: C.white })],
      })],
    })],
  }));
  // Body rows
  lines.forEach(line => {
    rows.push(new TableRow({
      children: [new TableCell({
        borders: cellBorders(borderColor),
        width: { size: 9360, type: WidthType.DXA },
        shading: { fill: fillColor, type: ShadingType.CLEAR },
        margins: { top: 60, bottom: 60, left: 160, right: 160 },
        children: [new Paragraph({
          spacing: { before: 0, after: 0 },
          children: [new TextRun({ text: line, font: "Arial", size: 21 })],
        })],
      })],
    }));
  });
  return new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [9360], rows });
}

function twoColTable(headers, rows, widths = [2400, 3480, 3480]) {
  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      borders: cellBorders(C.blue),
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: C.navy, type: ShadingType.CLEAR },
      margins: cellMargins,
      children: [new Paragraph({
        children: [new TextRun({ text: h, font: "Arial", size: 20, bold: true, color: C.white })],
      })],
    })),
  });
  const dataRows = rows.map((row, ri) => new TableRow({
    children: row.map((cell, ci) => new TableCell({
      borders: cellBorders(C.midGray),
      width: { size: widths[ci], type: WidthType.DXA },
      shading: { fill: ri % 2 === 0 ? C.white : C.lightGray, type: ShadingType.CLEAR },
      margins: cellMargins,
      children: [new Paragraph({
        spacing: { before: 0, after: 0 },
        children: [new TextRun({ text: cell, font: "Arial", size: 20 })],
      })],
    })),
  }));
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: widths,
    rows: [headerRow, ...dataRows],
  });
}

// ─── Cover page ───────────────────────────────────────────────────────────────
function coverPage() {
  return [
    spacer(1440),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 80 },
      children: [new TextRun({ text: "IGNIS", font: "Arial", size: 72, bold: true, color: C.navy })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 240 },
      children: [new TextRun({ text: "Integrated Ground-Networked Intelligent UAS System", font: "Arial", size: 30, color: C.blue })],
    }),
    hRule(C.orange, 8),
    spacer(200),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 120 },
      children: [new TextRun({ text: "Full System Architecture Documentation", font: "Arial", size: 28, bold: true, color: C.darkGray })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 80 },
      children: [new TextRun({ text: "NASA SBIR Phase I — Nontraditional Aviation Operations for Wildfire Response", font: "Arial", size: 22, italics: true, color: C.darkGray })],
    }),
    spacer(80),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 40 },
      children: [new TextRun({ text: "Version 1.0  |  May 2026", font: "Arial", size: 22, color: C.darkGray })],
    }),
    spacer(1200),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "CLASSIFICATION: UNCONTROLLED // FOR OFFICIAL USE", font: "Arial", size: 18, bold: true, color: C.orange })],
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ─── Document sections ────────────────────────────────────────────────────────

const tocSection = [
  h1("Table of Contents"),
  new TableOfContents("Table of Contents", {
    hyperlink: true,
    headingStyleRange: "1-3",
    stylesWithLevels: [
      { styleName: "Heading 1", level: 1 },
      { styleName: "Heading 2", level: 2 },
      { styleName: "Heading 3", level: 3 },
    ],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 1: Executive Summary ────────────────────────────────────────────
const execSummary = [
  h1("1. Executive Summary"),
  hRule(),
  spacer(80),
  para("IGNIS (Integrated Ground-Networked Intelligent UAS System) is an end-to-end drone management and fire prediction platform designed for wildland fire operations. It integrates three major capabilities into a unified, field-deployable system:"),
  bullet("An adaptive fire prediction engine (ELMFIRE ensemble + Gaussian Process uncertainty quantification) that continuously updates probabilistic fire spread forecasts."),
  bullet("A drone fleet management layer that optimally tasks a limited number of UAS to resolve fire model uncertainty in the locations that most affect predicted fire behavior."),
  bullet("A communications mesh architecture that simultaneously provides sensor coverage, airborne relay connectivity, and real-time situational awareness to ground crews."),
  spacer(80),
  para("The system is designed to operate in the austere connectivity environments characteristic of wildland fire incidents — remote terrain, no cellular infrastructure, intermittent satellite access — while remaining fully compliant with NWCG PMS 515 standards and FAA regulatory requirements for BVLOS UAS operations."),
  spacer(80),
  infoBox("Key Performance Targets", [
    "  Prediction cycle time:       < 20 minutes end-to-end",
    "  Telemetry delivery rate:     > 95% (vs. 52% in PAMS TCL1 baseline)",
    "  TFR/OI latency:              < 30 seconds (vs. up to 12 minutes in baseline)",
    "  Ground crew alert latency:   < 60 seconds for safety-critical events",
    "  Drone utilization:           Dual-role (sensing + relay) per platform",
    "  Offline operational:         Full capability with zero internet dependency",
  ]),
  spacer(120),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 2: System Overview ───────────────────────────────────────────────
const systemOverview = [
  h1("2. System Overview"),
  hRule(),
  spacer(80),
  h2("2.1 Problem Statement"),
  para("Wildland fire aerial operations face three compounding challenges that no current system addresses holistically:"),
  numbered("Fire prediction models are data-starved. RAWS weather stations are spaced 30–50 km apart. Satellite perimeter imagery updates every 4 hours. Between updates, fire managers rely on stale data and expert judgment to position resources and predict fire behavior."),
  numbered("Drone operations are manually coordinated. The ATGS manages airspace from a manned aircraft using voice radio and visual observation. This approach cannot scale to support multiple simultaneous BVLOS drone operations, cannot function at night, and cannot accommodate the data volumes produced by modern sensor payloads."),
  numbered("Ground crews are informationally isolated. Firefighters on the fireline have no access to the digital common operating picture available to air operations. They receive information via radio relay chains that may be several hops deep, with no guarantee of timeliness."),
  spacer(80),
  h2("2.2 Solution Architecture"),
  para("IGNIS addresses all three problems with a closed-loop architecture where each component feeds the next:"),
  spacer(60),
  codeBlock([
    "┌─────────────────────────────────────────────────────────────────────┐",
    "│                     GROUND STATION (PAMS Case)                      │",
    "│                                                                     │",
    "│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   │",
    "│  │    ELMFIRE    │   │  GP / EnKF   │   │   IGNIS Orchestrator  │   │",
    "│  │   Ensemble   │◄──│  Assimilation│◄──│   (20-min cycle)     │   │",
    "│  └──────┬───────┘   └──────────────┘   └──────────┬───────────┘   │",
    "│         │ fire spread                              │ mission queue  │",
    "│  ┌──────▼───────────────────────────────────────  │  ───────────┐  │",
    "│  │           Information Field + Target Selector  │             │  │",
    "│  └──────────────────────────────────┬─────────────▼─────────────┘  │",
    "│                                     │ OI requests                   │",
    "│  ┌──────────────────────────────────▼─────────────────────────────┐ │",
    "│  │                  UTM / WFSS Layer                               │ │",
    "│  │  Conflict Detection | OI Lifecycle | Conformance | Auth        │ │",
    "│  └──────────────────────────────────┬─────────────────────────────┘ │",
    "└─────────────────────────────────────┼─────────────────────────────┘",
    "                                      │ cleared flight plans",
    "         ┌────────────────────────────▼──────────────────────────┐",
    "         │                   DRONE MESH NETWORK                   │",
    "         │  Type 1/2: High-altitude relay + strategic mapping     │",
    "         │  Type 3/4: Low-altitude sensing + ground crew comms   │",
    "         └────────┬────────────────────────────┬─────────────────┘",
    "                  │ observations                │ relay",
    "         ┌────────▼────────┐          ┌─────────▼───────────────┐",
    "         │  Back to IGNIS  │          │  GROUND CREW DEVICES    │",
    "         │  (assimilation) │          │  Fire perimeter + wind  │",
    "         └─────────────────┘          │  Escape routes + alerts │",
    "                                      └─────────────────────────┘",
  ]),
  spacer(120),
  h2("2.3 Operational Concept"),
  para("A single IGNIS deployment consists of a ground station (ruggedized mini-PC in a PAMS-style wheeled case), a drone fleet of mixed types, and handheld devices for ground crews. The system is fully self-contained — no internet connection is required for core operations. Optional cloud connections (HRRR weather, D-Wave QPU) enhance performance when available."),
  para("The system operates in continuous 20-minute cycles. Within each cycle, ELMFIRE runs an ensemble of N=50 fire spread simulations with perturbed inputs drawn from the Gaussian Process uncertainty model. The ensemble output is analyzed to identify which unobserved locations, if measured, would most reduce prediction uncertainty. Drones are tasked to those locations. When drones return observations, the GP and ensemble are updated, and the cycle repeats."),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 3: NWCG Compliance ───────────────────────────────────────────────
const nwcgCompliance = [
  h1("3. NWCG PMS 515 Compliance Framework"),
  hRule(),
  spacer(80),
  para("All drone operations within IGNIS are governed by NWCG Standards for Fire Unmanned Aircraft Systems Operations, PMS 515, in conjunction with FAA 14 CFR Part 107 and applicable DOI/USFS operational memoranda. Compliance is enforced programmatically — no flight is authorized without the full approval chain being satisfied digitally."),
  spacer(80),
  h2("3.1 UAS Fleet Typing"),
  para("IGNIS operates a mixed fleet classified per PMS 515 Table 1:"),
  spacer(60),
  twoColTable(
    ["Type", "Role in IGNIS", "Altitude Band", "Endurance", "Sensors"],
    [
      ["Type 1 (Fixed-Wing)", "Primary strategic relay + perimeter mapping", "3,500–8,000 ft AGL", "6–14 hrs", "EO/Mid-Wave IR, Mode C transponder"],
      ["Type 2 (Fixed-Wing)", "Secondary relay + tactical mapping", "3,500–6,000 ft AGL", "1–6 hrs", "EO/Long-Wave IR, Mode C transponder"],
      ["Type 3 (Rotorcraft)", "Targeted sensing per IGNIS queue", "≤ 2,000 ft AGL", "20–60 min", "Multispectral (FMC), anemometer, EO/IR"],
      ["Type 4 (Rotorcraft)", "Ground crew communications bridge", "≤ 1,200 ft AGL", "≤ 20 min", "900 MHz radio relay, EO video"],
    ],
    [2000, 2400, 2000, 1560, 1400]
  ),
  spacer(100),
  h2("3.2 Authorization Chain"),
  para("The following authorization sequence is enforced as a hard gate in the UTM layer. No Operational Intent (OI) may transition to Activated state without each step being digitally confirmed:"),
  numbered("IC or designee approval obtained and logged in the system."),
  numbered("Airspace authorization confirmed: FAA Part 107, SGI Waiver (BVLOS in TFR), DOI/FAA MOA (night or below 1,200 ft AGL), COA (EVLOS), or USFS/FAA MOA as applicable."),
  numbered("NOTAM filed with FAA. System generates NOTAM-compatible text automatically from TFR polygon and time window."),
  numbered("TFR deconfliction confirmed with dispatch or TFR-controlling authority."),
  numbered("Clearance obtained from ATGS, ASM, HLCO, or Lead Plane. One-tap digital approval via ground station UI replaces voice-only coordination."),
  numbered("OI submitted to WFSS and validated against active TFR volume and existing OIs. Strategic conflict detection run automatically."),
  numbered("OI transitions to Accepted. Drone authorized to launch."),
  spacer(80),
  h2("3.3 Call Sign Management"),
  para("IGNIS automatically assigns and tracks NWCG-standard call signs for all managed aircraft. Call signs follow the format: [Unmanned] [R/F][Type][Number]. Examples: Unmanned R31, Unmanned F12, Unmanned R42. The system broadcasts call signs on both assigned Victor (AM) and air-to-ground (FM) frequencies. For BVLOS operations where no human operator is monitoring audio, the system generates automated blind radio calls at configurable intervals."),
  spacer(80),
  h2("3.4 Separation and Deconfliction Requirements"),
  para("Per PMS 515, UAS must give way to all manned aircraft at all times. IGNIS enforces this through three layers:"),
  bullet("Altitude band enforcement: Type 3 drones cannot be authorized above 2,500 ft AGL regardless of IGNIS mission requests. Hard ceiling enforced in OI validation."),
  bullet("ADS-B proximity alerting: When an ADS-B target enters the TFR or approaches within 500 ft horizontal / 200 ft vertical of any active UAS altitude band, all drones in that band execute a pre-programmed hold maneuver and the ATGS is alerted."),
  bullet("Lost-link protocol: Every OI must specify a lost-link behavior before authorization is granted — loiter, return-to-LRZ, or controlled descent to a designated safe zone. This is pre-programmed into the flight controller before launch."),
  spacer(80),
  h2("3.5 Ground Crew Safety Requirements"),
  para("Per PMS 515 BVLOS guidelines, all ground resources must be briefed about UAS operations above them. IGNIS addresses this through:"),
  bullet("Ground crew devices display a persistent 'UAS Overhead' indicator showing drone positions within 500 ft horizontal of crew locations."),
  bullet("When any drone descends below 500 ft AGL within 300 m of a crew position, an audible and visual alert is issued on all crew devices."),
  bullet("Crew GPS positions are visible to the ATGS and all drone operators in the common operating picture, ensuring spatial awareness of human assets at all times."),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 4: IGNIS Core Engine ─────────────────────────────────────────────
const ignisEngine = [
  h1("4. IGNIS Core Prediction Engine"),
  hRule(),
  spacer(80),
  para("The prediction engine runs continuously on the ground station, completing a full cycle every 20 minutes. It consists of six tightly coupled components: Terrain Manager, Gaussian Process Prior, ELMFIRE Ensemble Engine, Information Field Computation, Target Selector, and Data Assimilation."),
  spacer(80),
  h2("4.1 Terrain Manager"),
  para("Static data loaded once at deployment from LANDFIRE via the landfire-python library. Provides elevation, slope, aspect, and Anderson 13 fuel models at 50m resolution for the incident domain. Fuel model parameters (load, SAV ratio, bed depth, moisture of extinction, heat content) are stored as published constants from Andrews 2018, RMRS-GTR-371. The terrain data is immutable after initialization — it does not change during a cycle."),
  spacer(60),
  codeBlock([
    "TerrainData:",
    "  elevation:   float32[rows, cols]   # meters MSL",
    "  slope:       float32[rows, cols]   # degrees",
    "  aspect:      float32[rows, cols]   # degrees from north",
    "  fuel_model:  int8[rows, cols]      # Anderson 13 IDs (1-13)",
    "  resolution:  50.0 m",
    "  origin:      (lat, lon)            # NW corner of domain",
  ]),
  spacer(80),
  h2("4.2 Gaussian Process Prior"),
  para("The GP maintains a spatially resolved estimate of fuel moisture content (FMC) and wind fields with calibrated uncertainty at every grid cell, conditioned on all available observations. Observations include RAWS station data (~50 km spacing), HRRR weather forecast (pulled once per cycle when connectivity is available, cached otherwise), and all previous drone measurements."),
  para("The kernel uses terrain-aware distance — two points on the same aspect and elevation band are more correlated than two points at equal Euclidean distance on opposite sides of a ridge. Correlation lengths are set to physically motivated defaults: approximately 1–2 km for FMC and 5 km for wind, fitted from RAWS data when sufficient observations are available."),
  para("The critical property exploited by the target selector is the closed-form conditional variance update: when a new observation is added at location x_new, the posterior variance at every other grid cell can be updated in a single vectorized NumPy operation with no matrix inversion. This makes the greedy selector computationally tractable even for large grids."),
  spacer(60),
  codeBlock([
    "GP Posterior Update (per new observation at x_new):",
    "",
    "  sigma2_updated(x) = sigma2(x) - k(x, x_new)^2 / (k(x_new, x_new) + sigma2_noise)",
    "",
    "  Cost: one vectorized operation over all D grid cells",
    "  No matrix inversion, no GP refitting",
    "  Called K times per cycle (once per drone placement)",
  ]),
  spacer(80),
  h2("4.3 ELMFIRE Ensemble Engine"),
  para("ELMFIRE (Eulerian Level-set Model of FIRE spread) replaces the custom Rothermel cellular automaton described in initial IGNIS design. ELMFIRE is a GPU-native, physics-based fire spread model developed at USFS, using the same Rothermel rate-of-spread physics but solving them as a level-set PDE rather than cellular automata. This eliminates grid-direction bias, improves fire front geometry accuracy, and provides better handling of backing fires."),
  para("ELMFIRE ensemble execution: N=50 members run with perturbed FMC and wind fields drawn from the GP posterior. Perturbations are spatially correlated — cells near RAWS stations (low GP variance) receive small perturbations while cells in data-sparse terrain (high GP variance) receive large perturbations. The correlation structure is generated via circulant embedding with FFT, cost O(D log D), avoiding the O(D^3) full covariance matrix."),
  spacer(60),
  twoColTable(
    ["Parameter", "Value", "Notes"],
    [
      ["Ensemble size (N)", "50 members", "Sufficient for stable variance estimates; increase to 100 for high-complexity terrain"],
      ["Domain resolution", "50 m", "Resampled from 30m LANDFIRE for computational tractability"],
      ["Forecast horizon", "60 minutes", "Covers 2–3 prediction cycles ahead"],
      ["GPU memory required", "~12 GB", "For N=50 on 200x200 domain; RTX 4090 (24 GB) provides headroom"],
      ["Single-member runtime", "30–60 sec", "GPU-accelerated ELMFIRE on RTX 4090"],
      ["Full ensemble (batched)", "< 5 minutes", "With sufficient GPU VRAM to batch members"],
    ],
    [2400, 2400, 4560]
  ),
  spacer(80),
  h2("4.4 Information Field Computation"),
  para("The information field w(x) quantifies, at every grid cell, the value of a drone measurement at that location. It combines three factors: GP variance (how uncertain is this location), sensitivity (does uncertainty here actually affect the predicted fire trajectory), and observability (can the drone sensor reliably measure this variable at this location)."),
  spacer(60),
  codeBlock([
    "Information Field Computation:",
    "",
    "Step 1 — Sensitivity (per variable v, per cell c):",
    "  S_v(c) = corr(arrival_times[:, c], perturbation_fields[:, c])",
    "  Computed via element-wise correlation across N ensemble members",
    "  Cost: one matrix operation, milliseconds total",
    "",
    "Step 2 — Observability (sensor accuracy by location):",
    "  D_fmc(x)  = 0.86 baseline, degraded near active fire by smoke proxy",
    "  D_wind(x) = 0.90 baseline, degraded by terrain complexity",
    "",
    "Step 3 — Information value (combined):",
    "  w(x) = GP_var_fmc(x) * |S_fmc(x)| * D_fmc(x)",
    "        + GP_var_wind(x) * |S_wind(x)| * D_wind(x)",
    "        + GP_var_winddir(x) * |S_winddir(x)| * D_wd(x)",
    "",
    "Step 4 — Overlays:",
    "  w(x) *= priority_weight(x)   # operator-defined priority regions",
    "  w(x)  = 0  if x in exclusion_zone",
  ]),
  spacer(80),
  h2("4.5 Target Selector"),
  para("Two selection algorithms run in parallel each cycle, with their outputs compared for quality on the same counterfactual evaluation framework:"),
  h3("4.5.1 Greedy Selector"),
  para("Iteratively selects the highest-value cell, then updates the GP variance to account for the information that observation would provide, naturally handling spatial redundancy through the GP kernel's correlation structure. Achieves a provable (1 - 1/e) ≈ 63% approximation ratio to the optimal solution under Gaussian assumptions (Krause et al., 2008). Runtime scales as O(K * D) where K is the number of drones and D is the grid size — milliseconds for typical domains."),
  h3("4.5.2 QUBO Selector"),
  para("Encodes the same information-gain-with-redundancy problem as a Quadratic Unconstrained Binary Optimization matrix. Linear terms encode individual location value (w_i). Quadratic terms encode spatial redundancy via ensemble covariance. Cardinality penalty enforces exactly K selections. Solved via fallback chain: D-Wave QPU (if satellite connectivity available) → simulated annealing (always available on ground station GPU) → greedy (always succeeds). Both selectors produce the same output format and are compared on equal footing each cycle."),
  spacer(80),
  h2("4.6 Data Assimilation"),
  para("Two parallel update mechanisms run after each drone observation batch:"),
  bullet("GP update: New observations are added to the conditioning set. Posterior variance drops near observed locations, reducing perturbation magnitude in those regions for the next ensemble run."),
  bullet("Ensemble Kalman Filter (EnKF): Adjusts each ensemble member's state to be consistent with drone observations. Gaspari-Cohn localization tapering limits spurious long-range correlations, preventing observations from incorrectly updating distant unobserved regions."),
  para("Replan triggers are computed after assimilation: if total posterior variance drops by more than 20%, the cycle is flagged as high-information. If observed wind deviates from the prior mean by more than 30 degrees at any location, an immediate partial re-solve is triggered without waiting for the full 20-minute cycle."),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 5: UTM / Airspace Management ────────────────────────────────────
const utmSection = [
  h1("5. UTM and Airspace Management Layer"),
  hRule(),
  spacer(80),
  para("The UTM layer is derived from NASA's FREDDIE (Federated Airspace Management Framework) and the PAMS/WFSS architecture developed under the ACERO project. It handles the full OI lifecycle, strategic conflict detection, conformance monitoring, and the interface between IGNIS mission requests and regulatory compliance."),
  spacer(80),
  h2("5.1 Wildland Fire Service Supplier (WFSS)"),
  para("Each ground station runs a WFSS instance that provides the following capabilities:"),
  bullet("Constraint Sharing: TFR volumes ingested and broadcast to all PAMS cases in the network. Periodic rebroadcast at 60-second intervals ensures eventual delivery despite intermittent connectivity."),
  bullet("Operational Intent (OI) Management: Full OI lifecycle per ASTM F3548-21, adapted for wildfire operations. See Section 5.2 for state diagram."),
  bullet("Strategic Conflict Detection: OIs compared against TFR volume and all other active OIs. Conflicts flagged with nature of overlap (spatial volume and time window). Users prompted to replan before activation."),
  bullet("Conformance Monitoring: Active drones tracked against their filed OI volumes. Alerts issued and broadcast to all WFSS instances when a drone exits its authorized volume."),
  bullet("Data Archiving: All AMF messages (TFR, OI, telemetry) logged with timestamps for post-incident analysis and regulatory compliance."),
  spacer(80),
  h2("5.2 Operational Intent State Machine"),
  para("The IGNIS OI lifecycle adapts the ASTM F3548-21 standard with two wildfire-specific modifications: (1) the Contingent state is replaced by a pre-declared contingency volume extension that activates automatically on nonconformance, and (2) OI approval is enforced digitally through the ATGS interface rather than voice radio."),
  spacer(60),
  codeBlock([
    "OI State Diagram:",
    "",
    "  [IGNIS generates mission] → DRAFT",
    "       │",
    "       ▼ (WFSS validates against TFR + existing OIs)",
    "    ACCEPTED",
    "       │",
    "       ▼ (ATGS one-tap digital approval)",
    "    ACTIVATED  ──────────────────────────────────────────┐",
    "       │                                                  │",
    "       ▼ (drone exits OI volume or time window)          │",
    "  NONCONFORMING  ─── (drone returns to volume) ──────────┘",
    "       │                                                  │",
    "       ▼ (timeout or operator action)                     │",
    "    CONTINGENT VOLUME ACTIVE  ──── (resolves) ───────────┘",
    "       │",
    "       ▼ (drone landed, telemetry stops)",
    "      ENDED",
    "",
    "  Key difference from UTM: Contingent state pre-declared as",
    "  volume expansion (+200m lateral, +500ft vertical) around",
    "  nominal OI. Activates automatically, no operator action needed.",
    "  Eliminates lost-link gap from original PAMS design.",
  ]),
  spacer(80),
  h2("5.3 IGNIS-to-WFSS Bridge"),
  para("This bridge is the critical integration point between the prediction engine and the airspace management layer. It converts IGNIS MissionRequest objects into WFSS-compliant OI volumes and manages the authorization workflow."),
  spacer(60),
  codeBlock([
    "MissionRequest (from IGNIS):           OI Volume (for WFSS):",
    "  target: (lat, lon)          →          polygon: 200m radius circle",
    "  information_value: float    →          (priority score for scheduling)",
    "  dominant_variable: str      →          (logged for post-analysis)",
    "  substitutes: [(lat,lon)]    →          (fallback OI volumes if conflict)",
    "  expiry_minutes: float       →          time_window: [now, now+expiry]",
    "  drone_type: UASType         →          altitude_range: per PMS 515 typing",
    "",
    "Authorization workflow (automated):",
    "  1. Validate OI against TFR volume",
    "  2. Run strategic conflict detection vs. all active OIs",
    "  3. If no conflicts → push to ATGS approval queue",
    "  4. ATGS approves via one-tap UI (replaces voice radio)",
    "  5. OI transitions to Accepted → drone assigned and briefed",
    "  6. On launch confirmation → OI transitions to Activated",
  ]),
  spacer(80),
  h2("5.4 Airspace Conflict Detection"),
  para("Conflict detection runs in four dimensions — spatial volume (x, y, z) and time — and at three levels of severity:"),
  spacer(60),
  twoColTable(
    ["Conflict Type", "Detection Method", "Response"],
    [
      ["TFR boundary violation", "OI volume intersects TFR exclusion zone", "OI rejected; IGNIS generates substitute target"],
      ["OI-OI spatial conflict", "4D volume overlap between two active OIs", "Warning issued; users prompted to replan"],
      ["Altitude band violation", "OI altitude exceeds PMS 515 ceiling for UAS type", "Hard block; OI cannot be activated"],
      ["ADS-B proximity alert", "ADS-B target within 500 ft horizontal / 200 ft vertical of active UAS", "Immediate hold issued to all drones in band; ATGS alerted"],
      ["Lost-link / conformance breach", "Telemetry stops or drone exits OI volume", "Contingency volume activates; alert broadcast to all WFSS instances"],
    ],
    [2400, 3360, 3600]
  ),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 6: Drone Fleet Management ───────────────────────────────────────
const droneSection = [
  h1("6. Drone Fleet Management"),
  hRule(),
  spacer(80),
  para("The fleet management layer bridges the UTM authorization system and physical drone operations. It handles role allocation, coverage optimization, path planning, and real-time reallocation in response to IGNIS replan triggers."),
  spacer(80),
  h2("6.1 Dual-Role Architecture"),
  para("Each drone in the IGNIS fleet serves two simultaneous roles: a primary mission role (sensing or relay) and a secondary mesh networking role. This is the key architectural departure from PAMS, where a dedicated relay drone was required as a separate asset. In IGNIS, every drone is a mesh node, so adding drones for improved fire coverage automatically improves network redundancy."),
  spacer(60),
  infoBox("Why This Fixes the PAMS Reliability Problem", [
    "  PAMS TCL1 result:  52% telemetry success rate with 1 relay drone + 3 ground nodes",
    "  Root cause:         Single relay node = single point of failure for entire mesh",
    "  IGNIS approach:    Every drone is a relay node; N drones = N-1 relay redundancy",
    "  Expected result:   Network failure requires ALL high-altitude drones to fail simultaneously",
    "                     Scales naturally: more drones = better coverage = better comms",
  ], "D5F0D5", "375623"),
  spacer(80),
  h2("6.2 Fleet Role Allocation"),
  para("Given a fleet of N drones, the allocation algorithm balances relay topology coverage against IGNIS sensing requirements. The relay fraction is a function of terrain complexity and the number of ground nodes that need connectivity:"),
  spacer(60),
  codeBlock([
    "Fleet Allocation Algorithm:",
    "",
    "  relay_fraction = f(terrain_complexity, ground_node_count, K_sensing)",
    "",
    "  Defaults (adjustable by ATGS):",
    "    N=3:  1 relay (Type 1/2) + 2 sensing (Type 3)",
    "    N=5:  2 relay (Type 1/2) + 3 sensing (Type 3)",
    "    N=8:  2 relay (Type 1/2) + 4 sensing (Type 3) + 2 ground-crew comms (Type 4)",
    "    N=10: 3 relay + 5 sensing + 2 ground-crew comms",
    "",
    "  Relay drones: Fixed waypoints optimized for LOS to all ground nodes",
    "  Sensing drones: Dynamic waypoints from IGNIS mission queue",
    "  Ground-crew comms drones (Type 4): Orbit above crew positions at 800-1200 ft AGL",
  ]),
  spacer(80),
  h2("6.3 Coverage Optimization"),
  para("Relay drone positions are computed by solving a facility location problem over the terrain: find the set of R airborne positions that maximizes line-of-sight connectivity to all ground nodes while maintaining mutual LOS between relay drones. The terrain digital elevation model from LANDFIRE is used to compute LOS profiles."),
  spacer(60),
  codeBlock([
    "Relay Position Optimization:",
    "",
    "  Inputs:",
    "    - Ground node positions (ground station + ground crew devices)",
    "    - Terrain DEM at 50m resolution",
    "    - R = number of relay drones available",
    "    - Altitude constraint: relay drones operate at 3,500-8,000 ft AGL",
    "",
    "  Objective:",
    "    Minimize max_hop_count(any_node, ground_station)",
    "    Subject to: LOS(relay_i, relay_j) for adjacent relays",
    "                LOS(relay_i, ground_node_j) for assigned nodes",
    "                altitude constraints per PMS 515",
    "",
    "  Method: Greedy facility location (same submodularity argument as IGNIS selector)",
    "  Runtime: < 1 second for R <= 4, N_nodes <= 20",
  ]),
  spacer(80),
  h2("6.4 Dynamic Reallocation"),
  para("When IGNIS identifies a high-priority replan trigger (wind shift > 30 degrees or new high-uncertainty region outside current drone coverage), the fleet manager can interrupt a low-priority sensing mission and redirect a drone within a single 20-minute cycle. The reallocation sequence is:"),
  numbered("IGNIS flags replan trigger with new target set."),
  numbered("Fleet manager identifies lowest-priority active sensing mission."),
  numbered("New OI submitted for redirected drone, validated by WFSS."),
  numbered("ATGS one-tap approval of new OI."),
  numbered("Existing OI transitioned to Ended (drone rerouted mid-flight if needed)."),
  numbered("New OI activated, drone proceeds to new waypoints."),
  para("Total reallocation latency target: under 3 minutes from trigger to new OI activation."),
  spacer(80),
  h2("6.5 Path Planning"),
  para("Path planning converts IGNIS-selected target locations into feasible drone flight plans that respect OI volume constraints, altitude band limits, and PMS 515 separation requirements. For the initial deployment, nearest-neighbor routing from a staged launch and recovery zone (LRZ) is used. Future versions will incorporate minimum-time routing with obstacle avoidance for complex terrain."),
  para("Path-integrated observations: drones do not only measure at waypoints — they observe every grid cell they fly over. The path planner computes all cells within the sensor footprint along each flight leg using Bresenham's line algorithm with a 3-cell-wide camera footprint at nominal flight altitude. These additional observations are included in the assimilation step, making targeted flights more efficient than the path alone would suggest."),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 7: Ground Crew Communications ────────────────────────────────────
const groundComms = [
  h1("7. Ground Crew Communications System"),
  hRule(),
  spacer(80),
  para("The ground crew communications subsystem extends the IGNIS common operating picture to firefighters on the fireline — the user population most at risk and least served by existing digital situational awareness tools. It is designed for extreme simplicity of use: no training required beyond a 5-minute briefing, single-button status reporting, and battery life exceeding a full operational period (10+ hours)."),
  spacer(80),
  h2("7.1 Device Architecture"),
  para("Each ground crew supervisor carries a ruggedized Android tablet or smartphone with the IGNIS ground crew application. The device communicates with the nearest Type 4 drone overhead via 900 MHz license-free radio link (900 MHz chosen for superior range and penetration through smoke relative to 2.4/5.8 GHz). The Type 4 drone relays traffic to the WFSS ground station via the mesh network."),
  spacer(60),
  codeBlock([
    "Ground Crew Communication Path:",
    "",
    "  Ground crew device",
    "    └── 900 MHz radio link (range: 3-5 km line-of-sight)",
    "          └── Type 4 drone (orbiting at 800-1,200 ft AGL)",
    "                └── Silvus/DoodleLabs mesh (S-band)",
    "                      └── Type 1/2 relay drone (3,500-8,000 ft AGL)",
    "                            └── Silvus/DoodleLabs mesh",
    "                                  └── WFSS ground station",
    "                                        └── IGNIS + common operating picture",
    "",
    "  Latency budget: < 2 seconds end-to-end for non-safety messages",
    "  Safety alerts:  Priority interrupt, < 500 ms, retransmitted every 5 sec",
    "                  until acknowledged",
  ]),
  spacer(80),
  h2("7.2 Information Downlink to Ground Crews"),
  para("The following data is pushed to ground crew devices on each IGNIS cycle completion (approximately every 20 minutes) and on any safety-critical event trigger:"),
  spacer(60),
  twoColTable(
    ["Data Element", "Source", "Update Frequency"],
    [
      ["Current fire perimeter (GeoJSON)", "ELMFIRE ensemble mean", "Every 20-min cycle"],
      ["20-min predicted perimeter + uncertainty band", "ELMFIRE ensemble spread", "Every 20-min cycle"],
      ["Wind speed and direction at crew position", "GP posterior at crew GPS", "Every 20-min cycle"],
      ["All crew GPS positions", "Uplink from all devices", "Continuous (30-sec poll)"],
      ["Active aircraft overhead", "WFSS ADS-B + OI registry", "Continuous"],
      ["Escape routes and safety zones", "Pre-designated + IGNIS updated", "On change"],
      ["Hazard alerts (wind shift, blowup)", "IGNIS replan trigger", "Immediate, priority interrupt"],
      ["UAS overhead indicator", "WFSS conformance monitor", "Continuous"],
    ],
    [2880, 2880, 3600]
  ),
  spacer(80),
  h2("7.3 Information Uplink from Ground Crews"),
  para("Ground crew observations feed back into IGNIS as soft data points. The ground crew app provides three reporting mechanisms, designed for use with gloves and under stress:"),
  bullet("One-tap status: OK / Needs Support / Emergency. Status visible to IC and ATGS immediately."),
  bullet("Fire observation: Pre-set options for spotting distance, flame length estimate, rate-of-spread qualitative (slow / moderate / running). Translated to IGNIS soft constraints — e.g., 'running uphill NE' updates the wind direction prior in that sector."),
  bullet("Free text (optional): For unusual observations. Logged but not automatically assimilated."),
  spacer(80),
  h2("7.4 Safety Alert Protocol"),
  para("Safety alerts bypass normal message scheduling and are transmitted as priority interrupts through every available path simultaneously (mesh network, direct 900 MHz, and satellite fallback if available). Alert conditions and their triggers:"),
  spacer(60),
  twoColTable(
    ["Alert Type", "Trigger Condition", "Response Required"],
    [
      ["Wind shift warning", "IGNIS detects > 30-degree wind direction change at any observed location", "Acknowledge within 60 sec; auto-escalate to ATGS if not acknowledged"],
      ["Blowup potential", "ELMFIRE ensemble shows > 30% probability of area ignition in next 20 min", "Immediate acknowledgment; evacuation route highlighted"],
      ["UAS approach", "Any drone within 500 ft horizontal and 500 ft AGL of crew position", "Advisory only; no action required"],
      ["Communication degraded", "No uplink from crew device for > 5 minutes", "ATGS alerted; last known position displayed on COP"],
      ["Crew emergency", "Emergency button pressed on crew device", "Immediate broadcast to all devices; ATGS and IC alerted; GPS position pinned"],
    ],
    [2200, 3560, 3600]
  ),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 8: Network Architecture ─────────────────────────────────────────
const networkSection = [
  h1("8. Network Architecture"),
  hRule(),
  spacer(80),
  para("The IGNIS network is designed for resilience-first operation in environments with no cellular or internet infrastructure. It uses a multi-layer mesh architecture where every airborne platform is a network node, and no single failure can partition the network."),
  spacer(80),
  h2("8.1 Network Layers"),
  spacer(60),
  twoColTable(
    ["Layer", "Technology", "Role", "Fallback"],
    [
      ["Primary airborne mesh", "Silvus Streamcaster 4200 E+ (S-band)", "High-bandwidth data between drones and ground station", "DoodleLabs mesh"],
      ["Secondary airborne mesh", "DoodleLabs (2.4/5.8 GHz)", "Backup inter-drone and drone-to-ground link", "Store-and-forward DTN"],
      ["Ground crew link", "900 MHz license-free radio", "Device-to-Type-4-drone last-mile", "Direct SMS-style text if mesh down"],
      ["Satellite backhaul", "Starlink / Iridium (optional)", "HRRR weather pull, D-Wave QPU, remote COP access", "None (graceful degradation)"],
      ["Local ground mesh", "Ethernet / WiFi", "PAMS case to radio node connection", "USB tether"],
    ],
    [2000, 2400, 2960, 2000]
  ),
  spacer(80),
  h2("8.2 Message Priority and Store-and-Forward"),
  para("The PAMS TCL1 evaluation showed 52% telemetry delivery due to no retransmit logic for telemetry packets. IGNIS implements a four-tier priority queue with store-and-forward for all message types:"),
  spacer(60),
  twoColTable(
    ["Priority", "Message Type", "Delivery Guarantee", "Max Latency"],
    [
      ["P0 — Emergency", "Safety alerts, crew emergency, lost-link", "Retransmit every 5 sec until ACK; broadcast all paths", "< 500 ms"],
      ["P1 — Safety", "Wind shift alerts, blowup potential, ADS-B proximity", "Retransmit every 15 sec until ACK", "< 5 sec"],
      ["P2 — Operational", "OI state transitions, TFR updates, conformance alerts", "Periodic rebroadcast at 60-sec intervals", "< 60 sec"],
      ["P3 — Telemetry", "Drone position, velocity, sensor readings", "Delta-compressed, adaptive rate; store-and-forward buffer", "< 5 min acceptable"],
      ["P4 — Background", "Fire perimeter updates, map tiles, IGNIS cycle reports", "Best-effort, dropped if congested", "As available"],
    ],
    [1400, 2400, 2760, 2800]
  ),
  spacer(80),
  h2("8.3 Telemetry Compression"),
  para("Raw telemetry at full rate was the primary cause of the 52% delivery failure in PAMS. IGNIS uses three compression strategies applied in combination:"),
  bullet("Trajectory state compression: transmit position + velocity vector + timestamp. Receivers dead-reckon position between updates. Only deviations from dead-reckoned position trigger a correction packet."),
  bullet("Delta encoding against OI: when a drone is conforming (flying within its filed OI volume), only transmit deviation from the filed trajectory. Conforming flight requires minimal bandwidth."),
  bullet("Adaptive rate control: telemetry rate is a function of link quality (RSSI/SNR logged per radio pair). Full rate at strong signal, reduced rate as link degrades, minimum heartbeat at poor link. Rate restored immediately when link improves."),
  spacer(80),
  h2("8.4 Delay-Tolerant Networking"),
  para("For scenarios where connectivity is intermittent rather than degraded, IGNIS implements Bundle Protocol (RFC 9171) for store-and-forward operation. OI state transitions and safety alerts are bundled and stored locally if the destination is unreachable, then delivered when connectivity resumes. This ensures that even in the worst-case connectivity scenario — a drone flying behind a ridge for 10 minutes — all state transitions are eventually delivered and the common operating picture converges."),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 9: Hardware ──────────────────────────────────────────────────────
const hardwareSection = [
  h1("9. Hardware and Deployment"),
  hRule(),
  spacer(80),
  h2("9.1 Ground Station"),
  para("The ground station runs all software components: IGNIS (ELMFIRE ensemble, GP, information field, target selection, assimilation), WFSS (UTM/airspace management), fleet management, and the common operating picture display. It is packaged in a PAMS-style ruggedized wheeled case for field deployment."),
  spacer(60),
  twoColTable(
    ["Component", "Specification", "Purpose"],
    [
      ["Compute", "Intel Core i9 / AMD Ryzen 9, 32 GB RAM", "IGNIS orchestrator, GP, EnKF, fleet management"],
      ["GPU", "NVIDIA RTX 4090 (24 GB VRAM)", "ELMFIRE ensemble (N=50 batched), QUBO simulated annealing"],
      ["Storage", "2 TB NVMe SSD", "LANDFIRE terrain cache, mission data archive, telemetry log"],
      ["Radio interface", "Silvus SC4200E+ (primary), DoodleLabs (backup)", "Mesh network uplink"],
      ["ADS-B receiver", "uAvionix pingStation or equivalent", "Manned aircraft situational awareness"],
      ["Power", "AC mains + 200 Wh LiFePO4 battery", "2-4 hrs autonomous operation; vehicle 12V charging"],
      ["Display", "15\" ruggedized touchscreen", "ATGS common operating picture interface"],
      ["Case", "Pelican 1650 or equivalent", "Field portability; IP67 dust/water resistance"],
    ],
    [2000, 3400, 3960]
  ),
  spacer(80),
  h2("9.2 Drone Platform Requirements"),
  para("IGNIS is platform-agnostic at the airframe level. The following sensor and communication requirements must be met for each drone type:"),
  spacer(60),
  twoColTable(
    ["Requirement", "Type 1/2 (Relay)", "Type 3 (Sensing)", "Type 4 (Crew Comms)"],
    [
      ["Mode C transponder", "Required (PMS 515)", "Not required", "Not required"],
      ["ADS-B out", "Required (Type 1/2)", "Not required", "Not required"],
      ["Silvus/DoodleLabs radio", "Required", "Required", "Optional"],
      ["900 MHz radio relay", "Not required", "Not required", "Required"],
      ["Multispectral camera", "Not required", "Required (FMC measurement)", "Not required"],
      ["Anemometer", "Not required", "Recommended", "Not required"],
      ["Thermal/IR camera", "Optional", "Recommended", "Not required"],
      ["GPS accuracy", "< 3 m CEP", "< 3 m CEP", "< 10 m CEP"],
      ["Telemetry downlink", "MAVLink or equivalent", "MAVLink or equivalent", "MAVLink or equivalent"],
    ],
    [3000, 2120, 2120, 2120]
  ),
  spacer(80),
  h2("9.3 Ground Crew Devices"),
  para("Ground crew devices must be ruggedized, simple, and battery-capable of a full operational period. Minimum requirements: Android 10 or later, IP67 dust/water resistance, 10+ hour battery life, built-in 900 MHz radio capability (or external dongle), screen readable in direct sunlight (> 600 nit brightness). Recommended devices include Getac ZX10, Samsung Galaxy XCover Pro, or Kyocera DuraForce Ultra 5G."),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 10: Software Architecture ───────────────────────────────────────
const softwareSection = [
  h1("10. Software Architecture"),
  hRule(),
  spacer(80),
  h2("10.1 Repository Structure"),
  spacer(60),
  codeBlock([
    "ignis/",
    "├── core/",
    "│   ├── types.py              # Shared dataclasses (TerrainData, GPPrior, etc.)",
    "│   ├── config.py             # Constants, fuel params, PMS 515 altitude limits",
    "│   └── utils.py              # UTM projection, distances, geometry",
    "├── terrain/",
    "│   └── terrain.py            # LANDFIRE loader, DEM processing",
    "├── prediction/",
    "│   ├── gp.py                 # GP prior, conditional variance update",
    "│   ├── elmfire_engine.py     # ELMFIRE ensemble wrapper",
    "│   ├── information.py        # Sensitivity + information field",
    "│   └── assimilation.py       # EnKF + GP observation update",
    "├── selectors/",
    "│   ├── greedy.py             # Greedy selector with GP variance update",
    "│   ├── qubo.py               # QUBO construction + solver fallback chain",
    "│   └── baselines.py          # Uniform grid, fire-front following",
    "├── utm/",
    "│   ├── wfss.py               # WFSS OI lifecycle, conflict detection",
    "│   ├── bridge.py             # IGNIS MissionRequest → WFSS OI conversion",
    "│   ├── airspace.py           # ADS-B integration, altitude enforcement",
    "│   └── auth_chain.py         # PMS 515 authorization gate",
    "├── fleet/",
    "│   ├── allocator.py          # Role allocation, relay position optimization",
    "│   ├── path_planner.py       # Waypoint generation, path-integrated obs",
    "│   └── reallocator.py        # Dynamic reallocation on replan triggers",
    "├── network/",
    "│   ├── mesh.py               # Silvus/DoodleLabs radio interface",
    "│   ├── priority_queue.py     # P0-P4 message priority + store-and-forward",
    "│   ├── telemetry.py          # Delta compression, adaptive rate control",
    "│   └── dtn.py                # Bundle Protocol RFC 9171 implementation",
    "├── ground_comms/",
    "│   ├── crew_feed.py          # Downlink data package assembly",
    "│   ├── crew_uplink.py        # Observation ingestion + IGNIS soft constraint",
    "│   └── alert_manager.py      # Safety alert priority interrupt",
    "├── orchestrator.py           # 20-minute cycle coordinator",
    "├── evaluation.py             # Counterfactual comparison framework",
    "└── visualization.py          # Common operating picture display",
    "",
    "apps/",
    "├── ground_station/           # ATGS desktop interface (Python/Qt or Electron)",
    "└── crew_app/                 # Ground crew Android application",
    "",
    "scripts/",
    "├── run_cycle.py              # Single cycle execution",
    "├── run_comparison.py         # Multi-strategy comparison",
    "└── sim_scenario.py           # Simulation-only mode for testing",
  ]),
  spacer(80),
  h2("10.2 Key Interfaces"),
  spacer(60),
  codeBlock([
    "# IGNIS → UTM Bridge",
    "class MissionRequest:",
    "    target: tuple[float, float]        # (lat, lon)",
    "    information_value: float           # w_i from information field",
    "    dominant_variable: str             # 'fmc' | 'wind_speed' | 'wind_dir'",
    "    substitutes: list[tuple]           # fallback locations if OI conflicts",
    "    expiry_minutes: float              # OI time window duration",
    "    drone_type: UASType                # determines altitude band",
    "    priority: int                      # 0=emergency replan, 1=normal, 2=low",
    "",
    "# UTM → IGNIS Feedback",
    "def ingest_observation(obs: DroneObservation) -> Optional[MissionQueue]: ...",
    "def add_exclusion_zone(polygon, reason) -> None: ...",
    "def add_priority_region(polygon, weight) -> None: ...",
    "",
    "# Ground Crew → IGNIS",
    "def ingest_crew_observation(obs: CrewObservation) -> None:",
    "    # Translates qualitative fire observations to GP soft constraints",
    "    # 'running uphill NE' → wind_direction_prior update in NE sector",
    "    # 'spotting 300m SE' → effective spotting distance observation",
  ]),
  spacer(80),
  h2("10.3 Degradation Contracts"),
  para("Every component has a defined failure mode that allows the system to continue operating in a degraded but safe state:"),
  spacer(60),
  twoColTable(
    ["Component", "Failure", "Degraded Behavior"],
    [
      ["LANDFIRE API", "Unreachable at deployment", "Use synthetic terrain (fractal DEM + default fuel model 2)"],
      ["ELMFIRE", "Timeout or crash", "Use last valid ensemble; flag predictions as stale after 40 min"],
      ["GP fitting", "Insufficient RAWS data (< 2 stations)", "Constant prior variance everywhere; note in COP"],
      ["QUBO / D-Wave", "Unreachable or timeout", "Automatic fallback to simulated annealing, then greedy"],
      ["EnKF", "No observations in last cycle", "Pass prior through unchanged; GP variance increases"],
      ["Mesh network", "Primary (Silvus) failure", "Automatic failover to DoodleLabs backup"],
      ["Satellite backhaul", "Unavailable (normal case)", "No HRRR update; cached forecast used; D-Wave unavailable"],
      ["Ground crew device", "No uplink for > 5 min", "Last known position displayed; ATGS alerted"],
      ["ADS-B receiver", "Failure", "Voice radio monitoring required; alert operator; no automated proximity alerts"],
    ],
    [2200, 2760, 4400]
  ),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 11: Operational Deployment ───────────────────────────────────────
const deploySection = [
  h1("11. Operational Deployment and Verification"),
  hRule(),
  spacer(80),
  h2("11.1 Deployment Sequence"),
  para("IGNIS is designed to be operational within 30 minutes of arriving at an incident:"),
  numbered("Transport: Ground station in wheeled PAMS case. Drone fleet in vehicle transport cases. Ground crew devices pre-charged and loaded with incident GIS data."),
  numbered("Site survey: Identify LRZ (flat, clear of obstacles, away from manned aircraft landing zones). Establish ground station location with clear sky view for satellite and ADS-B."),
  numbered("Network initialization: Power on ground station. Connect Silvus radio via ethernet. Verify mesh connectivity between ground station radio node and first relay drone on the ground."),
  numbered("Terrain and data load: IGNIS auto-loads LANDFIRE data for incident bounding box (pulled from cache if pre-loaded, or downloaded via satellite if available). Load incident perimeter from current situation report."),
  numbered("Authorization chain: Confirm IC approval. Verify airspace authorization type. File NOTAM (auto-generated by IGNIS from TFR polygon). Coordinate with ATGS for clearance."),
  numbered("First drone launch: Type 1/2 relay drone launched first, climbs to altitude, establishes mesh relay. System verifies >90% telemetry delivery before launching sensing drones."),
  numbered("IGNIS first cycle: Run initial ensemble. Generate first mission queue. ATGS reviews and approves sensing drone OIs. Sensing drones launch."),
  numbered("Ground crew brief: Distribute crew devices. 5-minute app briefing. Verify two-way communication with ground station."),
  spacer(80),
  h2("11.2 Verification and Validation"),
  para("The following tests must pass before IGNIS is cleared for operational deployment at a wildland fire incident:"),
  spacer(60),
  twoColTable(
    ["Test", "Pass Criterion", "NWCG Reference"],
    [
      ["Authorization chain enforcement", "No OI activates without complete digital authorization chain", "PMS 515 §3"],
      ["Altitude band enforcement", "Type 3 OI rejected if altitude exceeds 2,500 ft AGL", "PMS 515 Table 1"],
      ["ADS-B proximity alert", "Alert issued within 5 sec of simulated ADS-B target entering proximity zone", "PMS 515 §7"],
      ["Lost-link response", "Drone executes pre-programmed contingency within 30 sec of simulated link loss", "PMS 515 §8"],
      ["Telemetry delivery rate", "> 95% of telemetry packets delivered within 5-minute window", "Exceeds PAMS TCL1 baseline"],
      ["Safety alert latency", "P0 alert delivered to all crew devices within 500 ms in benign conditions", "BVLOS safety requirement"],
      ["Call sign broadcast", "Blind AM/FM calls generated correctly for BVLOS operations", "PMS 515 §6"],
      ["Ground crew UAS indicator", "UAS overhead indicator updates within 5 sec of drone entering 500 ft proximity", "PMS 515 BVLOS §5"],
      ["Full cycle time", "Complete IGNIS cycle (ensemble + targeting + OI generation) < 20 minutes", "System performance target"],
      ["Offline operation", "All core functions operational with zero internet connectivity for 4+ hours", "Operational requirement"],
    ],
    [2880, 3480, 3000]
  ),
  spacer(80),
  h2("11.3 NASA SBIR Phase I / Phase II Milestones"),
  spacer(60),
  twoColTable(
    ["Milestone", "Deliverable", "Phase"],
    [
      ["M1: Architecture validation", "System design document (this document); simulation environment operational", "Phase I"],
      ["M2: ELMFIRE integration", "ELMFIRE ensemble running on ground station GPU; GP prior validated against RAWS data", "Phase I"],
      ["M3: IGNIS cycle demonstration", "Full 20-minute cycle in simulation; greedy vs. QUBO comparison results", "Phase I"],
      ["M4: UTM layer integration", "WFSS OI lifecycle; IGNIS-WFSS bridge; authorization chain enforced", "Phase I"],
      ["M5: Network prototype", "Silvus mesh + DoodleLabs backup; priority queue; telemetry compression", "Phase II"],
      ["M6: Ground crew app", "Android app; 900 MHz link; safety alert protocol validated", "Phase II"],
      ["M7: TCL field evaluation", "Operationally relevant environment; comparison against PAMS baseline metrics", "Phase II"],
      ["M8: Multi-cycle assimilation", "EnKF + GP update over 5+ cycles; entropy reduction demonstrated", "Phase II"],
      ["M9: Phase III transition", "Partnership with CAL FIRE / USFS / commercial UAS operator for operational trial", "Phase II exit"],
    ],
    [2400, 4560, 2400]
  ),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 12: Risk Register ────────────────────────────────────────────────
const riskSection = [
  h1("12. Risk Register"),
  hRule(),
  spacer(80),
  twoColTable(
    ["Risk", "Likelihood", "Impact", "Mitigation"],
    [
      ["ELMFIRE ensemble does not complete within 20-min cycle on available GPU hardware", "Medium", "High", "Reduce ensemble size to N=25 as fallback; extend cycle to 30 min; upgrade to dual-GPU if needed"],
      ["D-Wave QPU unavailable (no satellite connectivity)", "High (expected)", "Low", "Simulated annealing on GPU is primary solver; D-Wave is enhancement only"],
      ["FMC sensor accuracy degrades near active fire due to smoke", "High", "Medium", "Smoke optical depth proxy degrades D_fmc observability; IGNIS redirects drones to non-smoke-affected sectors"],
      ["GPS accuracy degrades in mountainous canyons", "Medium", "Medium", "Terrain-aided navigation; relative positioning via mesh TDOA; note in proposal as future work"],
      ["Ground crew device battery fails mid-shift", "Medium", "Medium", "Vehicle charging in LRZO; spare devices; last known position retained in COP for 2 hours"],
      ["ATGS unfamiliar with digital approval workflow", "High (initial)", "Medium", "One-tap approval requires < 3 seconds; falls back to voice radio if tablet unavailable; training materials"],
      ["Single relay drone failure partitions mesh network", "Low", "High", "Multi-relay topology; automatic rerouting; DTN store-and-forward bridges partitions"],
      ["Regulatory changes to BVLOS authorization during project", "Low", "High", "Monitor FAA Reauthorization Act Section 910; architecture is authorization-type-agnostic"],
    ],
    [2400, 960, 960, 4680]
  ),
  spacer(80),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Section 13: Glossary ─────────────────────────────────────────────────────
const glossary = [
  h1("13. Glossary"),
  hRule(),
  spacer(80),
  twoColTable(
    ["Term", "Definition"],
    [
      ["ADS-B", "Automatic Dependent Surveillance-Broadcast. Aircraft position broadcast system."],
      ["ATGS", "Air Tactical Group Supervisor. Manages airspace over an incident."],
      ["BVLOS", "Beyond Visual Line of Sight. UAS operations where pilot cannot see the aircraft."],
      ["COA", "Certificate of Authorization. FAA authorization for UAS operations."],
      ["DTN", "Delay-Tolerant Networking. Store-and-forward protocol for intermittent connectivity."],
      ["ELMFIRE", "Eulerian Level-set Model of FIRE spread. GPU-native wildfire spread model (USFS)."],
      ["EnKF", "Ensemble Kalman Filter. Data assimilation method for updating model state."],
      ["FMC", "Fuel Moisture Content. Key driver of fire spread rate; primary IGNIS sensing target."],
      ["FTA", "Fire Traffic Area. 5 nm radius airspace established around a wildland fire."],
      ["GP", "Gaussian Process. Probabilistic model providing spatially continuous uncertainty estimates."],
      ["HRRR", "High-Resolution Rapid Refresh. NOAA hourly weather forecast model."],
      ["IC", "Incident Commander. Highest authority at an incident."],
      ["IGNIS", "Integrated Ground-Networked Intelligent UAS System (this system)."],
      ["LRZ", "Launch and Recovery Zone. Designated UAS takeoff and landing area."],
      ["NWCG", "National Wildfire Coordinating Group. Sets standards for wildland fire operations."],
      ["OI", "Operational Intent. Declared airspace volume + time window for a drone operation."],
      ["PAMS", "Portable Airspace Management System. NASA ACERO prototype airspace management system."],
      ["PMS 515", "NWCG Standards for Fire Unmanned Aircraft Systems Operations."],
      ["QUBO", "Quadratic Unconstrained Binary Optimization. Problem formulation for combinatorial optimization."],
      ["RAWS", "Remote Automated Weather Station. Sparse ground weather network."],
      ["SGI", "Special Government Interest waiver. FAA authorization for BVLOS in a TFR."],
      ["TFR", "Temporary Flight Restriction. FAA-established restricted airspace around an incident."],
      ["UTM", "UAS Traffic Management. NASA/FAA framework for low-altitude drone operations."],
      ["WFSS", "Wildland Fire Service Supplier. PAMS adaptation of the UTM USS concept."],
    ],
    [2400, 6960]
  ),
  spacer(80),
];

// ─── Assemble document ────────────────────────────────────────────────────────
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: C.navy },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: C.blue },
        paragraph: { spacing: { before: 280, after: 100 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: C.navy },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } }, run: { font: "Arial" } },
        }],
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } }, run: { font: "Arial" } },
        }],
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1260, bottom: 1440, left: 1260 },
      },
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            spacing: { before: 0, after: 80 },
            children: [
              new TextRun({ text: "IGNIS — Integrated Ground-Networked Intelligent UAS System", font: "Arial", size: 18, color: C.darkGray }),
              new TextRun({ text: "     |     Architecture Documentation v1.0", font: "Arial", size: 18, color: C.darkGray }),
            ],
          }),
          hRule(C.blue, 4),
        ],
      }),
    },
    footers: {
      default: new Footer({
        children: [
          hRule(C.midGray, 2),
          new Paragraph({
            spacing: { before: 80, after: 0 },
            children: [
              new TextRun({ text: "NASA SBIR Phase I  |  Nontraditional Aviation Operations for Wildfire Response  |  Page ", font: "Arial", size: 18, color: C.darkGray }),
              new PageNumber(),
            ],
          }),
        ],
      }),
    },
    children: [
      ...coverPage(),
      ...tocSection,
      ...execSummary,
      ...systemOverview,
      ...nwcgCompliance,
      ...ignisEngine,
      ...utmSection,
      ...droneSection,
      ...groundComms,
      ...networkSection,
      ...hardwareSection,
      ...softwareSection,
      ...deploySection,
      ...riskSection,
      ...glossary,
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/mnt/user-data/outputs/IGNIS_Architecture_Documentation.docx", buffer);
  console.log("Done.");
});