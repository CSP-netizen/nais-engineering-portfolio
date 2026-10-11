"""Disposable SQLite vector/relations cache; canonical JSON is authoritative."""
import json
import math
import os
import sqlite3
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from .core import digest, encode
from hybrid_ai.provider import LMStudioEmbedding

CHUNK_VERSION = "characters-800-overlap-100-v1"


def chunks(text):
    normalized = text.replace("\r\n", "\n").strip()
    return [normalized[i:i + 800] for i in range(0, len(normalized), 700)]


class LegacyOllamaEmbedding:
    def __init__(self, host="http://127.0.0.1:11434", model="nomic-embed-text:latest"):
        self.host, self.model = host.rstrip("/"), model
        tags = self.request("/api/tags")["models"]
        matches = [m for m in tags if m["name"] == model or m["name"] == model + ":latest"]
        if not matches:
            raise RuntimeError("Embedding model is not installed; no fake embedding fallback")
        self.model = matches[0]["name"]
        self.signature = self.model + "@" + matches[0]["digest"] + ":nomic-prefix-v1"

    def request(self, route, payload=None):
        req = urllib.request.Request(self.host + route,
                                     data=encode(payload) if payload is not None else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)

    def embed(self, texts, query=False):
        prefix = ("search_query: " if query else "search_document: ") if self.model.startswith("nomic-embed-text") else ""
        vectors = self.request("/api/embed", {"model": self.model,
                               "input": [prefix + text for text in texts], "truncate": False})["embeddings"]
        if len(vectors) != len(texts):
            raise ValueError("Embedding response count mismatch")
        for vector in vectors:
            if not vector or not all(math.isfinite(x) for x in vector) or not any(vector):
                raise ValueError("Invalid embedding")
        return vectors


class OllamaEmbedding:
    """Backward-compatible adapter name.

    Normal Mode routes embedding requests to
    Windows-host LM Studio.

    Existing callers may still supply the old
    Ollama host/model arguments. Those arguments
    are ignored in LM Studio mode.

    Setting HARNESS_INFERENCE_PROVIDER=ollama
    explicitly restores the legacy implementation.
    """

    def __new__(
        cls,
        host="http://127.0.0.1:11434",
        model="nomic-embed-text:latest",
    ):

        provider = os.getenv(
            "HARNESS_INFERENCE_PROVIDER",
            "lmstudio",
        ).strip().lower()

        if provider == "ollama":
            return LegacyOllamaEmbedding(
                host,
                model,
            )

        return LMStudioEmbedding()


