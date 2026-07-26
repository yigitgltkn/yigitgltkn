"""Update the dynamic panel inside the GitHub profile README.

Only the block between the PANEL:START / PANEL:END markers is replaced;
the rest of the file (intro, tech badges, contact) is never touched.

No third-party packages: standard library only. Runs locally without a
token as well (public API, 60 requests/hour).
"""

import json
import os
import sys
import time
import urllib.request
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
# Provided by Actions from the repository owner; falls back to a constant locally
USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER") or "yigitgltkn"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

README_PATH = "README.md"
START = "<!-- PANEL:START -->"
END = "<!-- PANEL:END -->"

ACTIVITY_LIMIT = 6      # max rows in the activity table
PROJECT_LIMIT = 4       # repos listed under "Active Projects"
LANGUAGE_LIMIT = 5      # bars in the language chart
WINDOW_DAYS = 30        # "last X days" metrics
BAR_WIDTH = 22          # width of the language bars

# Only repos pushed within this window count towards the language chart.
# Otherwise the 2023 Unity projects render the chart as 57% C# and hide
# the current focus (Python / TypeScript).
LANGUAGE_WINDOW_MONTHS = 24

# The repo that generates this panel: keep it out of the stats and tables
PROFILE_REPO = f"{USERNAME}/{USERNAME}"


# --------------------------------------------------------------------------
# GitHub API
# --------------------------------------------------------------------------

def _single_request(url):
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", f"{USERNAME}-profile-panel")
    if GITHUB_TOKEN:
        request.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api(path, required=True, attempts=3):
    """Fetch JSON from the API. Exits if a required request keeps failing.

    Key detail: the README is written only after all data has been
    collected, so an API failure leaves the file exactly as it was.
    """
    url = path if path.startswith("http") else f"{API}{path}"
    last_error = None
    for attempt in range(attempts):
        try:
            return _single_request(url)
        except Exception as error:  # urllib.error.*, socket timeout, bad JSON
            last_error = error
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))

    if required:
        print(f"[ERROR] could not fetch {url}: {last_error}", file=sys.stderr)
        print("README left untouched.", file=sys.stderr)
        sys.exit(1)
    print(f"[WARN] skipped {url}: {last_error}", file=sys.stderr)
    return None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def parse_time(stamp):
    """'2026-07-25T11:58:07Z' -> timezone-aware datetime."""
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def cell(text, length=72):
    """Table-safe text: collapse whitespace, escape pipes, truncate."""
    if not text:
        return "—"
    text = " ".join(text.split()).replace("|", "\\|")
    if len(text) > length:
        text = text[: length - 1].rstrip() + "…"
    return text


def bar(ratio):
    """Turn a 0.0-1.0 ratio into a block bar.

    Fill only, no empty track: the shaded track character renders as a
    noisy hatch pattern in GitHub's body font. Anything above zero gets
    at least one block so small shares stay visible.
    """
    return "█" * max(1, round(ratio * BAR_WIDTH))


def commits_label(count):
    return "1 commit" if count == 1 else f"{count} commits"


# --------------------------------------------------------------------------
# Data collection
# --------------------------------------------------------------------------

def collect_data():
    user = api(f"/users/{USERNAME}")
    repos = api(f"/users/{USERNAME}/repos?per_page=100&sort=pushed") or []
    events = api(f"/users/{USERNAME}/events/public?per_page=100") or []

    # Forks, archived repos and this panel's own repo are excluded: the first
    # two are not my own output, the third is the infrastructure itself.
    own_repos = [
        r for r in repos
        if not r.get("fork")
        and not r.get("archived")
        and r["full_name"] != PROFILE_REPO
    ]

    return user, own_repos, events


def language_mix(repos):
    """Language mix with every repo weighted equally by its internal shares.

    Only repos pushed within LANGUAGE_WINDOW_MONTHS count, so the chart
    answers "what am I writing lately" rather than "what do I know".

    Raw byte totals are misleading: a single static site repo turns the
    whole chart into 50% HTML and hides six Python projects. So each repo
    is normalized to 1.0 first, making the result the average language
    mix across repos.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=LANGUAGE_WINDOW_MONTHS * 30)
    totals = Counter()

    for repo in repos:
        pushed = repo.get("pushed_at")  # can be None on empty repos
        if not pushed or parse_time(pushed) < cutoff:
            continue
        languages = api(repo["languages_url"], required=False)
        if not languages:
            continue
        repo_total = sum(languages.values())
        if not repo_total:
            continue
        for language, size in languages.items():
            totals[language] += size / repo_total

    return totals


def window_metrics(events):
    """Commit count and number of repos touched in the last WINDOW_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    commits = 0
    active_repos = set()

    for event in events:
        if event["repo"]["name"] == PROFILE_REPO:
            continue
        if parse_time(event["created_at"]) < cutoff:
            continue
        active_repos.add(event["repo"]["name"])
        if event["type"] == "PushEvent":
            commits += event["payload"].get("size") or 1

    return commits, len(active_repos)


