"""Build reports/agile_metrics.csv from real Git/GitHub history.

Every number is counted from `git log` and the GitHub API (`gh`), never
estimated. The repo has no sprint board, so story points / committed vs
completed stories do not exist; commits, PRs and issues are the measurable
proxies used in Chapter 7.

Usage (from the repo root, after `git fetch`):
    python reports/src/agile_metrics.py reports/agile_metrics.csv

Sprints are two weeks long; sprint 1 starts on 2026-06-01 (same boundaries
as docs/sprint-logs/sprint-1..4.md). Dates are Vietnam local time (UTC+7).
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
FIRST_SPRINT_START = date(2026, 6, 1)
SPRINT_DAYS = 14


def _run(args: list[str]) -> str:
    """Run a CLI command and return its stdout (raises on failure)."""
    return subprocess.run(
        args, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _vn_date(iso: str | None) -> date | None:
    """Convert an ISO-8601 timestamp to a Vietnam calendar date."""
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(VN_TZ).date()


def _load_history() -> tuple[list[tuple[date, str]], list[dict], list[dict]]:
    """Return (commits as (date, author)), PRs and issues from Git/GitHub."""
    log = _run(["git", "log", "--remotes", "--no-merges", "--format=%H %cI %an"])
    unique = {line.split(" ", 2)[0]: line.split(" ", 2) for line in log.splitlines()}
    commits = [(_vn_date(ts), author) for _sha, ts, author in unique.values()]
    prs = json.loads(
        _run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--limit",
                "500",
                "--json",
                "number,createdAt,mergedAt,closedAt,state",
            ]
        )
    )
    issues = json.loads(
        _run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "all",
                "--limit",
                "500",
                "--json",
                "number,closedAt",
            ]
        )
    )
    return commits, prs, issues


def build_rows(today: date) -> list[dict]:
    """Count activity per sprint, from sprint 1 up to the current sprint."""
    commits, prs, issues = _load_history()
    rows: list[dict] = []
    number = 1
    while True:
        start = FIRST_SPRINT_START + timedelta(days=SPRINT_DAYS * (number - 1))
        end = start + timedelta(days=SPRINT_DAYS - 1)
        if start > today:
            break

        def within(day: date | None, s: date = start, e: date = end) -> bool:
            return day is not None and s <= day <= e

        sprint_commits = [c for c in commits if within(c[0])]
        rows.append(
            {
                "sprint": number,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": "in_progress" if start <= today <= end else "done",
                "commits": len(sprint_commits),
                "authors": len({author for _day, author in sprint_commits}),
                "prs_opened": sum(within(_vn_date(p["createdAt"])) for p in prs),
                "prs_merged": sum(within(_vn_date(p["mergedAt"])) for p in prs),
                "prs_closed_unmerged": sum(
                    p["state"] == "CLOSED" and within(_vn_date(p["closedAt"]))
                    for p in prs
                ),
                "issues_closed": sum(within(_vn_date(i["closedAt"])) for i in issues),
            }
        )
        number += 1
    return rows


def main() -> None:
    """Write the per-sprint metrics CSV to the path given on the command line."""
    out_path = sys.argv[1] if len(sys.argv) > 1 else "reports/agile_metrics.csv"
    rows = build_rows(datetime.now(VN_TZ).date())
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
