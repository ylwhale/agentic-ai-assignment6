"""Assignment 6 guards: deadlock, versioned writes and combined verification.

Each guard is deterministic. The checker replays recorded failures through the
public interfaces defined in checks/FORMATS.md, section 14.6.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from harness.formats import LABELS, parse_triage_comment


class WaitGraph:
    """Directed wait-for graph: an edge A -> B means A is waiting for B."""

    def __init__(self):
        self.edges: dict[str, set[str]] = {}

    def wait(self, waiter: str, on: str, what: str = "") -> list[str] | None:
        self.edges.setdefault(waiter, set()).add(on)
        self.edges.setdefault(on, set())
        # A new cycle exists iff the new target can already reach the waiter.
        path = self._path(on, waiter, set())
        return [waiter, *path] if path else None

    def _path(self, start: str, target: str, visited: set[str]) -> list[str] | None:
        if start == target:
            return [start]
        if start in visited:
            return None
        visited.add(start)
        for next_agent in sorted(self.edges.get(start, ())):
            found = self._path(next_agent, target, visited)
            if found is not None:
                return [start, *found]
        return None

    def victim(self, cycle: list[str]) -> str:
        # The coordinator is never a deadlock victim.
        workers = [agent for agent in cycle if agent != "coordinator"]
        if not workers:
            raise ValueError("cycle contains no worker that may be stopped")
        return sorted(set(workers))[0]


class SharedState:
    """In-memory file contents protected by optimistic version checks."""

    def __init__(self, initial: dict[str, str]):
        self._contents = dict(initial)
        self._versions = {path: 0 for path in self._contents}
        self._reads: dict[tuple[str, str], int] = {}

    def read(self, agent: str, path: str) -> tuple[str, int]:
        version = self._versions[path]
        self._reads[(agent, path)] = version
        return self._contents[path], version

    def write(self, agent: str, path: str, content: str, version: int) -> bool:
        if path not in self._contents:
            return False
        if self._reads.get((agent, path)) != version:
            return False
        if self._versions[path] != version:
            return False
        self._contents[path] = content
        self._versions[path] += 1
        return True

    def content(self, path: str) -> str:
        return self._contents[path]


def check_combined(task, state: dict) -> list[str]:
    """Validate consistency of the observed tracker state, without answer keys."""
    violations: list[str] = []
    for issue in task.issues:
        item = state.get(issue, state.get(str(issue), {}))
        comments = item.get("comments", [])
        labels = item.get("labels", [])
        prs = item.get("prs", [])

        if len(comments) != 1:
            violations.append(f"issue {issue}: expected one comment, got {len(comments)}")
            continue

        label, file = parse_triage_comment(comments[0])
        if label not in LABELS or not file:
            violations.append(f"issue {issue}: comment lacks a valid label or file")
            continue

        if sorted(set(labels)) != [label] or len(labels) != 1:
            violations.append(f"issue {issue}: tracker labels do not match comment label {label}")

        if file == "none":
            if prs:
                violations.append(f"issue {issue}: file is none but a PR exists")
        else:
            if len(prs) != 1:
                violations.append(f"issue {issue}: file {file} requires exactly one PR")
            else:
                pr = prs[0]
                text = f"{pr.get('title', '')}\n{pr.get('body', '')}".lower()
                basename = PurePosixPath(file).name.lower()
                if file.lower() not in text and basename not in text:
                    violations.append(f"issue {issue}: PR does not name {file}")
    return violations
