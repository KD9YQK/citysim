# 🏙️ CITY SIM

**Version:** Development (Updated 2025-10-21)  
**Type:** Asynchronous City Simulation / Strategy Engine  
**Language:** Python 3.x  
**Persistence:** SQLite  
**Interface:** Telnet (Player + Admin)

---

## 📖 Overview

**CITY SIM** is a tick-driven asynchronous simulation game combining **city-building**, **economy management**, **AI-driven diplomacy**, and **espionage** systems.  
Each in-game tick advances the simulation — updating populations, resources, AI behaviors, achievements, and global market conditions — creating an evolving and reactive world.

---

## ⚙️ Core Gameplay & Simulation

| Gameplay Aspect | Description | Key Files / Modules |
|-----------------|--------------|----------------------|
| **Tick-Driven Simulation Loop** | Asynchronous loop advancing all systems (population, combat, AI, espionage, economy, prestige, etc.) | `world.py`, `main.py`, `utils.py`, `config.yaml` |
| **Persistent Database** | SQLite persistence with automatic schema creation and thread-safe access | `db.py` |
| **Models & Core Logic** | City state management: resources, population, buildings, training, wars | `models.py` |
| **Combat System** | Player/NPC battles, casualties, loot, peace resolution | `actions.py`, `models.py` |
| **Economy (Expanded)** | Multi-resource generation, tick-based updates, and dynamic market pricing | `resources_base.py`, `economy.py`, `market_base.py` |
| **Population Management** | Growth logic implemented; upkeep and starvation pending | `models.py`, `world.py` |
| **Achievements** | Milestones and titles validated each tick | `achievements.py`, `achievements_config.yaml` |
| **Ranking / Prestige** | Leaderboard recalculated from weighted resource values | `ranking.py`, `config.yaml` |
| **NPC AI** | Personality-driven decisions (Aggressor, Defender, Economist, Opportunist) handling warfare, espionage, and economy | `npc_ai.py`, `npc_config.yaml` |
| **Espionage** | Spy training, scouting, theft, sabotage, and intel | `espionage.py`, `models.py` |
| **Events & Messaging** | Random and narrative events with persistent message log | `events.py`, `random_events.py`, `lore.py` |
| **Telnet Command Interface** | Async Telnet server for player/admin interaction | `telnet_server.py`, `commands.py`, `admin_commands.py` |
| **Admin Tools** | Inspect/modify world state, broadcast, grant resources | `admin_commands.py` |
| **Logging Framework** | Unified colorized logger by category | `logger.py`, `config.yaml` |
| **Utility Functions** | YAML config loader, tick math, helpers | `utils.py` |

---

## 🗂️ Configuration & Data Files

| File | Purpose |
|------|----------|
| `config.yaml` | Global tick timing, prestige weights, constants |
| `npc_config.yaml` | AI personalities and behavior weights |
| `buildings_config.yaml` | Building definitions and bonuses |
| `resources_config.yaml` | Resource definitions (type, base_price, supply) and market params |
| `achievements_config.yaml` | Milestone thresholds and titles |
| `world_events_config.yaml` | Placeholder for large-scale world trade events |
| `lore.yaml` | Optional lore text for random world flavor |

---

## 🧩 Support Modules & Secondary Features

| Feature | Description | Files |
|----------|--------------|-------|
| **Lore & Flavor** | Randomized lore messages to enrich gameplay | `lore.py` |
| **Random Events** | Small per-tick effects for flavor or minor economic shifts | `random_events.py` |
| **Event Messaging** | Backend for in-game notifications and mail | `events.py` |
| **Utility Loader** | Safe YAML loading, tick math, conversion helpers | `utils.py` |
| **Logging Configuration** | Categories, colors, verbosity | `logger.py` |

---

## 🚧 Implementation Status (as of 2025-10-21)

| System | State | Notes |
|--------|--------|-------|
| Multi-Resource Base Layer | ✅ Complete | `resources_base.py` consolidates all resource logic |
| Economy Integration | ✅ Complete | All modules converted to use unified resource base |
| Global Market System | ✅ Complete | `market_base.py` supports dynamic supply/demand pricing |
| Ranking Refactor | ✅ Complete | Prestige computed from resource × base_price |
| NPC / Espionage / Event Updates | ✅ Complete | All economy calls routed via unified layer |
| Combat System | ⚙️ Functional | Uses unified resource handling |
| Food Upkeep / Consumption | ⏳ Pending | To be added in population tick updates |
| Trade Events | ⏳ Planned | Placeholder config exists, engine pending |
| AI Economic Behavior | ⏳ Pending | Will follow upkeep implementation |

---

## ⚠️ Current Implementation Gaps

- No per-tick **food/gold upkeep** for population or armies  
- No **market participation logic** for NPCs  
- No **global world/trade events** yet applied  
- No **dynamic AI trait feedback** from economic performance  

---

## 🗺️ Economic Expansion Roadmap

| Step | Feature | Status | Description |
|------|----------|---------|--------------|
| 1 | Multi-Resource Base Layer | ✅ | Unify all resource accounting (I/O, validation, DB) |
| 2 | Global Market System | ✅ | Dynamic pricing, player ↔ market trading |
| 3 | Upkeep & Consumption System | ⏳ | Food/gold upkeep for population, armies, buildings |
| 4 | Comprehensive Resource Integration | ⏳ | Ensure every system routes through unified layer |
| 5 | NPC Economic Planning | ⏳ | AI evaluates shortages, builds, and trades |
| 6 | NPC Market Behavior | ⏳ | NPCs buy/sell with market based on needs/personality |
| 7 | Economic Trait Feedback | ⏳ | AI traits evolve from economic success/failure |
| 8 | World Trade Events | ⏳ | Global booms/famines affect supply/demand |

---

## 🧠 Architecture Notes

- **Asynchronous Tick System:** Every system advances in coordinated, non-blocking ticks.
- **SQLite Persistence:** Safely handles concurrent writes via lightweight transaction layer.
- **Data-Driven Configuration:** All gameplay constants, building stats, and resources defined in YAML.
- **AI Modularity:** Personalities are data-defined; behaviors easily extended via config.

---

## 🧩 Running the Simulation

**Start the simulation:**
```bash
python main.py
