"""Resource checks retain connections so garbage collection cannot hide leaks."""
import sqlite3

import pytest


@pytest.fixture
def tracked_sqlite_connections(monkeypatch):
    original = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    yield connections
    try:
        assert connections
        for connection in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
    finally:
        for connection in connections:
            connection.close()
