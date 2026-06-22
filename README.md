# integrAted dAta-driven Agent-based siMulation (AAAM)

> An agent-based simulation framework for inferring dynamic passenger crowding and operational characteristics in urban rail transit networks, combining smartcard data with GTFS supply inputs.

[![Python 3.7+](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/)
[![DOI](https://img.shields.io/badge/DOI-10.1016%2Fj.jrtpm.2026.100586-orange)](https://doi.org/10.1016/j.jrtpm.2026.100586)
[![Journal](https://img.shields.io/badge/Journal-JRTPM%202026-green)](https://doi.org/10.1016/j.jrtpm.2026.100586)


---

**References**

*Primary reference — framework and methodology*

Zhao, B., Tang, Y., Soga, K., Zhou, X., & Yang, H. (2026). Dynamic passenger crowding and operations in rail transit systems: a validated framework of integrated data-driven agent-based simulation (AAAM). *Journal of Rail Transport Planning & Management*, *38*, 100586. https://doi.org/10.1016/j.jrtpm.2026.100586

*Application*

Zhao, B., Tang, Y., Wang, C., Zhang, S., & Soga, K. (2022). Evaluating the flooding level impacts on urban metro networks and travel demand: behavioral analyses, agent-based simulation, and large-scale case study. *Resilient Cities and Structures*, *1*(3), 12–23. https://doi.org/10.1016/j.rcns.2022.10.004

*Related studies*

Buchunde, S., Tang, Y., Nielsen, O. A., & Ingvardson, J. B. Departure Time Flexibility for Urban Rail Commuters. *Available at SSRN 6451838.* https://ssrn.com/abstract=6451838

Buchunde, S., & Tang, Y. Impact of Trip Characteristics on Passenger Departure Time Flexibility. *Available at SSRN 6598833.* https://ssrn.com/abstract=6598833

| Role | Members |
|---|---|
| **Scientific Team** | Yili Tang, Bingyu Zhao, Kenichi Soga, Xusong Zhou, Hai Yang, Surya Buchunde |
| **Developer Team** | Bingyu Zhao, Yili Tang, Surya Buchunde, Hongyu Shen |
| **Collaborating Team** | Stephen Wong, Mohamad Kahil |

---

## Table of Contents

1. [Overview](#1-overview)
   - [1.1 What is AAAM?](#11-what-is-aaam)
   - [1.2 Key Features](#12-key-features)
2. [Framework Architecture](#2-framework-architecture)
   - [2.1 Input Module](#21-input-module)
   - [2.2 Simulation Module](#22-simulation-module)
   - [2.3 Output Module](#23-output-module)
   - [2.4 Scenario Analysis Module](#24-scenario-analysis-module)
3. [Repository Structure](#3-repository-structure)
4. [Installation](#4-installation)
5. [Quick Start](#5-quick-start)
6. [Inputs](#6-inputs)
   - [6.1 Demand Data](#61-demand-data)
   - [6.2 GTFS Data](#62-gtfs-data)
7. [Citation](#7-citation)
8. [License](#8-license)

---

## 1. Overview

### 1.1 What is AAAM?

**AAAM** stands for **integrAted dAta-driven Agent-based siMulation**. It is a mesoscopic agent-based simulation framework for urban rail transit that combines two standard data sources:

- **Smartcard tap-in/tap-out records** (travel demand and validation ground truth)
- **GTFS transit feed** (network topology, train schedules, vehicle capacity)

The simulation represents the transit system as a directed network graph **G = (Z, A)**, where nodes **z ∈ Z** represent platforms or stations, and directed links **a ∈ A** represent rail linkages between platforms, walking paths connecting station entrances/exits to platforms, or transfer paths at interchange stations.

Three types of agents operate within this environment:

| Agent Type | Set | Role |
|---|---|---|
| **Platform agents** | K | Locations where passengers board/alight; track crowdedness μ_k(t) |
| **Passenger agents** | I | Individual travelers with origin o_i, destination d_i, departure time t_in_i |
| **Service run (train) agents** | J | Individual train services with arrival/departure schedule and vehicle capacity C_j |

The framework produces outputs across six visualization groups: traveler status over time, service traces, platform crowdedness, train trajectory crowding, smartcard validation, and per-trip occupancy.

### 1.2 Key Features

- **GTFS-native**: requires only three standard files — `stops.txt`, `stop_times.txt`, `trips.txt`
- **Sub-minute temporal resolution**: 20-second simulation timestep (ΔT = 20 s) captures train dwell times and platform dynamics
- **Capacity-constrained boarding**: denied boarding modelled explicitly when ν_j(t) ≥ C_j
- **Three routing criteria**: shortest dynamic travel time (with real-time congestion feedback), shortest timetable-based travel time, minimum number of stops
- **Dynamic rerouting**: passenger routes recomputed every 5 minutes using observed platform waiting times
- **Built-in smartcard validation**: compare simulated tap-out times against recorded smartcard tap-out data
- **Calibration scenarios**: parameter sweep over vehicle capacity and walking time to infer operational characteristics
- **Scalable**: 10–30 min runtime for a 7-hour simulation with 500k–3M passenger trips on a standard laptop
- **Short-turn train handling**: passengers temporarily alight at short-turn termini and reboard onward services

---

## 2. Framework Architecture

The AAAM is structured around four sequential modules, as described in the published framework (Zhao et al., 2026). The full framework diagram — including the network environment, agent interactions, and simulation flowchart — is described in the published paper (Zhao et al., 2026).

### 2.1 Input Module

Processes real-world data into simulation-ready agent characteristics. Two main data categories:

| Category | Content | Source |
|---|---|---|
| **Demand** | Origin o_i, destination d_i, departure time t_in_i; optional tap-out time t_out_i for validation | Smartcard AFC data, travel surveys, four-step model |
| **Supply** | Vehicle scheduling, train capacity C_j per service run | GTFS `trips.txt` + `stop_times.txt` + operator records |
| **Infrastructure** | Platform type, platform capacity S_k, walking time between entrance and platform | Operator records |
| **Network** | Station connectivity, link weights w_a, transfer walking paths | GTFS `stops.txt` + network construction |

**Code entry point:** `transit_sim/model/gtfs_utils.py` → `schedule_and_network_from_gtfs()`

### 2.2 Simulation Module

Each timestep (ΔT = 20 s) updates three agent types in strict sequence:

1. **Train agents** — moved along their fixed schedule; status classified as `stopped_at_platform_k` or `running_between_k_k'`
2. **Passenger agents** — state machine advances based on time elapsed and train positions
3. **Platform agents** — crowdedness μ_k(t) updated as count of all passenger agents in `waiting` status at platform k

The sequential update order is required: passenger boarding decisions depend on knowing the current train positions and remaining capacities.

**Code:** `transit_sim/model/trains.py`, `transit_sim/model/travelers.py`, `transit_sim/model/network.py`

### 2.3 Output Module

Produces outputs at multiple resolution levels from the per-timestep agent snapshots:

| Level | Output | Notebook section |
|---|---|---|
| **Traveler status** | Aggregate traveler state breakdown by timestep | `0200_transit_viz.ipynb` §1 |
| **Service trace** | Train trajectory diagrams by direction | `0200_transit_viz.ipynb` §2 |
| **Platform** | Crowdedness μ_k(t), queuing time per platform | `0200_transit_viz.ipynb` §3 |
| **Train trajectory crowding** | Occupancy heat map along each train run | `0200_transit_viz.ipynb` §4 |
| **Validation** | Simulated vs. smartcard tap-out time comparison | `0200_transit_viz.ipynb` §5 |
| **Train occupancy per trip** | Occupancy ν_j(t) per trip, grouped by direction | `0200_transit_viz.ipynb` §6 |

### 2.4 Scenario Analysis Module

Runs multiple simulation rounds with varied parameters to enable calibration and policy evaluation:

- **Parameter sweep**: vary `TRAIN_CAPACITY` (vehicle capacity C_j) and `EXIT_WALKING_PP`/`EXIT_WALKING_SP` (peak/off-peak walking time) in the CONFIG cell of `0100_transit_sim.ipynb`
- **Calibration metric**: mean and SD of (smartcard tap-out time − simulated tap-out time) in minutes
- **Policy scenarios**: infrastructure closures, capacity changes, demand increases — by modifying GTFS inputs or OD matrices

---

## 3. Repository Structure

```
AAAM/
├── transit_sim/                    # Core simulation framework
│   ├── model/
│   │   ├── gtfs_utils.py           # GTFS → Network/Schedule
│   │   ├── network.py              # Directed graph + 3 routing subgraphs
│   │   ├── trains.py               # Service run agent
│   │   ├── travelers.py            # Passenger agent FSM
│   │   ├── routing.py              # Serial Dijkstra
│   │   ├── routing_mp.py           # Parallel Dijkstra
│   │   └── config.py               # Global config
│   └── sp/                         # C++ shortest-path engine (vendored — build before first run)
│
├── code/
│   ├── 0001_gtfs_generation.ipynb  # Raw timetable + station geometry → GTFS CSVs
│   ├── 0010_od_generation.ipynb    # Smartcard AFC records → OD matrix CSV
│   ├── 0100_transit_sim.ipynb      # *** Run simulation ***
│   └── 0200_transit_viz.ipynb      # Visualizations and validation
│
├── raw_data/                       # Source timetables, station geometry, and smartcard OD records
├── transit_sim_inputs/             # Prepared GTFS and OD matrix files (output of 0001 + 0010)
├── transit_sim_outputs/            # Simulation results (output of 0100)
└── figs/                           # Figures and visualizations (output of 0200)
```

> All simulation results and figures are saved in `transit_sim_outputs/` and `figs/` respectively after running the notebooks.

---

## 4. Installation

### Prerequisites

- Python 3.7 or above
- [conda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html) (recommended for environment management)
- A C++ compiler (GCC, Clang, or MSVC) and CMake for the shortest-path engine

### Step 1 — Create a Python environment

```bash
conda create -n aaam python=3.9
conda activate aaam
conda install -c conda-forge geopandas pandas numpy matplotlib
```

### Step 2 — Build the C++ shortest-path engine

The Dijkstra routing relies on a compiled C++ library (`liblsp`). The source is included in `transit_sim/sp/` — no separate download required. Build it once before running simulations:

```bash
cd transit_sim/sp
mkdir build && cd build
cmake ..
make
```

This produces `liblsp.so` (Linux), `liblsp.dylib` (macOS), or `liblsp.dll` (Windows) in `transit_sim/sp/build/`. The Python interface (`transit_sim/sp/interface.py`) loads this library via `ctypes` at runtime.

### Step 3 — Verify installation

```bash
python -c "import sys; sys.path.insert(0, 'transit_sim'); from model.network import Network; print('OK')"
```

---

## 5. Quick Start

### Step 1 — Prepare your input files

Place your raw data in `raw_data/`, then run the two preparation notebooks in `code/` to generate the required files in `transit_sim_inputs/`. The notebooks are implemented for the Beijing Subway as a worked example — adapt them for your own data:

| Notebook | What it does | Adapt for your data |
|---|---|---|
| `0001_gtfs_generation.ipynb` | Converts station geometry + Excel timetable → GTFS CSVs in `transit_sim_inputs/` | Replace the QGIS shapefile and timetable Excel with your own sources |
| `0010_od_generation.ipynb` | Processes smartcard AFC records → OD matrix CSV in `transit_sim_inputs/` | Replace the AFC column parsing with your smartcard data schema |

After running the notebooks, verify that `transit_sim_inputs/` contains these four files — named exactly as shown, where `{LINE_CODE}` and `{DEMAND_SCEN_NM}` are the identifiers set in the notebooks:

```
gtfs_{LINE_CODE}_stops.csv
gtfs_{LINE_CODE}_trips.csv
gtfs_{LINE_CODE}_stop_times.csv
od_{DEMAND_SCEN_NM}.csv
```

> See Section 6 for the required columns in each file.

### Step 2 — Run the simulation

Open `code/0100_transit_sim.ipynb` and edit the **CONFIG** cell at the top to match your scenario:

```python
LINE_NUM       = "your_line_number"  # line identifier
SERVICE_ID     = "weekday"
SIM_DATE       = 'YYYY-MM-DD'
TRAIN_CAPACITY = 1960                # vehicle capacity C_j
EXIT_WALKING_PP = 90                 # peak walking time (seconds)
EXIT_WALKING_SP = 90                 # off-peak walking time (seconds)
T_START_HOUR   = 5
T_END_HOUR     = 12
```

Run all cells. Results are saved automatically to:

```
transit_sim_outputs/{LINE_CODE}_{SIM_DATE}_cap{TRAIN_CAPACITY}_wt{EXIT_WALKING_PP}-{EXIT_WALKING_SP}/
```

### Step 3 — Generate visualizations

Open `code/0200_transit_viz.ipynb`, set the **CONFIG** cell to match the values used in Step 2, then run all cells. The notebook produces six plot groups:

| Section | Output |
|---|---|
| §1 Traveler status over time | Aggregate traveler state breakdown by timestep |
| §2 Service trace | Train trajectory diagrams by direction |
| §3 Platform crowding | Crowdedness μ_k(t) per platform |
| §4 Train trajectory crowding | Occupancy heat map along each train run |
| §5 Validation | Simulated vs. smartcard tap-out time comparison |
| §6 Train occupancy per trip | Occupancy ν_j(t) per trip, grouped by direction |

---

## 6. Inputs

> **Note:** Data provided in this repository is for demonstration purposes only and does not represent actual system characteristics.

### 6.1 Demand Data

The demand input is a passenger-level OD matrix. Each row represents one smartcard transaction:

| Column | Type | Description |
|---|---|---|
| `in.station` | string | Origin station name (tap-in) |
| `out.station` | string | Destination station name (tap-out) |
| `in.time` | int | Departure time in seconds since midnight (e.g., 26573 = 7:22:53) |
| `out.time` | int | Observed tap-out time in seconds since midnight (used for validation) |
| `exit_type` | string | Record type flag (used for filtering validation sets) |

**Generating random OD data** (for testing without smartcard data): a `random_od()` method is available on `Travelers` instances in `transit_sim/model/travelers.py` to generate synthetic origin-destination pairs without real smartcard records.

### 6.2 GTFS Data

AAAM requires three standard GTFS files. No other GTFS files are needed.

| File | Key Columns Used |
|---|---|
| `stops.txt` | `stop_id`, `stop_name`, `stop_lat`, `stop_lon` |
| `stop_times.txt` | `trip_id`, `arrival_time`, `departure_time`, `stop_id`, `stop_sequence` |
| `trips.txt` | `trip_id`, `route_id`, `direction_id`, `service_id` |

**Capacity and calibration:** Vehicle capacity C_j is set via the `TRAIN_CAPACITY` parameter in the CONFIG cell of `0100_transit_sim.ipynb`. To calibrate against observed tap-out times, run multiple scenarios with varying `TRAIN_CAPACITY` values and compare outputs using §5 of `0200_transit_viz.ipynb`. Setting a very high capacity (e.g. 10,000) effectively removes the boarding constraint and serves as a sensitivity check.

---

## 7. Citation

If you use AAAM in your research, please cite:

```bibtex
@article{zhao2026aaam,
  title   = {Dynamic passenger crowding and operations in rail transit systems:
             a validated framework of integrated data-driven agent-based simulation ({AAAM})},
  author  = {Bingyu Zhao and Yili Tang and Kenichi Soga and Xuesong Zhou and Hai Yang},
  journal = {Journal of Rail Transport Planning \& Management},
  volume  = {38},
  pages   = {100586},
  year    = {2026},
  doi     = {10.1016/j.jrtpm.2026.100586},
  url     = {https://doi.org/10.1016/j.jrtpm.2026.100586}
}
```

*Funding: Social Sciences and Humanities Research Council of Canada; Natural Sciences and Engineering Research Council of Canada.*

---

## 8. License

This repository is provided for academic and research use only. See [LICENSE](LICENSE) for full terms. For inquiries, contact Dr. Yili (Kelly) Tang at research.motech@gmail.com and Dr. Bingyu Zhao at bingyu.zhao@tuwien.ac.at

---

*For questions or issues, please open a GitHub issue or contact the corresponding author.*
