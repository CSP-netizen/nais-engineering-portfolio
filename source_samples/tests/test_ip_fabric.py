import copy
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from ip_fabric.core import Core
from ip_fabric.index import Index, OllamaEmbedding
from ip_fabric.notion import NotionAdapter, NotionClient


class TestEmbedding:
    """Only for deterministic unit tests, never offered by production CLI."""
    signature = "test-only-v1"

    def __init__(self):
        self.calls = 0

    def embed(self, texts, query=False):
        self.calls += len(texts)
        return [[1 + t.lower().count("student"), 1 + t.lower().count("robot"), 1] for t in texts]


class FabricSetup:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.core = Core(self.base / "canonical")
        self.embedding = TestEmbedding()
        self.index = Index(self.core, self.base / "derived", self.embedding)

    def asset(self, text="student learning plan", external_id="lesson", **kwargs):
        return self.core.ingest(text, title="Lesson", source_external_id=external_id, **kwargs)["ip_id"]

    def promote(self, ip_id):
        self.core.transition(ip_id, "validated", "tester", "content reviewed")
        self.core.transition(ip_id, "canonical", "human-reviewer", "approved fixture")


class FabricTests(FabricSetup, unittest.TestCase):
    def test_A_B_D_J_metadata_portability_and_lineage(self):
        parent = self.asset()
        child = self.asset("student assessment", "assessment", derived_from=[parent],
                           relationships=[{"relation": "references", "target": parent}], attachments={"rubric.txt": b"rubric"})
        self.promote(child)
        self.index.update()
        hit = self.index.search("student assessment")[0]
        self.assertEqual(hit["ip_id"], child)
        self.assertTrue(Path(hit["canonical_path"]).is_file())
        m, text, folder = self.core.read(child)
        self.assertEqual(m["derived_from"], [parent])
        self.assertEqual(m["source_external_id"], "assessment")
        self.assertEqual(m["project"], "academy")
        self.assertEqual((folder / m["attachments"][0]["path"]).read_bytes(), b"rubric")
        self.assertTrue(self.index.lineage(child)["chunks"])
        self.assertEqual(json.loads((folder / "metadata.json").read_text())["ip_id"], child)
        self.assertTrue(self.core.verify()["ok"])

    def test_E_F_incremental_and_metadata_only_changes(self):
        a, b = self.asset(), self.asset("robot control", "robot")
        self.index.update()
        before = self.embedding.calls
        self.assertEqual(self.index.update()["documents_skipped"], 2)
        self.assertEqual(self.embedding.calls, before)
        self.promote(a)
        self.assertEqual(self.index.update()["chunks_embedded"], 0)
        self.assertFalse(self.core.ingest("student learning plan", title="Lesson", source_external_id="lesson")["changed"])
        self.asset("student learning plan updated")
        stats = self.index.update()
        self.assertEqual(stats["documents_changed"], 1)
        self.assertEqual(stats["documents_skipped"], 1)
        self.assertEqual(stats["chunks_embedded"], 1)
        self.assertEqual(self.core.read(a)[0]["status"], "candidate")

    def test_G_H_I_delete_entire_index_restore_from_canonical_only(self):
        ip_id = self.asset()
        self.promote(ip_id)
        self.index.update()
        initial = self.index.search("student")[0]
        # Only delete this test's derived directory, never any production vector store.
        self.assertTrue(self.index.directory.is_relative_to(self.base))
        shutil.rmtree(self.index.directory)
        copied = self.base / "recovered-canonical"
        shutil.copytree(self.core.root, copied)
        restored = Index(Core(copied), self.base / "rebuilt-derived", TestEmbedding())
        restored.update(rebuild=True)
        hit = restored.search("student")[0]
        self.assertEqual(hit["ip_id"], initial["ip_id"])
        self.assertEqual(hit["chunk_id"], initial["chunk_id"])

    def test_K_promotion_gate_and_stale_index(self):
        ip_id = self.asset(source="ai")
        with self.assertRaises(ValueError):
            self.core.transition(ip_id, "canonical", "agent", "skip validation")
        with self.assertRaises(ValueError):
            self.core.ingest("text", title="bad", status="canonical")
        self.index.update()
        self.assertEqual(self.index.search("student"), [])
        self.promote(ip_id)
        self.index.update()
        self.assertEqual(len(self.index.search("student")), 1)
        self.core.transition(ip_id, "deprecated", "reviewer", "outdated")
        self.assertEqual(self.index.search("student"), [])
        self.assertEqual(self.index.update()["documents_removed"], 1)

    def test_integrity_and_path_guards(self):
        ip_id = self.asset()
        with self.assertRaises(ValueError):
            self.core.read("../../outside")
        with self.assertRaises(ValueError):
            Index(self.core, self.core.root / "index", self.embedding)
        with self.assertRaises(ValueError):
            self.asset(attachments={"../bad": b"bad"})
        _, _, folder = self.core.read(ip_id)
        (folder / "content.md").write_text("tampered")
        self.assertFalse(self.core.verify()["ok"])
        with self.assertRaises(ValueError):
            self.index.update()

    def test_filter_model_version_and_failure_atomicity(self):
        ip_id = self.asset()
        self.promote(ip_id)
        self.index.update()
        self.assertEqual(self.index.search("student", project="other"), [])
        self.assertEqual(self.index.search("student", version=999), [])
        self.assertEqual(len(self.index.search("student", domain="operations", source="local")), 1)
        before = self.index.path.read_bytes()
        self.embedding.embed = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("embedding offline"))
        with self.assertRaises(RuntimeError):
            self.index.update(rebuild=True)
        self.assertEqual(self.index.path.read_bytes(), before)

    def test_writer_lock_and_source_mapping(self):
        ip_id = self.asset()
        with self.core.writer(), self.assertRaises(RuntimeError):
            self.asset("other")
        self.assertEqual(self.asset("updated"), ip_id)
        with self.assertRaises(ValueError):
            self.core.ingest("bad", title="bad", ip_id=ip_id, source="notion")

    def test_changed_chunk_only_and_new_model_reprocess(self):
        ip_id = self.asset("a" * 1600)
        self.index.update()
        self.asset("a" * 1599 + "b")
        result = self.index.update()
        self.assertEqual(result["documents_changed"], 1)
        self.assertEqual(result["chunks_embedded"], 1)
        self.embedding.signature = "test-only-v2"
        self.assertGreater(self.index.update()["chunks_embedded"], 1)

    def test_existing_attendance_regression(self):
        from attendance_manager import AttendanceManager
        manager = AttendanceManager(str(self.base / "attendance"))
        self.assertTrue(manager.record_attendance("[STUDENT_001]", "2026-09-30", "absent"))
        self.assertFalse(manager.record_attendance("unmasked", "2026-09-30"))
        self.assertEqual(manager.get_attendance_by_student("[STUDENT_001]")[0]["status"], "absent")


