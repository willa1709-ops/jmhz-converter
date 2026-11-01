"""Short SQLite transactions that release the file on every exit path."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def database(path):
    connection = sqlite3.connect(str(path))
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        with connection:
            yield connection
    finally:
        # Connection.__exit__ only commits/rolls back; Windows also needs close().
        connection.close()
