"""File dependency graph helpers for analyze (cycle detection)."""

from __future__ import annotations

from collections import defaultdict

from ..symbols import cycle_runtime_edge_sql
from .common import fetch_all

FILE_EDGES_SQL = f"""
    SELECT DISTINCT d1.relative_path AS from_file, d2.relative_path AS to_file
    FROM mentions m
    JOIN chunks c ON m.chunk_id = c.id
    JOIN documents d1 ON c.document_id = d1.id
    JOIN defn_enclosing_ranges der ON m.symbol_id = der.symbol_id
    JOIN documents d2 ON der.document_id = d2.id
    JOIN global_symbols gs ON gs.id = der.symbol_id
    WHERE d1.id != d2.id AND m.role != 1
      AND {cycle_runtime_edge_sql()}
"""


def fetch_file_edges(db) -> list[tuple[str, str]]:
    return fetch_all(db, FILE_EDGES_SQL)


def _tarjan_sccs(graph: dict[str, list[str]], nodes: set[str]) -> list[list[str]]:
    """Iterative Tarjan's SCC — avoids RecursionError on large graphs."""
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    for root in nodes:
        if root in indices:
            continue
        call_stack: list[tuple[str, int]] = [(root, 0)]
        while call_stack:
            vertex, ni = call_stack.pop()
            neighbors = graph.get(vertex, ())
            if ni == 0:
                indices[vertex] = index
                lowlink[vertex] = index
                index += 1
                stack.append(vertex)
                on_stack.add(vertex)
            else:
                neighbor = neighbors[ni - 1]
                lowlink[vertex] = min(lowlink[vertex], lowlink[neighbor])
            while ni < len(neighbors):
                neighbor = neighbors[ni]
                ni += 1
                if neighbor not in indices:
                    call_stack.append((vertex, ni))
                    call_stack.append((neighbor, 0))
                    break
                if neighbor in on_stack:
                    lowlink[vertex] = min(lowlink[vertex], indices[neighbor])
            else:
                if lowlink[vertex] == indices[vertex]:
                    component: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        component.append(w)
                        if w == vertex:
                            break
                    sccs.append(component)
    return sccs


def _cycles_in_scc(
    graph: dict[str, list[str]],
    scc_nodes: list[str],
    *,
    max_depth: int,
    limit: int,
) -> list[str]:
    if len(scc_nodes) <= 2:
        return []

    scc = set(scc_nodes)
    subgraph: dict[str, list[str]] = defaultdict(list)
    for src in scc:
        for dst in graph.get(src, ()):
            if dst in scc:
                subgraph[src].append(dst)

    found: dict[tuple[str, ...], str] = {}

    def record(path: list[str]) -> None:
        key = min(tuple(path[i:] + path[:i]) for i in range(len(path)))
        if key not in found:
            found[key] = " -> ".join([*path, path[0]])

    for origin in sorted(scc):
        stack: list[tuple[str, list[str]]] = [(origin, [origin])]
        while stack:
            node, path = stack.pop()
            if len(path) > max_depth:
                continue
            for nxt in subgraph.get(node, ()):
                if nxt == origin and len(path) >= 2:
                    record(path)
                    if len(found) >= limit:
                        return sorted(found.values())[:limit]
                elif nxt not in path:
                    stack.append((nxt, [*path, nxt]))
    return sorted(found.values())


def find_longer_cycles(
    edges: list[tuple[str, str]],
    *,
    max_depth: int = 8,
    limit: int,
) -> list[str]:
    """Find directed cycles with 3+ distinct files (2-node pairs use the SQL two-way check)."""
    if limit <= 0 or not edges:
        return []

    graph: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for src, dst in edges:
        graph[src].append(dst)
        nodes.add(src)
        nodes.add(dst)

    found: dict[tuple[str, ...], str] = {}
    for component in _tarjan_sccs(graph, nodes):
        if len(component) <= 2:
            continue
        for line in _cycles_in_scc(graph, component, max_depth=max_depth, limit=limit):
            path = line.split(" -> ")
            body = path[:-1]
            key = min(tuple(body[i:] + body[:i]) for i in range(len(body)))
            if key not in found:
                found[key] = line
            if len(found) >= limit:
                return sorted(found.values())[:limit]
    return sorted(found.values())[:limit]