def activity_rows(events):
    """Group events by (repo, day, kind).

    This was the bug in the old version: two pushes on the same day
    produced two separate "1 Commit" rows. They are now merged.
    """
    groups = OrderedDict()  # events arrive newest-first, so order is preserved

    for event in events:
        repo = event["repo"]["name"]
        if repo == PROFILE_REPO:  # keep the bot's own commits out of the table
            continue

        date = event["created_at"][:10]
        kind = event["type"]
        payload = event.get("payload") or {}

        if kind == "PushEvent":
            key = (repo, date, "push")
            entry = groups.setdefault(key, {"count": 0})
            entry["count"] += payload.get("size") or 1

        elif kind == "PullRequestEvent":
            action = payload.get("action")
            merged = (payload.get("pull_request") or {}).get("merged")
            if action == "closed" and merged:
                label = "Pull request merged"
            elif action == "closed":
                label = "Pull request closed"
            elif action == "reopened":
                label = "Pull request reopened"
            elif action == "opened":
                label = "Pull request opened"
            else:
                continue
            groups.setdefault((repo, date, label), {"count": 0})["count"] += 1

        elif kind == "CreateEvent" and payload.get("ref_type") == "repository":
            groups.setdefault((repo, date, "Repository created"), {"count": 1})

        elif kind == "ReleaseEvent" and payload.get("action") == "published":
            tag = (payload.get("release") or {}).get("tag_name") or ""
            label = f"Release published {tag}".strip()
            groups.setdefault((repo, date, label), {"count": 1})

        if len(groups) >= ACTIVITY_LIMIT * 3:
            break  # no need to collect far beyond the limit

    rows = []
    for (repo, date, kind), entry in list(groups.items())[:ACTIVITY_LIMIT]:
        if kind == "push":
            activity = f"`{commits_label(entry['count'])}`"
        else:
            activity = kind if entry["count"] < 2 else f"{kind} ×{entry['count']}"
        rows.append((repo, activity, date))
    return rows


# --------------------------------------------------------------------------
# Panel rendering
# --------------------------------------------------------------------------

def card(value, label):
    return f'<td align="center" width="120"><b>{value}</b><br /><sub>{label}</sub></td>'


def build_panel(user, repos, events, languages):
    commits_30, active_30 = window_metrics(events)
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    parts = []

    # --- Stat cards -----------------------------------------------------
    cards = [
        card(user.get("public_repos", len(repos)), "Public repos"),
        card(stars, "Stars"),
        card(user.get("followers", 0), "Followers"),
        card(commits_30, f"Commits / {WINDOW_DAYS}d"),
        card(active_30, f"Active projects / {WINDOW_DAYS}d"),
    ]
    parts.append("#### Overview\n")
    parts.append(
        '<table>\n  <tr>\n    ' + "\n    ".join(cards) + "\n  </tr>\n</table>\n"
    )

    # --- Language chart -------------------------------------------------
    # Rendered as a table rather than a fenced code block: a code block
    # ships GitHub's grey chrome and a copy button, which reads as a
    # snippet to copy instead of a panel widget. Fixed column widths keep
    # the bars on a common baseline.
    if languages:
        total = sum(languages.values())
        rows = []
        for name, size in languages.most_common(LANGUAGE_LIMIT):
            share = size / total
            rows.append(
                "  <tr>\n"
                f'    <td width="120"><b>{name}</b></td>\n'
                f'    <td width="230">{bar(share)}</td>\n'
                f'    <td width="70" align="right">{share * 100:.1f}%</td>\n'
                "  </tr>"
            )
        parts.append("#### Language Mix\n")
        parts.append(
            f"<sub>repos pushed in the last {LANGUAGE_WINDOW_MONTHS} months · "
            f"normalized per repo</sub>\n"
        )
        parts.append("<table>\n" + "\n".join(rows) + "\n</table>\n")

    # --- Recent activity ------------------------------------------------
    parts.append("#### Recent Activity\n")
    table = ["| Project | Activity | Date |", "|:--|:--|--:|"]
    rows = activity_rows(events)
    if rows:
        for repo, activity, date in rows:
            name = repo.split("/", 1)[-1]
            table.append(f"| [{name}](https://github.com/{repo}) | {activity} | {date} |")
    else:
        table.append("| — | No public activity in the last 90 days | — |")
    parts.append("\n".join(table) + "\n")

    # --- Active projects ------------------------------------------------
    projects = repos[:PROJECT_LIMIT]  # API returned sort=pushed: newest first
    if projects:
        parts.append("#### Active Projects\n")
        table = ["| Project | Description | Language | ★ |", "|:--|:--|:--|--:|"]
        for repo in projects:
            table.append(
                f"| [{cell(repo['name'], 28)}]({repo['html_url']}) "
                f"| {cell(repo.get('description'), 70)} "
                f"| {repo.get('language') or '—'} "
                f"| {repo.get('stargazers_count', 0)} |"
            )
        parts.append("\n".join(table) + "\n")

    # --- Footer ---------------------------------------------------------
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    parts.append(
        f"<sub>Generated automatically by GitHub Actions · "
        f"last updated {now} UTC</sub>"
    )

    return "\n".join(parts)


# --------------------------------------------------------------------------
# Writing the README
# --------------------------------------------------------------------------

def update_readme(panel):
    with open(README_PATH, "r", encoding="utf-8") as file:
        content = file.read()

    block = f"{START}\n\n{panel}\n\n{END}"

    head = content.find(START)
    tail = content.find(END)
    if head != -1 and tail > head:
        # Only the span between the markers changes. Plain slicing on purpose:
        # with re.sub, sequences like \g inside the panel would be read as
        # escape references.
        updated = content[:head] + block + content[tail + len(END):]
    else:
        print("[WARN] markers not found, panel appended at end of file.",
              file=sys.stderr)
        updated = content.rstrip() + "\n\n" + block + "\n"

    if updated == content:
        print("No changes.")
        return

    with open(README_PATH, "w", encoding="utf-8", newline="\n") as file:
        file.write(updated)
    print(f"README updated ({len(updated)} characters).")


def main():
    user, repos, events = collect_data()
    languages = language_mix(repos)
    update_readme(build_panel(user, repos, events, languages))


if __name__ == "__main__":
    main()
