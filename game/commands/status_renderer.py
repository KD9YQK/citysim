import textwrap
from game.commands.status_data import get_status_data, get_detailed_status_data
from game.commands.status_formatter import format_status, format_detailed_status


async def draw_status(title=None, left=None, center=None, right=None, messages=None):
    """
    Build a three-column City Sim status display.\r\n
    Each argument is a list of strings.\r\n
    <title> Expects ['Left Title', 'Center Title', Right Title'] \r\n
    Returns a 'CRLF'-terminated string suitable for Telnet output.
    """
    left, center, right, messages = left or [], center or [], right or [], messages or []

    # --- Equalize row count ---
    max_rows = max(len(left), len(center), len(right))
    rows = list(zip(
        [left[i] if i < len(left) else "" for i in range(max_rows)],
        [center[i] if i < len(center) else "" for i in range(max_rows)],
        [right[i] if i < len(right) else "" for i in range(max_rows)]
    ))

    widths = _measure_widths(rows)

    # --- Build output ---
    out = []
    out.append(_border("top", widths))
    out.append(_row([title[0], title[1], title[2]], widths))
    out.append(_border("mid", widths))
    for r in rows:
        out.append(_row(r, widths))
    out.append(_border("bottom", widths))

    # --- Messages footer ---
    msg_width = sum(widths) + (len(widths) * 3) - 1
    out.append("┌" + "─" * msg_width + "┐")
    out.append(("│ Messages:".ljust(msg_width + 1)) + "│")
    if messages:
        for m in messages:
            for line in textwrap.wrap(m, msg_width - 1):
                out.append("│ " + line.ljust(msg_width - 1) + "│")
    else:
        out.append("│ No unread messages.".ljust(msg_width + 1) + "│")
    out.append("└" + "─" * msg_width + "┘")

    # join with CRLF
    return "\r\n".join(out) + "\r\n"


# ──────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────
def _measure_widths(rows, min_widths=(32, 32, 40), pad=2):
    """Find ideal width for each column, right one slightly larger."""
    widths = [w for w in min_widths]
    for row in rows:
        for i, col in enumerate(row):
            for line in col.split("\n"):
                needed = len(line) + pad
                if needed > widths[i]:
                    widths[i] = needed
    widths[-1] = int(widths[-1] * 1.1)
    return widths


def _border(kind, widths):
    """Draw box borders that always align perfectly on right edge."""
    # +3 accounts for " │ " between columns
    segs = ["─" * (w + 2) for w in widths]
    join = {"top": "┬", "mid": "┼", "bottom": "┴"}[kind]
    left, right = {"top": ("┌", "┐"), "mid": ("├", "┤"), "bottom": ("└", "┘")}[kind]
    return left + join.join(segs) + right


def _row(cols, widths):
    """Render a single row with proper column alignment and CRLF endings."""
    wrapped = []
    for c, w in zip(cols, widths):
        segs = []
        for para in c.split("\n"):
            segs.extend(textwrap.wrap(para, width=w) or [""])
        wrapped.append(segs)
    height = max(len(x) for x in wrapped)
    lines = []
    for i in range(height):
        cells = []
        for segs, w in zip(wrapped, widths):
            line = segs[i] if i < len(segs) else ""
            cells.append(line.ljust(w))
        # note: 1 space padding left/right per column, always ends with │
        lines.append("│ " + " │ ".join(cells) + " │")
    return "\r\n".join(lines)


# ───────────────────────────────────────────────
# Strategic Detailed Renderer
# ───────────────────────────────────────────────
async def render_status(session, player_name: str, detailed: bool = False):
    """
    Build and render either the standard or the detailed strategic
    status display. Uses the existing draw_status() for layout.
    """
    if detailed:
        data = get_detailed_status_data(player_name)
        left, center, right, messages = format_detailed_status(data)
        title = ["CITY OF " + player_name.upper(),
                 "ECONOMY & POPULATION",
                 "WAR ROOM"]
    else:
        data = get_status_data(player_name)
        left, center, right, messages = format_status(data)
        title = ["CITY STATUS", "ECONOMY", "OPERATIONS"]

    rendered = await draw_status(title, left, center, right, messages)
    await session.send(rendered)
