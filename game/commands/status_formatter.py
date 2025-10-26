"""
status_formatter.py
───────────────────────────────────────────────
Converts the structured data dictionary from status_data.py
into formatted text lists for draw_status() rendering.
Produces:
  left[]   - Core stats, population, troops, spies, resources, buildings
  center[] - Bonuses, resource gain, training/building queues
  right[]  - Wars, attacks, spy ops
  messages[] - Read messages

"""


# ───────────────────────────────────────────────
# Helper: safe formatting
# ───────────────────────────────────────────────
def fmt_time(minutes):
    """Return a readable ETA string."""
    if minutes <= 0:
        return "arrived"
    return f"{int(minutes)}m"


def fmt_plural(count, word):
    """Pluralize a word if count != 1."""
    return f"{count} {word}{'' if count == 1 else 's'}"


# ───────────────────────────────────────────────────────────────
# Left Column
# ───────────────────────────────────────────────────────────────
def build_left(data):
    """Construct the LEFT column: city stats, resources, and buildings."""
    player = data["player"]
    resources = data["resources"]
    buildings = data["buildings"]

    left = []
    left.append(f"Player:   {player['name']}")
    left.append(f"Rank:     {player.get('rank', 'N/A')}")
    left.append(f"Prestige: {player['prestige']}")
    social = data.get("social", {})
    left.append(f"Happiness: {social.get('happiness', 0)}")
    left.append(f"Morale:    {social.get('morale', 0)}")
    left.append(f"Pop:      {player['population']} / {player['max_population']}")
    left.append(f"Troops:   {player['troops']} / {player['max_troops']}")
    left.append(f"  Garrisoned: {player.get('garrisoned', 0)}")
    left.append(f"  Deployed:   {player.get('deployed', 0)}")
    left.append(f"Spies:    {player['spies']} / {player['max_spies']}")
    left.append("")

    # ─── Resources (2-column dynamic) ───────────────────────────
    if resources:
        left.append("Resources:")
        res_items = list(resources.items())
        for i in range(0, len(res_items), 2):
            pair = res_items[i:i + 2]
            row = "  ".join([f"{k.capitalize()}: {int(v)}".ljust(15) for k, v in pair])
            left.append(f"  {row}")

    # ─── Buildings (2-column dynamic) ───────────────────────────
    if buildings:
        left.append("Buildings:")
        b_items = [(b["name"], b["level"]) for b in buildings]
        for i in range(0, len(b_items), 2):
            pair = b_items[i:i + 2]
            row = "  ".join([f"{name}: {lvl}".ljust(15) for name, lvl in pair])
            left.append(f"  {row}")

    # ─── Global Events Summary ───────────────────────────────────
    global_events = data.get("global_events", [])
    if global_events:
        left.append("")
        left.append("Global Events:")
        for i, ev in enumerate(global_events):
            prefix = " └" if i == len(global_events) - 1 else " ├"
            mod_text = f" ({ev['modifier']})" if 'modifier' in ev else ""
            left.append(f"{prefix}─ {ev['name']} ({ev['ticks']}t){mod_text}")

    # ─── Achievements Summary ───────────────────────────────────
    achievements = data.get("achievements", [])
    if achievements:
        left.append("")
        left.append("Achievements:")
        for i, ach in enumerate(achievements):
            prefix = " └" if i == len(achievements) - 1 else " ├"
            left.append(f"{prefix}─ {ach['name']}")

    return left


