"""
PipelineDAG: parses a YAML pipeline definition into an executable DAG.
Validates structure, detects cycles, computes topological order and critical path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False
    logger.warning("networkx not installed; DAG cycle detection will use DFS fallback")


@dataclass
class StepDefinition:
    """One step in a pipeline as parsed from YAML."""
    step_id: str
    transform_type: str
    config: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    quality_rules: list[dict] = field(default_factory=list)
    on_error: str = "fail"   # fail | skip | warn


@dataclass
class PipelineDefinitionParsed:
    """Fully parsed and validated pipeline definition."""
    pipeline_id: str
    version: str
    client_id: str
    description: str
    steps: list[StepDefinition]
    topological_order: list[str]     # step_ids in execution order
    critical_path: list[str]         # longest dependency chain
    lineage_config: Optional[dict] = None  # {"entity_type": "company", "entity_id_column": "cin"}


class PipelineDAGError(Exception):
    pass


class PipelineDAG:
    """
    Build and validate a DAG from a pipeline definition dict (parsed YAML).

    Expected structure:
      pipeline_id: str
      version: str
      client_id: str
      description: str (optional)
      steps:
        - step_id: normalize_cin
          transform_type: normalize_cin
          depends_on: []
          config: {...}
          quality_rules: [...]
          on_error: fail
    """

    def __init__(self, definition: dict[str, Any]) -> None:
        self._raw = definition
        self._parsed: Optional[PipelineDefinitionParsed] = None

    def parse(self) -> PipelineDefinitionParsed:
        if self._parsed is not None:
            return self._parsed

        raw = self._raw
        pipeline_id = raw.get("pipeline_id")
        if not pipeline_id:
            raise PipelineDAGError("'pipeline_id' is required in pipeline definition")

        steps_raw = raw.get("steps", [])
        if not steps_raw:
            raise PipelineDAGError(f"Pipeline {pipeline_id!r} has no steps defined")

        steps: dict[str, StepDefinition] = {}
        for s in steps_raw:
            step_id = s.get("step_id")
            if not step_id:
                raise PipelineDAGError("Each step must have a 'step_id'")
            if step_id in steps:
                raise PipelineDAGError(f"Duplicate step_id: {step_id!r}")
            transform_type = s.get("transform_type")
            if not transform_type:
                raise PipelineDAGError(f"Step {step_id!r} missing 'transform_type'")
            steps[step_id] = StepDefinition(
                step_id=step_id,
                transform_type=transform_type,
                config=s.get("config", {}),
                depends_on=s.get("depends_on", []),
                quality_rules=s.get("quality_rules", []),
                on_error=s.get("on_error", "fail"),
            )

        # Validate dependency references
        for step in steps.values():
            for dep in step.depends_on:
                if dep not in steps:
                    raise PipelineDAGError(
                        f"Step {step.step_id!r} depends on unknown step {dep!r}"
                    )

        # Topological sort + cycle detection
        topo_order = self._topological_sort(steps)
        critical = self._critical_path(steps, topo_order)

        self._parsed = PipelineDefinitionParsed(
            pipeline_id=pipeline_id,
            version=str(raw.get("version", "1.0")),
            client_id=str(raw.get("client_id", "")),
            description=str(raw.get("description", "")),
            steps=[steps[s] for s in topo_order],
            topological_order=topo_order,
            critical_path=critical,
            lineage_config=raw.get("lineage_config"),
        )
        return self._parsed

    def _topological_sort(self, steps: dict[str, StepDefinition]) -> list[str]:
        if _HAS_NX:
            return self._topo_networkx(steps)
        return self._topo_dfs(steps)

    def _topo_networkx(self, steps: dict[str, StepDefinition]) -> list[str]:
        g = nx.DiGraph()
        for step in steps.values():
            g.add_node(step.step_id)
            for dep in step.depends_on:
                g.add_edge(dep, step.step_id)
        if not nx.is_directed_acyclic_graph(g):
            cycle = nx.find_cycle(g)
            raise PipelineDAGError(f"Pipeline contains a dependency cycle: {cycle}")
        return list(nx.topological_sort(g))

    def _topo_dfs(self, steps: dict[str, StepDefinition]) -> list[str]:
        """Kahn's algorithm (BFS-based topological sort + cycle detection)."""
        in_degree = {s: 0 for s in steps}
        for step in steps.values():
            for dep in step.depends_on:
                in_degree[step.step_id] += 1

        queue = [s for s, d in in_degree.items() if d == 0]
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for step in steps.values():
                if node in step.depends_on:
                    in_degree[step.step_id] -= 1
                    if in_degree[step.step_id] == 0:
                        queue.append(step.step_id)

        if len(result) != len(steps):
            raise PipelineDAGError("Pipeline contains a dependency cycle (detected by DFS)")
        return result

    def _critical_path(self, steps: dict[str, StepDefinition], topo_order: list[str]) -> list[str]:
        """Longest path by step count (proxy for execution time)."""
        dist: dict[str, int] = {s: 0 for s in steps}
        pred: dict[str, Optional[str]] = {s: None for s in steps}

        for step_id in topo_order:
            step = steps[step_id]
            for dep in step.depends_on:
                if dist[dep] + 1 > dist[step_id]:
                    dist[step_id] = dist[dep] + 1
                    pred[step_id] = dep

        # Trace back from the node with max distance
        end = max(dist, key=lambda s: dist[s])
        path: list[str] = []
        node: Optional[str] = end
        while node is not None:
            path.append(node)
            node = pred[node]
        return list(reversed(path))

    @classmethod
    def validate_definition(cls, definition: dict[str, Any]) -> list[str]:
        """Return validation errors without raising. Used at build/deploy time."""
        errors: list[str] = []
        try:
            dag = cls(definition)
            dag.parse()
        except PipelineDAGError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"Unexpected validation error: {exc}")
        return errors
