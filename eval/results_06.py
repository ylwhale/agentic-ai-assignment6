#!/usr/bin/env python3
"""Write grounded Assignment 6 run results from the tracker and run_end traces.

    python eval/results_06.py
    python eval/results_06.py --update-report   # only after all 72 runs finish

The results file contains every finished real-model run on fixtures/tasks6.
Scripted runs, development issues, incomplete runs, and agents' claims are not
counted. No way reads the known answers: ONLY this evaluator calls check_task.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_task import check_task
from harness import LAB
from harness.formats import ARMS, UNFINISHED
from harness.runner import is_free, is_trace
from harness.tasks import load_tasks
from harness.trace import read_trace


class TrackerView:
    """Read-only view across the active tracker and archived tracker databases."""

    def __init__(self):
        self.rows: dict[str, dict[str, list[dict]]] = {t: defaultdict(list)
                                                      for t in ("comments", "labels", "prs")}
        dbs = [ROOT / "tracker" / "tracker.db",
               *sorted((ROOT / "tracker" / "archive").glob("*.db"))]
        for path in dbs:
            if not path.exists():
                continue
            with sqlite3.connect(path) as db:
                db.row_factory = sqlite3.Row
                for table in self.rows:
                    try:
                        for row in db.execute(f"SELECT * FROM {table} ORDER BY id"):
                            item = dict(row)
                            self.rows[table][str(item["run_id"])].append(item)
                    except sqlite3.OperationalError:
                        pass

    def comments(self, run_id, issue=None):
        return [row for row in self.rows["comments"].get(run_id, [])
                if issue is None or int(row["issue"]) == int(issue)]

    def labels(self, run_id, issue=None, active=True):
        return [row for row in self.rows["labels"].get(run_id, [])
                if (issue is None or int(row["issue"]) == int(issue))
                and (not active or row.get("removed_at") is None)]

    def prs(self, run_id, branch=None, state="open"):
        return [row for row in self.rows["prs"].get(run_id, [])
                if (branch is None or row["branch"] == branch)
                and (state is None or row.get("state") == state)]


def collect() -> tuple[list[dict], list[dict]]:
    tasks = {task.id: task for task in load_tasks(ROOT / "fixtures" / "tasks6")}
    tracker = TrackerView()
    rows, headers = [], []
    for path in sorted((ROOT / "runs").glob("*.jsonl")):
        if not is_trace(path):
            continue
        records = read_trace(path)
        if not records or records[0].get("type") != "run_start":
            continue
        start = records[0]
        if start.get("lab") != LAB or start.get("task") not in tasks:
            continue
        if start.get("way") not in ARMS or is_free(start.get("backend") or ""):
            continue
        if records[-1].get("type") != "run_end":
            continue
        if {r.get("terminal_reason") for r in records if r.get("type") == "end"} & set(UNFINISHED):
            continue
        run_id = start["run_id"]
        outcome = check_task(run_id, tasks[start["task"]], tracker=tracker)
        end = records[-1]
        rows.append({"run_id": run_id, "arm": ARMS[start["way"]], "way": start["way"],
                     "task": start["task"], "kind": start["kind"],
                     "sweep": int(start["sweep"]), "passed": bool(outcome["passed"]),
                     "parts": {str(issue): bool(ok) for issue, ok in outcome["parts"].items()},
                     "tokens": int(end["totals"]["total_tokens"]),
                     "wall_s": float(end["elapsed_s"])})
        headers.append(start)
    rows.sort(key=lambda r: (r["arm"], r["task"], r["sweep"], r["run_id"]))
    return rows, headers


def save_rows(rows: list[dict]) -> Path:
    target = ROOT / "results" / "runs_06.jsonl"
    target.parent.mkdir(exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    temp.replace(target)
    return target


def summarize(rows: list[dict], kind: str) -> dict:
    mine = [r for r in rows if r["kind"] == kind]
    per_task: dict[str, int] = {}
    by_sweep: dict[int, int] = {}
    for row in mine:
        per_task[row["task"]] = per_task.get(row["task"], 0) + int(row["passed"])
        by_sweep[row["sweep"]] = by_sweep.get(row["sweep"], 0) + int(row["passed"])
    return {"runs": len(mine), "passes": sum(int(r["passed"]) for r in mine),
            "per_task": per_task, "sweep_min": min(by_sweep.values(), default=0),
            "sweep_max": max(by_sweep.values(), default=0),
            "all_three": sum(1 for value in per_task.values() if value >= 3),
            "mean_tokens": round(mean(r["tokens"] for r in mine)) if mine else 0,
            "mean_wall_s": round(mean(r["wall_s"] for r in mine), 1) if mine else 0.0}


def update_report(rows: list[dict], headers: list[dict]) -> None:
    expected = 3 * len(load_tasks(ROOT / "fixtures" / "tasks6"))
    arms = ("S", "M", "S_plus")
    counts = {arm: sum(r["arm"] == arm for r in rows) for arm in arms}
    if any(n != expected for n in counts.values()):
        raise SystemExit(f"Cannot update report yet: need {expected} runs per arm, have {counts}")
    constants = [h.get("constants") for h in headers]
    if not constants or any(c != constants[0] for c in constants):
        raise SystemExit("The five constants differ between runs; investigate before updating the report")

    path = ROOT / "reports" / "LAB_06.json"
    report = json.loads(path.read_text())
    report["constants"] = constants[0]
    report["arms"] = {arm: {kind: summarize([r for r in rows if r["arm"] == arm], kind)
                            for kind in ("single", "batch")} for arm in arms}
    report["multiplier"] = {}
    for kind in ("single", "batch"):
        s = report["arms"]["S"][kind]
        m = report["arms"]["M"][kind]
        sp = report["arms"]["S_plus"][kind]
        report["multiplier"][kind] = round(m["mean_tokens"] / s["mean_tokens"], 3) if s["mean_tokens"] else None
        report["spend_check"][kind] = {
            "spent_more": "yes" if m["mean_tokens"] > s["mean_tokens"] else "no",
            "spend_raises_score": "yes" if sp["passes"] > s["passes"] else "no",
            "one_agent_as_well": "yes" if sp["passes"] >= m["passes"] else "no",
        }
    # Failure categories and topology decisions are interpretive. Do not invent them.
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Updated {path.relative_to(ROOT)} with grounded counts and spend checks.")
    print("Still required: classify every failed M run and write the Part C/D decision.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-report", action="store_true", help="fill measured report fields only when complete")
    opts = parser.parse_args()
    rows, headers = collect()
    target = save_rows(rows)
    print(f"Wrote {len(rows)} finished real-model task-set runs to {target.relative_to(ROOT)}")
    for arm in ("S", "M", "S_plus"):
        own = [r for r in rows if r["arm"] == arm]
        print(f"  {arm}: {len(own)} runs, {sum(r['passed'] for r in own)} passes")
    if opts.update_report:
        update_report(rows, headers)


if __name__ == "__main__":
    main()