# ───────────────────────────────────────────────────────────────
# Center Column
# ───────────────────────────────────────────────────────────────
def build_center(data):
    """Construct the CENTER column: population, upkeep, income, combat, and queues."""
    player = data["player"]
    econ = data.get("economy", {})
    training = data["training"]
    bqueue = data["building_queue"]

    center = []

    # ─── Population Gain ────────────────────────────────────────
    try:
        from game.models.players import get_population_growth_rate
        growth = get_population_growth_rate(player["name"])
        center.append(f"Population Gain: +{growth:.2f}")
    except Exception:
        center.append("Population Gain: +0.00")

    # ─── Upkeep (total costs, negative values) ──────────────────
    center.append("Upkeep:")
    if econ and "upkeep" in econ:
        u = econ["upkeep"]
        u_items = list(u.items())
        for i in range(0, len(u_items), 2):
            pair = u_items[i:i + 2]
            row = "  ".join([f"{k.capitalize()}: {v:+.2f}".ljust(15) for k, v in pair])
            center.append(f"  {row}")

    # ─── Income (total positive flow from buildings) ────────────
    # ─── Income (includes taxation policy) ─────────────────────
    tax = data.get("taxation", {})
    center.append(f"Income & Tax Policy:")
    center.append(
        f"  Taxes ({tax.get('policy', 'Unknown')} – {tax.get('rate', 0):.0f}%): "
        f"+{tax.get('income', 0):.2f}g"
    )
    if econ and "income" in econ:
        n = econ["income"]
        n_items = list(n.items())
        for i in range(0, len(n_items), 2):
            pair = n_items[i:i + 2]
            row = "  ".join([f"{k.capitalize()}: {v:+.2f}".ljust(15) for k, v in pair])
            center.append(f"  {row}")

    # ─── Combat Bonuses ─────────────────────────────────────────
    center.append("Combat Bonuses:")
    center.append(f"  Def: {player['defense_bonus']:.2f}x  Atk: {player['attack_bonus']:.2f}x")

    ci = float(player.get("counterintelligence_penalty", 0.0))
    ci_pct = int(round(ci * 100))
    wt_lvls = int(player.get("watchtower_levels", 0))
    center.append(f"  Counterintelligence: {ci_pct}%")

    # ─── Training / Building Queues (2-column alignment) ────────
    tq = training["troops"] + training["spies"]
    bq = bqueue

    if tq or bq:
        center.append("Training / Building Queues:")
        left_col_width = 22  # fixed padding for alignment
        for i in range(max(len(tq), len(bq))):
            left_entry = tq[i] if i < len(tq) else ""
            right_entry = bq[i] if i < len(bq) else ""
            line = f"  {left_entry.ljust(left_col_width)}{right_entry}"
            center.append(line.rstrip())
    else:
        center.append("Training / Building Queues: None")

    return center


# ───────────────────────────────────────────────
# Right Column
# ───────────────────────────────────────────────
def build_right(data):
    """
    Construct the RIGHT column: wars, outgoing attacks, and espionage.
    Matches locked-in minimal War Room design.
    """
    wars_data = data["wars_attacks"]
    wars = wars_data.get("wars", [])
    outgoing = wars_data.get("outgoing", [])
    incoming = wars_data.get("incoming", [])
    spies = data.get("spies", [])

    right = []

    # ─── Current Wars ─────────────────────────────────────────────
    if wars:
        right.append("Current Wars:")
        for w in wars:
            enemy = w.get("enemy", "Unknown")
            right.append(f"  {enemy}")
            # Display incoming attacks under that enemy, no label, just troops and ETA
            for a in incoming:
                if a.get("attacker_name") == enemy:
                    right.append(f"    {a['troops_sent']} troops ({fmt_time(a['eta'])})")
    # no wars, omit section entirely

    # ─── Outgoing Attacks ─────────────────────────────────────────
    if outgoing:
        right.append("Outgoing Attacks:")
        for a in outgoing:
            target = a.get("defender_name", "Unknown")
            troops = a.get("troops_sent", 0)
            eta = fmt_time(a.get("eta", 0))
            right.append(f"  {target} – {troops} troops ({eta})")
    # else: omit section entirely for clean compression

    # ─── Diplomatic Relations ──────────────────────────────────
    rel = data.get("relations", {})
    if rel:
        right.append("Relations:")
        right.append(
            f"  Allies:{rel['allies']}   Enemies:{rel['enemies']}"
        )
        right.append(
            f"  Neutral:{rel['neutral']}  Avg Trust:{rel['avg_trust']:+.0f}"
        )

    # ─── Spy Operations ───────────────────────────────────────────
    if spies:
        right.append("Spy Operations:")
        for s in spies:
            right.append(f"  {s}")
    # else: omit entirely

    return right


# ───────────────────────────────────────────────
# Formatter Orchestrator
# ───────────────────────────────────────────────
def format_status(data):
    """
    Combine all formatted column data into ready-to-render lists
    for draw_status(left, center, right, messages).
    """
    left = build_left(data)
    center = build_center(data)
    right = build_right(data)
    messages = data["messages"]
    return left, center, right, messages


