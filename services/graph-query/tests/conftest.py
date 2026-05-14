"""Shared pytest fixtures for the graph-query service.

The query engine talks to Neo4j through ``GraphQueryEngine.execute_query``
and constructs Cypher WHERE clauses with ``_l7_match_where``. To keep
the test surface focused on the pure-Python filter/aggregation logic
introduced for the Integration Hub L7 parity work (Audit v3), we expose
a ``mock_engine`` fixture that:

* instantiates ``GraphQueryEngine`` without ever opening a real Neo4j
  driver (``_connect`` is patched to a no-op),
* replaces ``execute_query`` with a side-effectful stub the tests can
  program with the rows they want to feed the aggregator.

Tests get a strongly-typed helper (``set_rows``) so individual cases
read like data tables.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import pytest

# Ensure the service package is importable when pytest is invoked from
# the repo root or from inside ``services/graph-query/``. We prepend
# the service directory so ``import app.graph_query_engine`` matches the
# layout used by the Dockerfile.
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

# Pydantic-Settings will refuse to load without a Neo4j password. Provide
# placeholders for the test environment before importing ``app`` modules.
os.environ.setdefault("NEO4J_PASSWORD", "test-password")
os.environ.setdefault("NEO4J_USER", "neo4j")


@pytest.fixture
def mock_engine(monkeypatch: pytest.MonkeyPatch):
    """Return a ``GraphQueryEngine`` with a stubbed ``execute_query``.

    Usage::

        def test_something(mock_engine):
            engine, set_rows = mock_engine
            set_rows([{...}, {...}])
            response = engine.get_l7_dependency_summary(analysis_id="A1")

    ``set_rows`` accepts either a static list (echoed for every call) or
    a callable ``(query, params) -> List[dict]`` for tests that need to
    inspect the Cypher parameters the engine emits.
    """
    from app.graph_query_engine import GraphQueryEngine  # noqa: WPS433

    # Prevent the constructor from attempting to open a Bolt connection.
    monkeypatch.setattr(GraphQueryEngine, "_connect", lambda self: None)

    engine = GraphQueryEngine()
    engine.driver = object()  # truthy so execute_query short-circuits the lazy reconnect

    state: Dict[str, Any] = {"rows": [], "captured": []}

    def _execute_query(query: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows_src = state["rows"]
        if callable(rows_src):
            rows: List[Dict[str, Any]] = list(rows_src(query, parameters or {}))
        else:
            rows = list(rows_src)
        state["captured"].append({"query": query, "parameters": dict(parameters or {})})
        return {"success": True, "data": rows, "count": len(rows)}

    engine.execute_query = _execute_query  # type: ignore[assignment]

    def set_rows(rows: "Iterable[Dict[str, Any]] | Callable[[str, Dict[str, Any]], Iterable[Dict[str, Any]]]") -> None:
        state["rows"] = rows

    # Expose captured query metadata for assertions.
    engine._captured_queries = state["captured"]  # type: ignore[attr-defined]

    return engine, set_rows
