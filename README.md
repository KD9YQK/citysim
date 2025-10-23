# 🏙️ CITY SIM  
**Persistent Economic & AI Simulation Engine**  
**Updated:** 2025-10-21

---

## 📖 Overview
**City Sim** is a persistent, tick-driven simulation game modeling the **economic**, **social**, and **military** dynamics of both player- and NPC-controlled cities.  
Every game tick advances all systems — population, economy, construction, warfare, espionage, AI, and global events — within an asynchronous, data-driven world.

---

## ⚙️ Core Gameplay & Simulation

| Gameplay Aspect | Description | Key Files / Modules |
|-----------------|--------------|----------------------|
| **Tick-Driven Simulation Loop** | Asynchronous loop advancing all systems each tick — population, construction, combat, AI, espionage, economy, events, prestige. | `world.py`, `main.py`, `utils.py`, `config.yaml` |
| **Persistent Database** | SQLite persistence layer with schema auto-creation, thread-safe transactions, and pooled queries. | `db.py` |
| **Models & Core Logic** | Defines players, NPCs, resources, armies, and building logic. Handles wars, city growth, and effects. | `models.py` |
| **Combat System** | Resolves battles, casualties, and loot using the unified resource system. | `actions.py`, `models.py` |
| **Economy (Expanded)** | Implements unified resource persistence, global supply-based pricing, and player/NPC trading. | `resources_base.py`, `economy.py`, `market_base.py` |
| **Population & Upkeep System** | Deducts food/gold per tick; enforces starvation and morale penalties. | `upkeep_system.py`, `world.py`, `upkeep_config.yaml` |
| **Achievements** | Awards milestones and prestige-based titles. | `achievements.py`, `achievements_config.yaml` |
| **Ranking & Prestige** | Calculates prestige from weighted resource values; updates leaderboard per tick. | `ranking.py`, `config.yaml` |
| **NPC AI** | Personality-driven logic with evolving traits (greed, risk, trade bias). | `npc_ai.py`, `npc_market_behavior.py`, `npc_trait_feedback.py`, `npc_config.yaml` |
| **Espionage** | Spy training, scouting, sabotage, theft, and intel generation. | `espionage.py`, `models.py` |
| **Events & Messaging** | Central event hub with world trade events and notifications. | `events.py`, `random_events.py`, `world_events.py` |
| **Telnet Command Interface** | Async command system for player/admin control. | `telnet_server.py`, `commands.py`, `admin_commands.py` |
| **Admin Tools** | Inspect, broadcast, and modify world state. | `admin_commands.py` |
| **Logging Framework** | Unified, color-coded logger for AI, economy, and world systems. | `logger.py`, `config.yaml` |
| **Utility Functions** | YAML loaders, tick/time conversion, and helpers. | `utils.py` |

---

## CONFIGURATION
All balance and world data are defined in YAML files under `/config`:

| File | Purpose |
|------|----------|
| `config.yaml` | Global constants, tick timing, prestige weights, economy volatility |
| `npc_config.yaml` | AI tuning: trade thresholds, personality traits, evolution rates |
| `buildings_config.yaml` | Building definitions, production modifiers, and costs |
| `resources_config.yaml` | Canonical resource data (base price, volatility, supply) |
| `upkeep_config.yaml` | Defines per-tick costs for population, armies, and structures |
| `achievements_config.yaml` | Achievement requirements and prestige bonuses |
| `world_events_config.yaml` | Defines global market/environmental events |
| `lore.yaml` | Optional narrative flavor text |

---

## 🧩 Support Modules & Secondary Features

| Feature | Description | Files |
|----------|--------------|-------|
| **Lore & Flavor** | Adds dynamic lore messages and storylines. | `lore.py` |
| **Random Events** | Tick-based minor world fluctuations. | `random_events.py` |
| **Event Messaging** | Central message delivery and notification system. | `events.py` |
| **Utility Loader** | Safe YAML loading and tick math utilities. | `utils.py` |
| **Logging Configuration** | Color themes, verbosity, structured categories. | `logger.py` |

---

## 🚀 Implementation Status (As of Step 8 Completion)

| System | State | Notes |
|--------|--------|-------|
| **Multi-Resource Base Layer** | ✅ Complete | Unified resource management for all modules |
| **Global Market System** | ✅ Complete | Supply/demand pricing and market trading |
| **Population Upkeep & Consumption** | ✅ Complete | Starvation, desertion, morale logic implemented |
| **Comprehensive Resource Integration** | ✅ Complete | All systems use `resources_base` |
| **NPC Economic Planning** | ✅ Complete | NPCs maintain balanced food/gold intelligently |
| **NPC Market Behavior** | ✅ Complete | Adaptive trading based on market ratios/events |
| **Economic Trait Feedback** | ✅ Complete | Dynamic evolution of NPC traits |
| **World Trade Events** | ✅ Complete | Configurable global modifiers affect prices/trade |
| **Ranking & Prestige** | ✅ Complete | Integrated with economy and events |
| **Combat & Espionage** | ⚙️ Functional | Fully connected to economy and persistence layers |

---

## 🌍 World Trade Event System

Implemented via `world_events.py` and `world_events_config.yaml`.

Each event defines:
- **chance**  •  **duration**  •  **effects**  •  **messages**

Effects may modify:
- `global_price_mult`
- `npc_trade_rate_mult`
- Resource-specific multipliers

### Example Events
| Event | Effect |
|--------|---------|
| **Harvest Boom** | Abundant food, reduced prices |
| **Iron Shortage** | Scarcity raises metal prices |
| **Drought Season** | Increases food/water prices |
| **Prosperity Wave** | Boosts trade and production |
| **Trade Embargo** | Reduces trade volume, increases scarcity |
| **Technological Breakthrough** | Improves efficiency, lowers costs |
| **War Mobilization** | Raises demand for metals/weapons |

All event parameters are modular and easily balanced via configuration.

---



## 🧰 Dependencies

- Python 3.10 +  
- `aiosqlite`  
- `pyyaml`  
- `asyncio`  
- `colorama`  

---

## ▶️ Running the Simulation

```bash
python main.py
