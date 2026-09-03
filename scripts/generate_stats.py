#!/usr/bin/env python3
"""Draws the profile's SVGs from the GitHub GraphQL API. Stdlib only."""
import base64
import datetime
import json
import math
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
LOGIN = os.environ.get("GH_LOGIN")
TOKEN = os.environ.get("GITHUB_TOKEN")
API_URL = "https://api.github.com/graphql"

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#58a6ff"
RAMP = " .`:-=+*cs#%@"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $after: String) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date weekday contributionCount }
        }
      }
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gql(variables):
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": LOGIN or "profile-readme-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch():
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    start = today - datetime.timedelta(days=364)
    variables = {
        "login": LOGIN,
        "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{today.isoformat()}T23:59:59Z",
        "after": None,
    }
    repos = []
    calendar = None
    while True:
        data = gql(variables)["user"]
        if calendar is None:
            calendar = data["contributionsCollection"]["contributionCalendar"]
        page = data["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        variables["after"] = page["pageInfo"]["endCursor"]
    return calendar, repos


def esc(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def font_face(weights):
    rules = []
    for css_weight, filename in weights:
        data = (FONTS / filename).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'JBM';src:url(data:font/woff2;base64,{b64}) "
            f"format('woff2');font-weight:{css_weight};font-style:normal}}"
        )
    return "<style>text{font-family:'JBM',monospace}" + "".join(rules) + "</style>"


def card(width, height, body, weights=((400, "jbm-regular.woff2"),)):
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
        f"{font_face(weights)}"
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" '
        f'fill="{BG}" stroke="{BORDER}"/>'
        f"{body}</svg>"
    )


def plain(width, height, body, weights=((400, "jbm-regular.woff2"),)):
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
        f"{font_face(weights)}{body}</svg>"
    )


def write(name, svg):
    (ROOT / name).write_text(svg, encoding="utf-8")


def heading(name, label):
    width, height = 700, 32
    fs = 13
    letter_spacing = 2
    char_w = fs * 0.6 + letter_spacing
    text = label.lower()
    text_w = len(text) * char_w
    x0 = 0
    rule_x0 = x0 + text_w + 12
    body = (
        f'<text x="{x0}" y="20" font-size="{fs}" letter-spacing="2" fill="{MUTED}">'
        f"{esc(text)}</text>"
        f'<line x1="{rule_x0}" y1="16" x2="{width}" y2="16" stroke="{BORDER}"/>'
    )
    write(name, plain(width, height, body))


def stats_svg(calendar):
    width, height = 700, 170
    total = calendar["totalContributions"]
    weeks = calendar["weeks"]
    week_totals = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    pad = 20
    chart_top, chart_h = 96, 54
    chart_w = width - pad * 2
    n = len(week_totals)
    bar_w = chart_w / n
    peak = max(week_totals) or 1
    bars = []
    for i, v in enumerate(week_totals):
        h = 2 if v == 0 else max(2, round((v / peak) * chart_h))
        x = pad + i * bar_w
        y = chart_top + chart_h - h
        bars.append(
            f'<rect x="{x:.1f}" y="{y}" width="{max(bar_w - 1, 1):.1f}" height="{h}" '
            f'fill="{ACCENT}" opacity="{0.35 + 0.65 * (v / peak):.2f}"/>'
        )
    body = (
        f'<text x="{pad}" y="52" font-size="34" font-weight="700" fill="{TEXT}">{total:,}</text>'
        f'<text x="{pad}" y="72" font-size="12" letter-spacing="1" fill="{MUTED}">'
        f"contributions in the last year</text>"
        f'<text x="{pad}" y="{chart_top - 8}" font-size="11" fill="{MUTED}">by week</text>'
        + "".join(bars)
    )
    write("stats.svg", card(width, height, body, weights=((400, "jbm-regular.woff2"), (700, "jbm-bold.woff2"))))


