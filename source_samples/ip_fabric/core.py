"""Canonical source of truth: immutable Markdown/JSON revisions, no database needed."""
import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def identifier(value):
    if not re.fullmatch(r"ip_[0-9a-f]{32}", value):
        raise ValueError("Invalid internal IP ID")
    return value


class Core:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def writer(self):
        lock = self.root / ".writer-lock"
        try:
            lock.mkdir()
        except FileExistsError:
            raise RuntimeError("Canonical writer active; inspect stale lock manually after a crash")
        try:
            yield
        finally:
            lock.rmdir()

    def asset_dir(self, ip_id):
        return self.root / "assets" / identifier(ip_id)

    def read(self, ip_id):
        base = self.asset_dir(ip_id)
        head = json.loads((base / "HEAD.json").read_text(encoding="utf-8"))
        revision = head["revision"]
        if not isinstance(revision, int) or revision < 1:
            raise ValueError("Invalid revision")
        folder = base / "revisions" / str(revision)
        manifest_bytes = (folder / "manifest.json").read_bytes()
        if digest(manifest_bytes) != head["manifest_sha256"]:
            raise ValueError("HEAD manifest checksum mismatch")
        manifest = json.loads(manifest_bytes)
        for name, expected in manifest.items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or path.is_symlink():
                raise ValueError("Unsafe canonical path")
            if digest(path.read_bytes()) != expected:
                raise ValueError("Canonical checksum mismatch: " + name)
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        self.check_metadata(metadata)
        if metadata["ip_id"] != ip_id or metadata["version"] != revision:
            raise ValueError("Canonical identity/version mismatch")
        content = (folder / "content.md").read_text(encoding="utf-8")
        if digest(content.encode()) != metadata["content_hash"]:
            raise ValueError("Content hash mismatch")
        for attachment in metadata["attachments"]:
            name = attachment["path"]
            if name not in manifest or manifest[name] != attachment["sha256"]:
                raise ValueError("Attachment manifest mismatch")
            if (folder / name).stat().st_size != attachment["size"]:
                raise ValueError("Attachment size mismatch")
        return metadata, content, folder

    def ids(self):
        return sorted(p.parent.name for p in (self.root / "assets").glob("*/HEAD.json"))

    def find(self, source, external_id):
        for ip_id in self.ids():
            m, _, _ = self.read(ip_id)
            if m["source"] == source and m.get("source_external_id") == external_id:
                return ip_id
        return None

    @staticmethod
    def check_metadata(m):
        required = {"schema_version", "ip_id", "type", "title", "created_at", "updated_at",
                    "source", "author", "derived_from", "project", "domain", "status",
                    "version", "validation", "relationships", "content_hash", "attachments"}
        if required - m.keys():
            raise ValueError("Missing metadata: " + str(sorted(required - m.keys())))
        identifier(m["ip_id"])
        if m["schema_version"] != 1 or m["status"] not in {
            "external_evidence", "candidate", "validated", "canonical", "deprecated", "superseded"
        }:
            raise ValueError("Invalid schema or lifecycle status")
        if not m["title"] or not m["type"] or not m["source"]:
            raise ValueError("Title, type and source are required")
        if not isinstance(m["version"], int) or m["version"] < 1:
            raise ValueError("Invalid version")
        for key in ("created_at", "updated_at"):
            if datetime.fromisoformat(m[key]).tzinfo is None:
                raise ValueError("Timezone required")
        for parent in m["derived_from"]:
            identifier(parent)
        for rel in m["relationships"]:
            if not rel.get("relation"):
                raise ValueError("Relation type required")
            identifier(rel["target"])
        if m["status"] in {"validated", "canonical"} and not m["validation"].get("actor"):
            raise ValueError("Validation evidence required")
        if m["status"] == "canonical" and not m.get("promotion", {}).get("actor"):
            raise ValueError("Explicit promotion required")

    def _write(self, metadata, content, attachments, evidence=None):
        self.check_metadata(metadata)
        base = self.asset_dir(metadata["ip_id"])
        revisions = base / "revisions"
        revisions.mkdir(parents=True, exist_ok=True)
        # Preserve orphan revisions left before a failed HEAD update; never overwrite.
        existing = [int(p.name) for p in revisions.iterdir() if p.name.isdigit()]
        metadata["version"] = max(existing, default=0) + 1
        folder = revisions / str(metadata["version"])
        folder.mkdir()
        files = {"content.md": content.encode(), "metadata.json": encode(metadata)}
        if evidence is not None:
            files["evidence.json"] = encode(evidence)
        files.update(attachments)
        for name, data in files.items():
            target = folder / name
            if not target.resolve().is_relative_to(folder.resolve()):
                raise ValueError("Unsafe attachment path")
            atomic(target, data)
        manifest = encode({name: digest(data) for name, data in files.items()})
        atomic(folder / "manifest.json", manifest)
        atomic(base / "HEAD.json", encode({"revision": metadata["version"],
                                           "manifest_sha256": digest(manifest)}))
        return metadata

    def ingest(self, content, *, title, source="local", source_external_id=None,
               artifact_type="document", project="academy", domain="operations", author=None,
               derived_from=None, relationships=None, attachments=None, evidence=None,
               status="candidate", ip_id=None):
        if status not in {"candidate", "external_evidence"}:
            raise ValueError("Ingest cannot promote; use validate then promote")
        if source == "ai" and status != "candidate":
            raise ValueError("AI output must start as candidate")
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        blobs, att = {}, []
        for name, data in sorted((attachments or {}).items()):
            if Path(name).name != name or name in {".", ".."} or "\\" in name:
                raise ValueError("Attachment must have a plain filename")
            key = "attachments/" + digest(data) + Path(name).suffix[:12]
            blobs[key] = data
            att.append({"name": name, "path": key, "sha256": digest(data), "size": len(data)})
        payload = dict(title=title, source=source, source_external_id=source_external_id,
                       type=artifact_type, project=project, domain=domain, author=author,
                       derived_from=derived_from or [], relationships=relationships or [],
                       attachments=att, content_hash=digest(content.encode()))
        incoming_hash = digest(encode({**payload, "evidence": evidence}))
        with self.writer():
            mapped = self.find(source, source_external_id) if source_external_id else None
            if mapped and ip_id and mapped != ip_id:
                raise ValueError("External ID already mapped to another asset")
            ip_id = ip_id or mapped or "ip_" + uuid.uuid4().hex
            previous = self.read(ip_id)[0] if (self.asset_dir(ip_id) / "HEAD.json").exists() else None
            if previous and (previous["source"], previous.get("source_external_id")) != (source, source_external_id):
                raise ValueError("Cannot replace source identity")
            if previous and previous.get("ingest_hash") == incoming_hash:
                return {"ip_id": ip_id, "changed": False, "version": previous["version"]}
            for parent in payload["derived_from"] + [r["target"] for r in payload["relationships"]]:
                self.read(parent)
            metadata = {**payload, "schema_version": 1, "ip_id": ip_id,
                        "created_at": previous["created_at"] if previous else now(), "updated_at": now(),
                        "status": status, "version": 1, "validation": {"state": "pending"},
                        "ingest_hash": incoming_hash}
            self._write(metadata, content, blobs, evidence)
            return {"ip_id": ip_id, "changed": True, "version": metadata["version"]}

    def transition(self, ip_id, status, actor, reason):
        if not actor.strip() or not reason.strip():
            raise ValueError("Named actor and reason are required")
        transitions = {"external_evidence": {"candidate", "deprecated"},
                       "candidate": {"validated", "deprecated"},
                       "validated": {"canonical", "candidate", "deprecated"},
                       "canonical": {"deprecated", "superseded"},
                       "deprecated": {"candidate"}, "superseded": {"candidate"}}
        with self.writer():
            m, content, folder = self.read(ip_id)
            if status not in transitions[m["status"]]:
                raise ValueError("Invalid lifecycle transition")
            event = {"from": m["status"], "to": status, "actor": actor, "reason": reason, "at": now()}
            m["status"] = status
            m["updated_at"] = now()
            m.setdefault("events", []).append(event)
            if status == "validated":
                m["validation"] = {"state": "validated", **event}
            elif status == "canonical":
                m["promotion"] = event
            elif status == "candidate":
                m["validation"] = {"state": "pending"}
                m.pop("promotion", None)
            attachments = {a["path"]: (folder / a["path"]).read_bytes() for a in m["attachments"]}
            evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8")) if (folder / "evidence.json").exists() else None
            return self._write(m, content, attachments, evidence)

    def verify(self):
        errors = []
        for base in (self.root / "assets").glob("*"):
            if base.is_dir() and not (base / "HEAD.json").exists():
                errors.append({"ip_id": base.name, "error": "Missing HEAD; interrupted write or data loss"})
        for ip_id in self.ids():
            try:
                m, _, _ = self.read(ip_id)
                for rel in m["derived_from"] + [r["target"] for r in m["relationships"]]:
                    self.read(rel)
                for folder in (self.asset_dir(ip_id) / "revisions").iterdir():
                    if not folder.name.isdigit():
                        continue
                    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
                    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p.name != "manifest.json"}
                    if actual != set(manifest):
                        raise ValueError("Unmanifested/missing files in revision " + folder.name)
                    for name, checksum in manifest.items():
                        target = (folder / name).resolve()
                        if not target.is_relative_to(folder.resolve()) or digest(target.read_bytes()) != checksum:
                            raise ValueError("Revision integrity failure")
            except (ValueError, KeyError, OSError, TypeError) as exc:
                errors.append({"ip_id": ip_id, "error": str(exc)})
        return {"ok": not errors, "assets": len(self.ids()), "errors": errors}

    def checkpoint(self, key, value=None):
        path = self.root / "sync" / (digest(key.encode()) + ".json")
        if value is not None:
            with self.writer():
                atomic(path, encode({"source_key": key, **value}))
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