class Index:
    def __init__(self, core, directory, embedder):
        self.core = core
        self.directory = Path(directory).resolve()
        if self.directory == core.root or self.directory.is_relative_to(core.root) or core.root.is_relative_to(self.directory):
            raise ValueError("Canonical and derived directories must be disjoint")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "index.sqlite3"
        self.embedder = embedder

    @staticmethod
    def schema(db):
        db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (ip_id TEXT PRIMARY KEY, fingerprint TEXT, metadata TEXT);
            CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, ip_id TEXT, ordinal INTEGER,
                text TEXT, vector TEXT, cache_key TEXT, model TEXT, strategy TEXT);
            CREATE INDEX IF NOT EXISTS parent_lookup ON chunks(ip_id);
            CREATE TABLE IF NOT EXISTS relations (ip_id TEXT, relation TEXT, target TEXT);
        """)

    def update(self, rebuild=False):
        verification = self.core.verify()
        if not verification["ok"]:
            raise ValueError("Refusing index update: canonical integrity failure")
        target = self.directory / ("rebuild-" + uuid.uuid4().hex + ".sqlite3") if rebuild else self.path
        stats = {"documents_changed": 0, "documents_skipped": 0, "chunks_embedded": 0, "documents_removed": 0}
        db = sqlite3.connect(target)
        try:
            self.schema(db)
            with db:
                retained = set()
                for ip_id in self.core.ids():
                    m, content, _ = self.core.read(ip_id)
                    if m["status"] in {"deprecated", "superseded"}:
                        continue
                    retained.add(ip_id)
                    fp = digest(encode({"metadata": m, "model": self.embedder.signature, "strategy": CHUNK_VERSION}))
                    old = db.execute("SELECT fingerprint FROM documents WHERE ip_id=?", (ip_id,)).fetchone()
                    if old and old[0] == fp:
                        stats["documents_skipped"] += 1
                        continue
                    text_chunks = chunks(content)
                    cached = dict(db.execute("SELECT cache_key, vector FROM chunks WHERE ip_id=?", (ip_id,)))
                    keys = [digest(encode([self.embedder.signature, CHUNK_VERSION, text])) for text in text_chunks]
                    missing = list(dict.fromkeys(k for k in keys if k not in cached))
                    if missing:
                        lookup = dict(zip(keys, text_chunks))
                        vectors = self.embedder.embed([lookup[k] for k in missing])
                        if len(vectors) != len(missing):
                            raise ValueError("Embedding count mismatch")
                        cached.update({k: json.dumps(v) for k, v in zip(missing, vectors)})
                        stats["chunks_embedded"] += len(missing)
                    db.execute("DELETE FROM chunks WHERE ip_id=?", (ip_id,))
                    db.execute("DELETE FROM relations WHERE ip_id=?", (ip_id,))
                    for ordinal, (text, key) in enumerate(zip(text_chunks, keys)):
                        chunk_id = digest(encode([ip_id, ordinal, key]))
                        db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)",
                                   (chunk_id, ip_id, ordinal, text, cached[key], key, self.embedder.signature, CHUNK_VERSION))
                    for r in m["relationships"] + [{"relation": "derived_from", "target": p} for p in m["derived_from"]]:
                        db.execute("INSERT INTO relations VALUES (?,?,?)", (ip_id, r["relation"], r["target"]))
                    db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?)", (ip_id, fp, json.dumps(m)))
                    stats["documents_changed"] += 1
                for (ip_id,) in db.execute("SELECT ip_id FROM documents").fetchall():
                    if ip_id not in retained:
                        for table in ("chunks", "relations", "documents"):
                            db.execute("DELETE FROM " + table + " WHERE ip_id=?", (ip_id,))
                        stats["documents_removed"] += 1
        except Exception:
            db.close()
            if rebuild:
                target.unlink(missing_ok=True)
            raise
        else:
            db.close()
            if rebuild:
                os.replace(target, self.path)
        return stats

    def search(self, query, limit=5, **filters):
        allowed = {"ip_id", "project", "domain", "type", "status", "source", "version", "updated_after", "updated_before"}
        if set(filters) - allowed:
            raise ValueError("Unknown metadata filter")
        if limit < 1:
            raise ValueError("Limit must be positive")
        for key in ("updated_after", "updated_before"):
            if key in filters and datetime.fromisoformat(filters[key]).tzinfo is None:
                raise ValueError("Date filters require timezone-aware ISO timestamps")
        if not self.path.exists():
            raise RuntimeError("Index absent; run rebuild-index")
        filters.setdefault("status", "canonical")
        q = self.embedder.embed([query], query=True)[0]
        results = []
        db = sqlite3.connect(self.path)
        try:
            sql = "SELECT c.chunk_id,c.ip_id,c.text,c.vector,c.model,d.metadata FROM chunks c JOIN documents d USING(ip_id)"
            params = ()
            if 'ip_id' in filters:
                sql += ' WHERE c.ip_id = ?'
                params = (filters['ip_id'],)
            rows = db.execute(sql, params)
            for chunk_id, ip_id, text, vector, model, raw_metadata in rows:
                m = json.loads(raw_metadata)
                current, _, folder = self.core.read(ip_id)
                # Never return stale/promoted/deprecated content from an old cache.
                if current != m:
                    continue
                if model != self.embedder.signature:
                    raise ValueError("Embedding model changed; rebuild index")
                if any(m[k] != v for k, v in filters.items() if k not in {"updated_after", "updated_before"}):
                    continue
                if filters.get("updated_after") and datetime.fromisoformat(m["updated_at"]) < datetime.fromisoformat(filters["updated_after"]):
                    continue
                if filters.get("updated_before") and datetime.fromisoformat(m["updated_at"]) > datetime.fromisoformat(filters["updated_before"]):
                    continue
                v = json.loads(vector)
                if len(v) != len(q):
                    raise ValueError("Embedding dimension mismatch")
                denom = math.sqrt(sum(x*x for x in q) * sum(x*x for x in v))
                score = sum(a*b for a, b in zip(q, v)) / denom if denom else 0.0
                results.append({"score": score, "ip_id": ip_id, "chunk_id": chunk_id,
                                "text": text, "canonical_path": str(folder / "content.md"),
                                "metadata": m})
        finally:
            db.close()
        return sorted(results, key=lambda r: (-r["score"], r["chunk_id"]))[:limit]

    def lineage(self, ip_id):
        m, _, folder = self.core.read(ip_id)
        child_chunks = []
        if self.path.exists():
            db = sqlite3.connect(self.path)
            try:
                child_chunks = [dict(zip(["chunk_id", "ordinal", "model", "strategy"], r)) for r in
                                db.execute("SELECT chunk_id,ordinal,model,strategy FROM chunks WHERE ip_id=? ORDER BY ordinal", (ip_id,))]
            finally:
                db.close()
        return {"metadata": m, "artifact_path": str(folder), "index_path": str(self.path), "chunks": child_chunks}