def flatten_days(calendar):
    days = []
    for w in calendar["weeks"]:
        for d in w["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort(key=lambda d: d[0])
    return days


def compute_streaks(days):
    longest, longest_range = 0, (None, None)
    run, run_start = 0, None
    for date, count in days:
        if count > 0:
            if run == 0:
                run_start = date
            run += 1
            if run > longest:
                longest, longest_range = run, (run_start, date)
        else:
            run = 0
    end_idx = len(days) - 1
    while end_idx >= 0 and days[end_idx][1] == 0:
        end_idx -= 1
    current, current_range = 0, (None, None)
    if end_idx >= 0:
        end_date = days[end_idx][0]
        i = end_idx
        while i >= 0 and days[i][1] > 0:
            current += 1
            i -= 1
        current_range = (days[i + 1][0], end_date)
    return current, current_range, longest, longest_range


def fmt_range(r):
    if r[0] is None:
        return "—"
    a = datetime.date.fromisoformat(r[0]).strftime("%b %-d")
    b = datetime.date.fromisoformat(r[1]).strftime("%b %-d")
    return a if a == b else f"{a} - {b}"


def streak_svg(calendar):
    width, height = 700, 108
    days = flatten_days(calendar)
    current, current_range, longest, longest_range = compute_streaks(days)
    half = width // 2

    def block(x, label, value, rng):
        return (
            f'<text x="{x}" y="42" font-size="30" font-weight="700" fill="{TEXT}">{value}</text>'
            f'<text x="{x}" y="62" font-size="11" letter-spacing="1" fill="{MUTED}">{esc(label)}</text>'
            f'<text x="{x}" y="80" font-size="11" fill="{ACCENT}">{esc(fmt_range(rng))}</text>'
        )

    body = (
        block(20, "current streak (days)", current, current_range)
        + block(half + 20, "longest streak (days)", longest, longest_range)
        + f'<line x1="{half}" y1="16" x2="{half}" y2="{height - 16}" stroke="{BORDER}"/>'
    )
    write("streak.svg", card(width, height, body, weights=((400, "jbm-regular.woff2"), (700, "jbm-bold.woff2"))))


def langs_svg(repos):
    bytes_by_lang = {}
    color_by_lang = {}
    repos_by_lang = {}
    for repo in repos:
        seen = set()
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            color_by_lang[name] = edge["node"]["color"] or MUTED
            bytes_by_lang[name] = bytes_by_lang.get(name, 0) + edge["size"]
            if name not in seen:
                repos_by_lang[name] = repos_by_lang.get(name, 0) + 1
                seen.add(name)

    top_bytes = sorted(bytes_by_lang.items(), key=lambda kv: kv[1], reverse=True)[:6]
    top_repos = sorted(repos_by_lang.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total_bytes = sum(bytes_by_lang.values()) or 1
    max_repos = max((v for _, v in top_repos), default=1)

    width, height = 700, 210
    pad = 20
    col_w = (width - pad * 3) // 2

    def bar_list(x, title, items, value_fmt, scale):
        rows = [f'<text x="{x}" y="18" font-size="11" letter-spacing="1" fill="{MUTED}">{esc(title)}</text>']
        y = 40
        bar_max = col_w - 70
        for name, value in items:
            frac = scale(value)
            w = max(2, round(bar_max * frac))
            color = color_by_lang.get(name, ACCENT)
            rows.append(
                f'<text x="{x}" y="{y}" font-size="11" fill="{TEXT}">{esc(name)[:14]}</text>'
                f'<rect x="{x}" y="{y + 6}" width="{bar_max}" height="4" rx="2" fill="{BORDER}"/>'
                f'<rect x="{x}" y="{y + 6}" width="{w}" height="4" rx="2" fill="{color}"/>'
                f'<text x="{x + bar_max + 8}" y="{y}" font-size="10" fill="{MUTED}">{value_fmt(value)}</text>'
            )
            y += 26
        return "".join(rows)

    body = bar_list(
        pad, "by bytes", top_bytes, lambda v: f"{v / total_bytes * 100:.0f}%", lambda v: v / total_bytes
    ) + bar_list(
        pad * 2 + col_w, "by repo count", top_repos, lambda v: str(v), lambda v: v / max_repos
    )
    write("langs.svg", card(width, height, body))


def year_svg(calendar):
    weeks = calendar["weeks"]
    counts = [[d["contributionCount"] for d in w["contributionDays"]] for w in weeks]
    peak = max((c for week in counts for c in week), default=0) or 1
    rows = [""] * 7
    for week in counts:
        for row in range(7):
            if row < len(week):
                c = week[row]
                if c == 0:
                    idx = 0
                else:
                    idx = 1 + math.floor((len(RAMP) - 2) * math.sqrt(c) / math.sqrt(peak))
                    idx = min(idx, len(RAMP) - 1)
                rows[row] += RAMP[idx]
            else:
                rows[row] += " "

    width = 700
    height = 60 + 7 * 13
    pad = 20
    body = [
        f'<text x="{pad}" y="26" font-size="11" letter-spacing="1" fill="{MUTED}">'
        f"the year, one character per day</text>"
    ]
    for i, row in enumerate(rows):
        y = 48 + i * 13
        body.append(
            f'<text x="{pad}" y="{y}" font-size="12" xml:space="preserve" fill="{ACCENT}">{esc(row)}</text>'
        )
    write("year.svg", card(width, height, "".join(body)))


def main():
    if not LOGIN or not TOKEN:
        print("GH_LOGIN and GITHUB_TOKEN must be set", file=sys.stderr)
        sys.exit(1)
    calendar, repos = fetch()
    for name, label in (
        ("hd-stack.svg", "technology stack"),
        ("hd-connect.svg", "connect"),
        ("hd-activity.svg", "activity"),
        ("hd-year.svg", "this year"),
    ):
        heading(name, label)
    stats_svg(calendar)
    streak_svg(calendar)
    langs_svg(repos)
    year_svg(calendar)


if __name__ == "__main__":
    main()