class FakeNotion:
    def __init__(self):
        self.page = {"id": "notion-page-1", "last_edited_time": "2026-09-30T00:00:00Z",
                     "created_time": "2026-09-01T00:00:00Z", "created_by": {"id": "author"},
                     "properties": {"Name": {"type": "title", "title": [{"plain_text": "Academy"}]}}}
        self.block_calls = 0
        self.fail = False

    def request(self, route):
        if self.fail:
            raise RuntimeError("Notion API HTTP 404")
        if route.startswith("/databases/"):
            return {"data_sources": [{"id": "ds1"}]}
        return copy.deepcopy(self.page)

    def pages(self, route, payload=None):
        if route.startswith("/data_sources/"):
            return iter([copy.deepcopy(self.page)])
        self.block_calls += 1
        return iter([{"id": "b1", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Student learning"}]}},
                     {"id": "b2", "type": "file", "file": {"type": "file", "file": {"url": "https://s3.amazonaws.com/a.pdf?secret=ephemeral"}}}])

    def download(self, url):
        return b"sample attachment"


class NotionTests(FabricSetup, unittest.TestCase):
    def test_notion_incremental_attachment_tombstone(self):
        client = FakeNotion()
        adapter = NotionAdapter(self.core, client)
        result = adapter.sync_page("notion-page-1")
        ip_id = result["ip_id"]
        m, text, folder = self.core.read(ip_id)
        self.assertNotEqual(ip_id, "notion-page-1")
        self.assertEqual(m["status"], "external_evidence")
        self.assertEqual(len(m["attachments"]), 1)
        self.assertNotIn("ephemeral", (folder / "evidence.json").read_text())
        self.assertTrue(adapter.sync_page("notion-page-1")["skipped"])
        self.assertEqual(client.block_calls, 1)
        client.page["last_edited_time"] = "2026-09-30T01:00:00Z"
        self.assertEqual(adapter.sync_page("notion-page-1")["ip_id"], ip_id)
        self.assertEqual(client.block_calls, 2)
        client.page["archived"] = True
        adapter.sync_page("notion-page-1")
        self.assertEqual(self.core.read(ip_id)[0]["status"], "deprecated")
        self.assertTrue(folder.is_dir())

    def test_notion_database_and_no_delete_on_404(self):
        client = FakeNotion()
        adapter = NotionAdapter(self.core, client)
        self.assertTrue(adapter.sync_database("db1")["ok"])
        ip_id = self.core.ids()[0]
        client.fail = True
        self.assertFalse(adapter.sync_data_source("ds1")["ok"])
        self.assertEqual(self.core.read(ip_id)[0]["status"], "external_evidence")

    def test_notion_pagination(self):
        client = NotionClient("test-token")
        calls = []
        def request(route, payload=None):
            calls.append((route, payload))
            return {"results": [len(calls)], "has_more": len(calls) == 1, "next_cursor": "next"}
        client.request = request
        self.assertEqual(list(client.pages("/blocks/a/children")), [1, 2])
        self.assertIn("start_cursor=next", calls[1][0])

    def test_failed_attachment_is_explicit_and_retried(self):
        client = FakeNotion()
        client.download = lambda url: (_ for _ in ()).throw(ValueError("blocked"))
        adapter = NotionAdapter(self.core, client)
        self.assertTrue(adapter.sync_page("notion-page-1")["warnings"])
        self.assertTrue(adapter.sync_page("notion-page-1")["warnings"])
        self.assertEqual(client.block_calls, 2)

    def test_attachment_network_boundaries(self):
        client = NotionClient("not-a-real-token")
        for url in ("http://s3.amazonaws.com/file", "https://127.0.0.1/", "https://example.com/file", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                client.download(url)


@unittest.skipUnless(os.environ.get("IP_FABRIC_LIVE_TEST") == "1", "enable explicitly for local semantic acceptance")
class LiveSemanticTests(FabricSetup, unittest.TestCase):
    def test_C_D_G_H_I_real_semantic_rebuild(self):
        self.embedding = OllamaEmbedding(os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434"))
        self.index = Index(self.core, self.base / "real-derived", self.embedding)
        lesson = self.asset("Teachers record absent pupils and notify parents when a child misses class.")
        robot = self.asset("A robotic manipulator uses inverse kinematics to position the gripper.", "robot")
        for ip_id in (lesson, robot):
            self.promote(ip_id)
        self.assertEqual(self.index.update()["chunks_embedded"], 2)
        query = "How should the school handle a learner who did not attend?"
        self.assertEqual(self.index.search(query)[0]["ip_id"], lesson)
        self.assertEqual(self.index.update()["chunks_embedded"], 0)
        self.assertTrue(self.index.directory.is_relative_to(self.base))
        shutil.rmtree(self.index.directory)
        self.index = Index(self.core, self.base / "real-derived", self.embedding)
        self.index.update(rebuild=True)
        self.assertEqual(self.index.search(query)[0]["ip_id"], lesson)


if __name__ == "__main__":
    unittest.main()
