from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.Topology.lib.graph import (
    Edge,
    Node,
    collect_graph,
    collect_structure_tree,
    load_documents,
)
from tools.Topology.lib.projection import ProjectionResult
from tools.Topology.projections import PROJECTIONS


@dataclass
class ProjectionState:
    source: Path | None = None
    topology: str = "containment"
    projection: str = "hierarchy"


class TopologyProjector:
    """Host-neutral CW topology projection service.

    The projector consumes canonical CW only. Other source types, such as code,
    are converted to CW by their own importer before being opened here.

    Canonical relation projections consume canonical Node/Edge data. The
    hierarchy projection consumes a separate derived StructureTree navigation
    graph over those same canonical Entity identities. Projection-only directory
    nodes never become canonical truth.
    """

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

    def open(self, source: Path) -> None:
        candidate = source.expanduser().resolve()
        documents = load_documents(candidate)
        nodes, edges = collect_graph(documents)
        structure_nodes, structure_edges = collect_structure_tree(documents)

        self.state.source = candidate
        self.nodes = nodes
        self.edges = edges
        self.structure_nodes = structure_nodes
        self.structure_edges = structure_edges
        self._refresh_relations()

    def reload(self) -> None:
        if self.state.source is None:
            self.nodes = {}
            self.edges = []
            self.structure_nodes = {}
            self.structure_edges = []
            self.relations = []
            return

        documents = load_documents(self.state.source)
        nodes, edges = collect_graph(documents)
        structure_nodes, structure_edges = collect_structure_tree(documents)

        self.nodes = nodes
        self.edges = edges
        self.structure_nodes = structure_nodes
        self.structure_edges = structure_edges
        self._refresh_relations()

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
