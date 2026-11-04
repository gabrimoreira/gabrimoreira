#!/usr/bin/env python3
"""Play Conway's Game of Life on the GitHub contribution graph and write animated SVGs.

Usage: life.py OUTPUT_DIR

Frame 0 is the real graph, then every generation follows Conway's rules. A surviving cell
keeps its shade of green and a newborn takes the mean of its three parents. The animation
stops at the first repeated state and loops. On any failure nothing is written.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "gabrimoreira")
HEIGHT = 7
MAX_GENERATIONS = 120
PITCH = 16  # 12px cell plus a 4px gap: an 8px square with a 4px round stroke
HOLD_START, STEP, HOLD_END = 2.5, 0.16, 2.0  # seconds

QUERY = """query($login: String!) {
  user(login: $login) { contributionsCollection { contributionCalendar {
    weeks { contributionDays { weekday contributionLevel } }
  } } }
}"""
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

# GitHub's own contribution graph colors, from no contributions to the most.
THEMES = {
    "light": ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
    "dark": ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
}


def fetch_calendar():
    """Return (width, {(week, weekday): level}) for the days with contributions."""
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "profile-readme",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise ValueError(payload["errors"][0].get("message", "GraphQL error"))
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    if not weeks:
        raise ValueError("empty contribution calendar")
    cells = {
        (x, day["weekday"]): LEVELS[day["contributionLevel"]]
        for x, week in enumerate(weeks)
        for day in week["contributionDays"]
        if day["contributionLevel"] != "NONE"
    }
    return len(weeks), cells


def next_generation(cells, width):
    """Apply Conway's rules on a bounded grid."""
    parents = {}
    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near = (x + dx, y + dy)
                if (dx or dy) and 0 <= near[0] < width and 0 <= near[1] < HEIGHT:
                    parents.setdefault(near, []).append(cells[(x, y)])
    result = {}
    for cell, levels in parents.items():
        if len(levels) == 3 and cell not in cells:
            result[cell] = round(sum(levels) / 3)
        elif len(levels) in (2, 3) and cell in cells:
            result[cell] = cells[cell]
    return result


def simulate(seed, width):
    """Return the generations from the seed to the first repeated state."""
    generations, seen = [seed], {frozenset(seed)}
    for _ in range(MAX_GENERATIONS):
        current = next_generation(generations[-1], width)
        generations.append(current)
        if frozenset(current) in seen:
            break
        seen.add(frozenset(current))
    return generations


def squares(cells):
    """Compact path data, with each square positioned relative to the previous one."""
    parts, last_x, last_y = [], 0, 0
    for x, y in sorted(cells):
        left, top = x * PITCH + 2, y * PITCH + 2
        parts.append(f"m{left - last_x} {top - last_y}h8v8h-8z")
        last_x, last_y = left, top
    return "".join(parts)


def frame_paths(previous, current):
    """Draw a generation; cells that just died linger for one frame in the faintest green."""
    by_level = {level: [] for level in range(1, 5)}
    for cell, level in current.items():
        by_level[level].append(cell)
    if previous is not None:
        by_level[1].extend(cell for cell in previous if cell not in current)
    return "".join(f'<path class="l{level}" d="{squares(cells)}"/>' for level, cells in by_level.items() if cells)


def render(generations, width, palette):
    durations = [HOLD_START] + [STEP] * (len(generations) - 2) + [HOLD_END]
    total = sum(durations)
    frames, clock = [], 0.0
    for index, generation in enumerate(generations):
        name = "start" if index == 0 else "end" if index == len(generations) - 1 else "step"
        previous = generations[index - 1] if index else None
        frames.append(
            f'<g class="f f{index}" style="animation-name:{name};animation-delay:{clock:.2f}s">'
            f"{frame_paths(previous, generation)}</g>"
        )
        clock += durations[index]
    keyframes = "".join(
        f"@keyframes {name}{{0%{{visibility:visible}}{seconds / total * 100:.3f}%,100%{{visibility:hidden}}}}"
        for name, seconds in (("start", HOLD_START), ("step", STEP), ("end", HOLD_END))
    )
    colors = "".join(f".l{i}{{fill:{color};stroke:{color}}}" for i, color in enumerate(palette))
    background = squares((x, y) for x in range(width) for y in range(HEIGHT))
    view_width, view_height = width * PITCH - 4, HEIGHT * PITCH - 4
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_width} {view_height}" '
        f'width="{view_width}" height="{view_height}" role="img" aria-labelledby="t">'
        f'<title id="t">Conway\'s Game of Life played on the GitHub contribution graph of {USER}</title>'
        f"<style>path{{stroke-width:4;stroke-linejoin:round}}{colors}"
        f".f{{visibility:hidden;animation-duration:{total:.2f}s;"
        "animation-timing-function:step-end;animation-iteration-count:infinite}"
        f"{keyframes}"
        "@media (prefers-reduced-motion:reduce){.f{animation:none}.f0{visibility:visible}}</style>"
        f'<path class="l0" d="{background}"/>{"".join(frames)}</svg>\n'
    )


def main():
    if len(sys.argv) != 2:
        print("Usage: life.py OUTPUT_DIR", file=sys.stderr)
        return 2
    try:
        width, seed = fetch_calendar()
    except (urllib.error.URLError, TimeoutError, KeyError, TypeError, ValueError) as error:
        print(f"::error::Could not read the contribution calendar: {error}", file=sys.stderr)
        return 1
    generations = simulate(seed, width)
    images = {theme: render(generations, width, palette) for theme, palette in THEMES.items()}
    for theme, svg in images.items():
        (Path(sys.argv[1]) / f"life-{theme}.svg").write_text(svg, encoding="utf-8")
    print(f"{len(seed)} active days, {len(generations)} frames, {len(images['dark']) // 1024} KB per image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
