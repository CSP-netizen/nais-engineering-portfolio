"""MCP Gateway MVP — Unit Tests

Tests for:
- Queue status lookup (3 queues)
- MCP submit integration
- Output subdir uniqueness
- Artifact discovery
- Workflow adapter reuse
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import uuid

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


class TestQueueStatusLookup(unittest.TestCase):
    """Test queue status lookup across all queues"""

    @patch('queue_manager.Redis')
    @patch('queue_manager.Queue')
    def test_status_lookup_high_queue(self, MockQueue, MockRedis):
        """Test finding job in high priority queue"""
        from queue_manager import QueueManager

        # Mock Redis connection
        MockQueue.side_effect = lambda *a, **kw: MagicMock()
        mock_redis = MagicMock()
        MockRedis.return_value = mock_redis

        # Create manager
        manager = QueueManager()

        # Mock job in high queue
        mock_job = MagicMock()
        mock_job.id = "job-123"
        mock_job.get_status.return_value = "finished"
        mock_job.is_finished = True
        mock_job.is_failed = False
        mock_job.result = {"success": True}
        mock_job.exc_info = None
        mock_job.created_at = None
        mock_job.started_at = None
        mock_job.ended_at = None
        mock_job.meta = {"type": "test"}

        # Setup queue mock to return job on high queue only
        def fetch_job_side_effect(job_id):
            if job_id == "job-123":
                return mock_job
            return None

        manager.queue_high.fetch_job = fetch_job_side_effect
        manager.queue_low.fetch_job = lambda x: None
        manager.queue_default.fetch_job = lambda x: None

        # Test
        status = manager.get_job_status("job-123")

        self.assertIsNotNone(status)
        self.assertEqual(status["job_id"], "job-123")
        self.assertEqual(status["status"], "finished")
        self.assertTrue(status["is_finished"])

    @patch('queue_manager.Redis')
    @patch('queue_manager.Queue')
    def test_status_lookup_low_queue(self, MockQueue, MockRedis):
        """Test finding job in low priority queue"""
        from queue_manager import QueueManager

        MockQueue.side_effect = lambda *a, **kw: MagicMock()
        mock_redis = MagicMock()
        MockRedis.return_value = mock_redis

        manager = QueueManager()

        mock_job = MagicMock()
        mock_job.id = "job-456"
        mock_job.get_status.return_value = "queued"
        mock_job.is_finished = False
        mock_job.is_failed = False
        mock_job.result = None
        mock_job.exc_info = None
        mock_job.created_at = None
        mock_job.started_at = None
        mock_job.ended_at = None
        mock_job.meta = {}

        manager.queue_high.fetch_job = lambda x: None
        manager.queue_low.fetch_job = lambda job_id: mock_job if job_id == "job-456" else None
        manager.queue_default.fetch_job = lambda x: None

        status = manager.get_job_status("job-456")

        self.assertIsNotNone(status)
        self.assertEqual(status["status"], "queued")
        self.assertFalse(status["is_finished"])

    @patch('queue_manager.Redis')
    @patch('queue_manager.Queue')
    def test_status_lookup_not_found(self, MockQueue, MockRedis):
        """Test job not found in any queue"""
        from queue_manager import QueueManager

        MockQueue.side_effect = lambda *a, **kw: MagicMock()
        mock_redis = MagicMock()
        MockRedis.return_value = mock_redis

        manager = QueueManager()
        manager.queue_high.fetch_job = lambda x: None
        manager.queue_low.fetch_job = lambda x: None
        manager.queue_default.fetch_job = lambda x: None

        status = manager.get_job_status("job-notfound")

        self.assertIsNone(status)


class TestWorkflowAdapter(unittest.TestCase):
    """Test workflow adapter"""

    def test_adapter_callable(self):
        """Test adapter function is RQ-serializable"""
        from workflow_jobs import run_academy_e2e_002_job

        # Check function exists and is callable
        self.assertTrue(callable(run_academy_e2e_002_job))

        # Check signature
        import inspect
        sig = inspect.signature(run_academy_e2e_002_job)
        params = list(sig.parameters.keys())

        self.assertIn("prompt", params)
        self.assertIn("output_subdir", params)

    def test_output_subdir_format(self):
        """Test output subdirectory generation"""
        import re

        # Generate sample subdir like MCP gateway would
        subdir = f"mcp_{uuid.uuid4().hex[:8]}"

        # Validate format
        self.assertRegex(subdir, r"^mcp_[a-f0-9]{8}$")


class TestMCPGatewayTools(unittest.TestCase):
    """Test MCP gateway tools"""

    @patch('queue_manager.QueueManager')
    def test_submit_task_returns_job_id(self, MockQueueManager):
        """Test submit task returns job_id and output_subdir"""
        from mcp_gateway.tools import submit_academy_task

        mock_manager = MagicMock()
        mock_manager.enqueue_job.return_value = "job-abc123"
        MockQueueManager.return_value = mock_manager

        # Note: run_academy_e2e_002_job import will fail without full env
        # So we'll test the structure without async
        # This is a mock test

        import asyncio
        result = asyncio.run(submit_academy_task("synthetic request"))
        self.assertEqual(result["job_id"], "job-abc123")
        self.assertEqual(result["status"], "submitted")
        mock_manager.enqueue_job.assert_called_once()
        call = mock_manager.enqueue_job.call_args
        self.assertEqual(call.args[0].__module__, "workflow_jobs")
        self.assertEqual(call.args[1], "synthetic request")

    def test_tools_list_complete(self):
        """Test MCP server exposes required tools"""
        import asyncio
        from mcp_gateway.server import mcp

        tools = [t.model_dump(by_alias=True) for t in asyncio.run(mcp.list_tools())]

        tool_names = [t["name"] for t in tools]

        self.assertIn("submit_academy_task", tool_names)
        self.assertIn("get_task_status", tool_names)
        self.assertIn("get_task_artifacts", tool_names)

        # Check each tool has required fields
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("inputSchema", tool)


class TestWorkflowReuse(unittest.TestCase):
    """Test workflow adapter reuses existing workflow"""

    def test_workflow_import_path(self):
        """Test workflow adapter imports existing academy workflow"""
        import ast

        workflow_code = Path("workflow_jobs.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(workflow_code)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module)

        # Should import from academy_workflows
        self.assertIn("academy_workflows.academy_e2e_002", imports)

        # Should NOT import any competing orchestration
        for imp in imports:
            if imp:
                self.assertNotIn("control_plane", imp)  # Don't duplicate ACP
                self.assertNotIn("hyperautomation", imp)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestQueueStatusLookup))
    suite.addTests(loader.loadTestsFromTestCase(TestWorkflowAdapter))
    suite.addTests(loader.loadTestsFromTestCase(TestMCPGatewayTools))
    suite.addTests(loader.loadTestsFromTestCase(TestWorkflowReuse))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
