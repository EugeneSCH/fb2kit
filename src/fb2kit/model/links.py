"""Internal link resolution against the id index."""

from __future__ import annotations

from collections.abc import Iterable

from fb2kit import report
from fb2kit.builder import Builder
from fb2kit.model import iter_nodes
from fb2kit.model.inline import Link


def check_links(nodes: Iterable[object], ctx: Builder) -> None:
    for node in iter_nodes(nodes):
        if isinstance(node, Link) and node.href.startswith("#") and node.href[1:] not in ctx.index:
            ctx.warn(report.LINK_UNRESOLVED, f"link target {node.href!r} not found")
