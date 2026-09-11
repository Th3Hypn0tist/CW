from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools.Topology.lib.graph import (
    Edge,
    Node,
    ProgressCallback,
    collect_graph,
    collect_structure_tree,
    load_documents,
)
from tools.Topology.lib.projection import ProjectionResult
from tools.Topology.projections import PROJECTIONS


OpenProgressCallback = Callable[[int, str], None]


@dataclass
class ProjectionState:
    source: Path | None = None
    topology: str = "containment"
    projection: str = "hierarchy"


class TopologyProjector:
    """Host-neutral CW topology projection service."""

    def __init__(self, source: Path | None = None) -> None:
        self.state = ProjectionState(source=source.expanduser().resolve() if source else None)
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.structure_nodes: dict[str, Node] = {}
        self.structure_edges: list[Edge] = []
        self.relations: list[str] = []
        if self.state.source is not None:
            self.reload()

    @property
    def projections(self) -> tuple[str, ...]:
        return tuple(sorted(PROJECTIONS))

    @property
    def active_topology(self) -> str:
        if self.state.projection == "hierarchy":
            return "structuretree"
        return self.state.topology

    @staticmethod
    def _phase_progress(
        callback: OpenProgressCallback | None,
        start: int,
        end: int,
    ) -> ProgressCallback | None:
        if callback is None:
            return None

        def report(fraction: float, detail: str) -> None:
            bounded = max(0.0, min(1.0, fraction))
            percent = start + round((end - start) * bounded)
            callback(percent, detail)

        return report

    def _load(
        self,
        candidate: Path,
        progress: OpenProgressCallback | None = None,
    ) -> None:
        if progress is not None:
            progress(0, "starting CW load")

        documents = load_documents(
            candidate,
            progress=self._phase_progress(progress, 0, 65),
        )
        nodes, edges = collect_graph(
            documents,
            progress=self._phase_progress(progress, 65, 82),
        )
        structure_nodes, structure_edges = collect_structure_tree(
            documents,
            progress=self._phase_progress(progress, 82, 99),
        )

        self.state.source = candidate
        self.nodes = nodes
        self.edges = edges
        self.structure_nodes = structure_nodes
        self.structure_edges = structure_edges
        self._refresh_relations()

        if progress is not None:
            progress(100, "CW ready")

    def open(
        self,
        source: Path,
        progress: OpenProgressCallback | None = None,
    ) -> None:
        self._load(source.expanduser().resolve(), progress)

    def reload(self, progress: OpenProgressCallback | None = None) -> None:
        if self.state.source is None:
            self.nodes = {}
            self.edges = []
            self.structure_nodes = {}
            self.structure_edges = []
            self.relations = []
            return
        self._load(self.state.source, progress)

    def _refresh_relations(self) -> None:
        self.relations = sorted({edge.relation for edge in self.edges})
        if self.relations and self.state.topology not in self.relations:
            self.state.topology = self.relations[0]
        if self.state.projection not in PROJECTIONS:
            self.state.projection = "hierarchy"

    def selected_edges(self) -> list[Edge]:
        return [edge for edge in self.edges if edge.relation == self.state.topology]

    def project(self) -> ProjectionResult:
        if self.state.source is None:
            return ProjectionResult(
                name=self.state.projection,
                lines=("No source loaded. Press o to open a CW folder or monolith.",),
            )

        projector = PROJECTIONS[self.state.projection]
        if self.state.projection == "hierarchy":
            return projector(self.structure_edges, self.structure_nodes)
        return projector(self.selected_edges(), self.nodes)

    def select_topology(self, topology: str) -> None:
        if topology not in self.relations:
            raise ValueError(f"topology not present: {topology}")
        self.state.topology = topology

    def select_projection(self, projection: str) -> None:
        if projection not in PROJECTIONS:
            raise ValueError(f"unknown projection: {projection}")
        self.state.projection = projection
