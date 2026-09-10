from .hierarchy import project as project_hierarchy
from .mermaid import project as project_mermaid
from .topology import project as project_topology

PROJECTIONS = {
    "hierarchy": project_hierarchy,
    "topology": project_topology,
    "mermaid": project_mermaid,
}

__all__ = ["PROJECTIONS", "project_hierarchy", "project_topology", "project_mermaid"]
