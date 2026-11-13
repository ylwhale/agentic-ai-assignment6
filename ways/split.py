"""Assignment 6 experimental arm M: two tool-restricted workers per issue.

All model/tool calls belong to ctx.agent() traces. The coordinator is code, not
an extra model call. Every issue's read -> write pipeline is independent; batch
pipelines run concurrently. Each worker is bounded under one shared run ceiling.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from agent.loop import load_bounds, run_loop
from harness.formats import LABELS
from harness.roles import arg, role_of, tool_for
from harness.schema import errors as schema_errors
from harness.tasks import end_state
from split.guards import check_combined
from tools import ToolResult
from ways.agent import disclosure_line, with_disclosure


class RoleTools:
    """Refuses any tool outside its role's allowed registry names.

    The investigator is also offered one local return tool; no registry call is
    made for that tool. Other calls all use ctx.tools, including the policy hook.
    """

    RETURN_NAME = "return_findings"

    def __init__(self, registry, roles, *, schema=None, disclosure="", issue=None, trace=None):
        self.registry = registry
        self.roles = frozenset(roles)
        self.allowed = {tool_for(r) for r in roles}
        self.schema = schema
        self.disclosure = disclosure
        self.issue = issue
        self.trace = trace
        self.calls = []
        self.returned = []
        self._schemas = [s for s in registry.schemas if s["name"] in self.allowed]
        if schema is not None:
            self._schemas.append({
                "name": self.RETURN_NAME,
                "description": "Return the investigator's structured finding once; do not write to the tracker.",
                "input_schema": schema,
            })

    @property
    def schemas(self):
        return self._schemas

    def call(self, name, inputs):
        if name == self.RETURN_NAME and self.schema is not None:
            # Reject inaccurate returns at the tool boundary. Do not silently
            # rewrite the model's claimed fields: require a corrected return.
            actual_searched, actual_count = observed_facts(self.calls)
            problems = schema_errors(inputs, self.schema)
            if not problems:
                if inputs["searched"] != actual_searched:
                    problems.append("searched differs from the actual search queries and read-file paths")
                if inputs["calls_used"] != actual_count:
                    problems.append("calls_used differs from the actual registry tool-call count")
                if self.issue is not None and inputs["result"]["issue"] != self.issue:
                    problems.append("result.issue differs from the assigned issue")
            if problems:
                if self.trace is not None:
                    self.trace.event("return_rejected", errors=problems,
                                     actual_searched=actual_searched,
                                     actual_calls_used=actual_count)
                correction = (
                    "Invalid return_findings; no result has been accepted. "
                    + "; ".join(problems)
                    + ". Retry return_findings using exactly these observed values: "
                    + "searched=" + json.dumps(actual_searched)
                    + ", calls_used=" + str(actual_count)
                    + ". Do not include the issue ID in searched unless it was literally "
                      "a search query or read-file path. Do not make further registry calls."
                )
                return ToolResult(correction, True, 0.0)
            self.returned.append(inputs)
            return ToolResult("Return accepted. Do not call any more tools.", False, 0.0)
        if name not in self.allowed:
            return ToolResult("Forbidden: this worker has no permission to use that tool.", True, 0.0)
        arguments = dict(inputs) if isinstance(inputs, dict) else inputs
        if role_of(name) == "comment" and isinstance(arguments, dict):
            body_arg = arg("comment", "body")
            if body_arg in arguments:
                arguments = {**arguments, body_arg: with_disclosure(arguments[body_arg], self.disclosure)}
        self.calls.append((name, arguments))
        return self.registry.call(name, arguments)


def observed_facts(calls):
    """What the worker actually searched/read; never trust self-reported metrics."""
    searched = []
    for name, args in calls:
        role = role_of(name)
        key = arg("search", "query") if role == "search" else arg("read_file", "path") if role == "read_file" else None
        if key and isinstance(args, dict) and isinstance(args.get(key), str):
            item = args[key]
            if item not in searched:
                searched.append(item)
    return searched, len(calls)


def _one(ctx, coordinator, issue, per_issue, schema, line):
    investigator = ctx.agent(f"investigator-{issue}", parent=coordinator.id)
    writer = ctx.agent(f"writer-{issue}", parent=coordinator.id)
    investigator_tools = RoleTools(ctx.tools, ("read_issue", "search", "read_file"),
                                   schema=schema, issue=issue, trace=investigator.trace)

    base = load_bounds()
    share_investigate = max(1, int(per_issue * 0.64))
    share_write = max(1, int(per_issue * 0.31))
    coordinator.trace.event("wait", waiter=coordinator.id, on=investigator.id,
                            what=f"validated investigation for issue {issue}", turn=0)
    run_loop(investigator.client, investigator_tools, ctx.prompt("investigator.md"),
             f"Investigate issue #{issue}. Return one structured finding using return_findings.",
             replace(base, max_steps=9, max_tokens=share_investigate), investigator.trace)

    raw = investigator_tools.returned[-1] if investigator_tools.returned else {}
    problems = schema_errors(raw, schema)
    actual_searched, actual_count = observed_facts(investigator_tools.calls)
    if not problems:
        if raw["searched"] != actual_searched:
            problems.append("searched does not match actual search and read calls")
        if raw["calls_used"] != actual_count:
            problems.append("calls_used does not match actual tool calls")
        if raw["result"]["issue"] != issue:
            problems.append("result.issue differs from assigned issue")
    coordinator.trace.event("worker_return", worker=investigator.id,
                            contract=raw, valid=not problems, errors=problems)
    if problems:
        coordinator.trace.event("worker_stopped", worker=investigator.id,
                                reason="invalid return: " + "; ".join(problems[:3]))
        return

    result = raw["result"]
    if raw["status"] == "out_of_budget" or result["label"] not in LABELS or not result["file"]:
        coordinator.trace.event("worker_stopped", worker=writer.id,
                                reason="no actionable validated finding")
        return

    writer_tools = RoleTools(ctx.tools, ("apply_label", "open_pr", "comment"), disclosure=line)
    brief = (f"Triage issue #{issue} using the validated investigation.\n"
             f"label: {result['label']}\nfile: {result['file']}\n"
             f"evidence: {result['evidence']}\n"
             "Apply the label, open one draft PR only when file is not none, "
             "then post exactly one triage comment.")
    coordinator.trace.event("wait", waiter=coordinator.id, on=writer.id,
                            what=f"tracker writes for issue {issue}", turn=0)
    run_loop(writer.client, writer_tools, ctx.prompt("writer.md"), brief,
             replace(base, max_steps=7, max_tokens=share_write), writer.trace)


def run(ctx):
    """The way invoked by `python run.py --way split`."""
    coordinator = ctx.agent("coordinator")
    schema = json.loads((Path(__file__).resolve().parent.parent / "split" / "contract.schema.json").read_text())
    line = disclosure_line()
    per_issue = max(1, int((ctx.budget or load_bounds().max_tokens * len(ctx.issues)) / len(ctx.issues)))
    # Five unrelated issues really can run concurrently. Keep a single run ceiling.
    with ThreadPoolExecutor(max_workers=min(5, len(ctx.issues))) as pool:
        futures = [pool.submit(_one, ctx, coordinator, issue, per_issue, schema, line) for issue in ctx.issues]
        for future in futures:
            future.result()  # let quota and rate-limit failures reach the runner
    violations = check_combined(ctx.task, end_state(ctx.tracker, ctx.run_id, ctx.task))
    coordinator.trace.event("combined_check", passed=not violations, violations=violations)
    coordinator.trace.end("completed", detail="coordinator finished independent issue pipelines")