# ───────────────────────────────────────────────────────────────
# Strategic (Detailed) Formatter
# ───────────────────────────────────────────────────────────────
def format_detailed_status(data: dict):
    """
    Build formatted columns for the detailed strategic readout.
    Returns (left, center, right, messages).
    """

    # ─── LEFT COLUMN ─────────────────────────────────────────────
    left = []
    city = data.get("city_overview", {})
    social = city.get("social", {})

    left.append(f"Rank: {city.get('rank', 'N/A')}")
    left.append(f"Prestige: {city.get('prestige', 0)}")
    left.append(f"Happiness: {social.get('happiness', 0)} (Content)")
    left.append(f"Morale:    {social.get('morale', 0)} (Steady)")

    pop = city.get("population", {})
    left.append(f"Pop: {pop.get('current', 0)} / {pop.get('max', 0)}")
    troops = city.get("troops", {})
    left.append(f"Troops: {troops.get('current', 0)} / {troops.get('max', 0)}")
    left.append(f" ├─ Garrisoned: {troops.get('garrisoned', 0)}")
    left.append(f" └─ Deployed:   {troops.get('deployed', 0)}")
    spies = city.get("spies", {})
    left.append(f"Spies: {spies.get('current', 0)} / {spies.get('max', 0)}")

    # Resources & Buildings
    res = city.get("resources", {})
    if res:
        left.append("")
        left.append("Resources:")
        items = list(res.items())
        for i in range(0, len(items), 2):
            pair = items[i:i + 2]
            row = "  ".join([f"{k.capitalize()}: {int(v)}".ljust(15) for k, v in pair])
            left.append(f"  {row}")

    bldgs = city.get("buildings", [])
    if bldgs:
        left.append("Buildings:")
        b_items = [(b['name'], b['level']) for b in bldgs]
        for i in range(0, len(b_items), 2):
            pair = b_items[i:i + 2]
            row = "  ".join([f"{n}: {lvl}".ljust(15) for n, lvl in pair])
            left.append(f"  {row}")

    # Events & Achievements
    events = city.get("global_events", [])
    if events:
        left.append("")
        left.append("Global Events:")
        for i, ev in enumerate(events):
            prefix = " └─" if i == len(events) - 1 else " ├─"
            mod_text = f" ({ev['modifier']})" if 'modifier' in ev else ""
            left.append(f"{prefix} {ev['name']} ({ev['ticks']}t){mod_text}")

    ach = city.get("achievements", [])
    if ach:
        left.append("")
        left.append("Achievements:")
        for i, a in enumerate(ach):
            prefix = " └─" if i == len(ach) - 1 else " ├─"
            left.append(f"{prefix} {a['name']}")

    # ─── CENTER COLUMN ───────────────────────────────────────────
    center = []
    econ = data.get("economy", {})
    pop_gain = econ.get("population_gain", {})

    # Population Gain totals first
    center.append(f"Population Gain: +{pop_gain.get('total', 0):.2f}")
    center.append(f" ├─ Base Growth: +{pop_gain.get('base', 0):.2f}")
    for name, val in pop_gain.get("buildings", {}).items():
        center.append(f" ├─ {name}: +{val:.2f}")
    mods = pop_gain.get("modifiers", {})
    center.append(f" ├─ Happiness Modifier: {mods.get('happiness', 0):+.0f}%")
    center.append(f" └─ Morale Modifier: {mods.get('morale', 0):+.0f}%")

    # Upkeep & Income
    center.append("")
    center.append("Upkeep per Resource:")
    for res_name, sources in econ.get("upkeep", {}).items():
        subtotal = sum(sources.values())
        center.append(f" {res_name.capitalize()}: -{abs(subtotal):.2f}")
        for src, val in sources.items():
            center.append(f"   └─ {src}: -{abs(val):.2f}")

    center.append("")
    center.append("Income per Resource:")
    for res_name, sources in econ.get("income", {}).items():
        subtotal = sum(sources.values())
        center.append(f" {res_name.capitalize()}: {subtotal:+.2f}")
        for src, val in sources.items():
            center.append(f"   └─ {src}: {val:+.2f}")

    # Taxation
    tax = econ.get("taxation", {})
    if tax:
        center.append("")
        center.append(f"Tax Policy: {tax.get('policy', 'Unknown')} ({tax.get('rate', 0):.0f}%)")
        center.append(f" ├─ Population Tax Income: +{tax.get('income', 0):.2f}g")
        center.append(f" └─ Policy Modifier: +10%")

    # ─── RIGHT COLUMN ────────────────────────────────────────────
    right = []
    war = data.get("war_room", {})
    cb = war.get("combat_bonuses", {})

    # Combat bonuses with totals first
    right.append("Combat Bonuses:")
    for kind, entry in cb.items():
        total = entry.get("total", 0)
        right.append(f" {kind.capitalize()}: {total:.2f}x")
        for name, val in (entry.get("buildings") or {}).items():
            if val != 0:
                right.append(f"   └─ {name}: +{val:.2f}x")

    # Spy success section
    spy_success = war.get("spy_success", {})
    if spy_success:
        right.append("")
        right.append("Intelligence:")
        right.append(
            f"  ├─ Scout Success:    {int(spy_success['scout'] * 100)}% (Adj:+{int(spy_success['academy_bonus'] * 100)}%)"
        )
        right.append(
            f"  ├─ Steal Success:    {int(spy_success['steal'] * 100)}% (Adj:+{int(spy_success['academy_bonus'] * 100)}%)"
        )
        right.append(
            f"  ├─ Sabotage Success: {int(spy_success['sabotage'] * 100)}% (Adj:+{int(spy_success['academy_bonus'] * 100)}%)"
        )
        right.append(
            f"  └─ Academies Bonus:  +{spy_success['academy_bonus']:.2f}x per level"
        )

    # Relations moved above wars
    rel = war.get("relations", {})
    if rel:
        right.append("")
        right.append("Relations:")
        right.append(f"  Allies:{rel['allies']}   Enemies:{rel['enemies']}")
        right.append(f"  Neutral:{rel['neutral']}  Avg Trust:{rel['avg_trust']:+.0f}")

    # ─── Wars ────────────────────────────────────────────────────
    wars = war.get("wars", [])
    if wars:
        right.append("")
        right.append("Current Wars:")
        # wars may be a dict or list
        if isinstance(wars, dict):
            iterable = wars.items()
        else:
            iterable = [(w.get("enemy", "Unknown"), w) for w in wars]

        for enemy, details in iterable:
            right.append(f" ├─ {enemy}")

            incoming = details.get("incoming", []) if isinstance(details, dict) else []
            outgoing = details.get("outgoing", []) if isinstance(details, dict) else []

            # Normalize and render attacks with counts and ETAs
            if incoming:
                right.append(" │   Incoming:")
                for atk in incoming:
                    troops = atk.get("troops_sent", atk.get("troops", 0))
                    eta = atk.get("eta", "?")
                    right.append(f" │     └─ {troops} troops ({eta}t)")
            if outgoing:
                right.append(" │   Outgoing:")
                for atk in outgoing:
                    troops = atk.get("troops_sent", atk.get("troops", 0))
                    eta = atk.get("eta", "?")
                    right.append(f" │     └─ {troops} troops ({eta}t)")
        right.append("")

    # ─── Spy Network ─────────────────────────────────────────────
    spy = war.get("spy_network", {})
    if spy:
        right.append("Spy Network:")
        # Active Missions
        if spy.get("active"):
            right.append("  Active Missions:")
            for m in spy["active"]:
                action = m.get("action", "?")
                target = m.get("target", "?")
                age = m.get("age", "?")
                right.append(f"   └─ {action} → {target} ({age}t)")

        # Intel Reports
        if spy.get("intel"):
            right.append("  Intel Reports:")
            for i in spy["intel"]:
                target = i.get("target", "?")
                age = i.get("age", "?")
                right.append(f"   └─ {target} (Age: {age}t)")

        # Mission History
        if spy.get("history"):
            right.append("  Mission History:")
            for h in spy["history"]:
                action = h.get("action", "?")
                target = h.get("target", "?")
                outcome = "Success" if h.get("success") else "Failed"
                age = h.get("age", "?")
                right.append(f"   └─ {action} {target} [{outcome}] ({age}t)")
        right.append("")

    # ─── Recent Battles ──────────────────────────────────────────
    battles = war.get("recent_battles", [])
    if battles:
        right.append("Recent Battles:")
        for b in battles:
            right.append(
                f" └─ {b['outcome']} vs {b['opponent']} "
                f"(A:{b['attacker_losses']} D:{b['defender_losses']}) [{b['age']}t]"
            )

    # ─── FOOTER ──────────────────────────────────────────────────
    footer = data.get("messages", "Messages: None")

    return left, center, right, footer

