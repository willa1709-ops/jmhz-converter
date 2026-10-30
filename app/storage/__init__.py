import json
from pathlib import Path
import sqlite3

from app.definitions import Artifact
from app.mapping import Profile


class Store:
    """Ukládá pouze konfiguraci a metadata, nikdy importované mzdové řádky."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, content TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS artifacts (sha256 TEXT, version TEXT, content TEXT NOT NULL, PRIMARY KEY(sha256, version))")

    def save_profile(self, profile: Profile) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?)", (profile.name, profile.dumps()))

    def load_profile(self, name: str) -> Profile:
        with sqlite3.connect(self.path) as connection:
            record = connection.execute("SELECT content FROM profiles WHERE name = ?", (name,)).fetchone()
        if record is None:
            raise ValueError("Profil neexistuje.")
        return Profile.loads(record[0])

    def save_artifact(self, artifact: Artifact) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT OR REPLACE INTO artifacts VALUES (?, ?, ?)",
                               (artifact.sha256, artifact.version, json.dumps(artifact.as_dict())))
