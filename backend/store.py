import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY, hash TEXT NOT NULL, width INTEGER, height INTEGER
                );
                CREATE TABLE IF NOT EXISTS extractions (
                    id TEXT PRIMARY KEY, image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                    cache_key TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS extraction_cache ON extractions(cache_key, status);
                CREATE TABLE IF NOT EXISTS metrics (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
            """)
            interrupted = db.execute(
                "SELECT id, payload FROM extractions WHERE status NOT IN ('completed', 'failed')"
            ).fetchall()
            for item in interrupted:
                payload = json.loads(item["payload"])
                payload.update(status="failed", error="Processing interrupted by restart. Extract again.")
                db.execute("UPDATE extractions SET status='failed', payload=? WHERE id=?",
                           (json.dumps(payload), item["id"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "app.sqlite3", timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def image(self, image_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
        return dict(row) if row else None

    def extraction(self, extraction_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM extractions WHERE id=?", (extraction_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def save_extraction(self, payload: dict, cache_key: str):
        with self.connect() as db:
            db.execute(
                "INSERT INTO extractions VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
                (payload["id"], payload["imageId"], cache_key, payload["status"],
                 json.dumps(payload, ensure_ascii=False)),
            )

    def bump(self, name: str):
        with self.connect() as db:
            db.execute("INSERT INTO metrics VALUES (?, 1) "
                       "ON CONFLICT(name) DO UPDATE SET value=value+1", (name,))

    def metrics(self) -> dict:
        with self.connect() as db:
            rows = db.execute("SELECT name, value FROM metrics").fetchall()
        result = {"ocrCalls": 0, "modelCalls": 0, "cacheHits": 0}
        result.update({row["name"]: row["value"] for row in rows})
        return result
