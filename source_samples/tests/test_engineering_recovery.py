"""격리된 합성 입력으로 게시 전 확인하는 실행·실패·파일 경계 회귀 검사."""
import ast
import asyncio
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import json
import unittest
from unittest.mock import Mock, patch

from hybrid_ai.provider import LMStudioProvider, InferenceProviderError
from mcp_gateway import audit_fs_tools as audit
from pii_masker import PIIMasker
from worker import JobWorker, counseling_job, attendance_job

ROOT = Path(__file__).resolve().parents[1]


class RecoveryTests(unittest.TestCase):
    def test_router_does_not_claim_unexecuted_success(self):
        from task_router import TaskRouter
        router = TaskRouter.__new__(TaskRouter)
        router.classifier = Mock(classify=Mock(return_value={'task_type': 'counseling'}))
        router.modules = {'counseling': 'existing-handler'}
        router.policies = {'permissions': {'counseling': {'projects': ['test'], 'domains': ['test'], 'roles': ['test']}}}
        result = router.route_task('synthetic', {'project': 'test', 'domain': 'test', 'role': 'test'})
        self.assertEqual(result['status'], 'not_implemented')

    def test_bridge_recovers_after_malformed_request(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'safe.py').write_text('safe = 42', encoding='utf-8')
            env = dict(os.environ, HARNESS_AUDIT_ROOT=d, PYTHONIOENCODING='utf-8')
            requests = 'not json\n' + json.dumps({'method': 'audit_read_file', 'params': {'path': 'safe.py'}}) + '\n'
            result = subprocess.run([sys.executable, '-B', '-m', 'mcp_gateway.monitor_bridge'],
                                    input=requests, text=True, encoding='utf-8', capture_output=True,
                                    env=env, cwd=ROOT, timeout=20)
            self.assertEqual(result.returncode, 0)
            lines = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(lines[0]['status'], 'error')
            self.assertEqual(lines[1]['text'], 'safe = 42')

    def test_agent_file_roots_use_components_not_prefixes(self):
        tree = ast.parse((ROOT / 'qwen_agent/sandbox.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_check_path_allowed')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'allowed'
            scope = {'Path': Path, 'APPROVED_READ_PATHS': [root], 'APPROVED_WRITE_PATHS': [root]}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), '<isolated-function>', 'exec'), scope)
            check = scope['_check_path_allowed']
            self.assertTrue(check(str(root / 'safe.txt'), True))
            self.assertFalse(check(str(Path(d) / 'allowed-escape' / 'file.txt'), True))
            self.assertFalse(check(str(Path(d) / 'outside.txt')))
            self.assertFalse(check(str(root / '.env')))

    def test_model_missing_does_not_use_another_model(self):
        p = LMStudioProvider()
        with patch.object(p, 'list_models', return_value={'data': [{'id': 'other-model'}]}):
            with self.assertRaises(InferenceProviderError):
                p._resolve('qwen-required')

    def test_ambiguous_model_rejected(self):
        p = LMStudioProvider()
        with patch.object(p, 'list_models', return_value={'data': [{'id': 'qwen-a'}, {'id': 'qwen-b'}]}):
            with self.assertRaises(InferenceProviderError):
                p._resolve('qwen')

    def test_worker_failure_never_writes_completed_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            worker = JobWorker.__new__(JobWorker)
            worker.output_dir = Path(d)
            for model in (None, Mock(invoke=Mock(side_effect=RuntimeError('synthetic error'))),
                          Mock(invoke=Mock(return_value=''))):
                worker.llm = model
                for method in (worker.process_counseling, worker.process_research):
                    self.assertEqual(method('synthetic input')['status'], 'failed')
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_worker_success_persists(self):
        with tempfile.TemporaryDirectory() as d:
            worker = JobWorker.__new__(JobWorker)
            worker.output_dir = Path(d)
            worker.llm = Mock(invoke=Mock(return_value='Synthetic advice'))
            self.assertEqual(worker.process_counseling('synthetic')['status'], 'completed')
            self.assertEqual(len(list(Path(d).glob('*.json'))), 1)

    def test_rq_entrypoints_raise_on_failure(self):
        with patch('worker.JobWorker') as factory:
            factory.return_value.process_counseling.return_value = {'status': 'failed'}
            factory.return_value.process_attendance.return_value = {'recorded': False}
            for f in (counseling_job, attendance_job):
                with self.assertRaises(RuntimeError):
                    f('synthetic')

    def test_service_queues_importable_functions(self):
        source = (ROOT / 'service_engine.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        values = [n.args[0].value for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == 'enqueue_job']
        self.assertEqual(values, ['worker.counseling_job', 'worker.attendance_job'])
        self.assertEqual(counseling_job.__module__, 'worker')

    def test_single_active_instruction_definition(self):
        tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8-sig'))
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name == '_job_instruction'
                             for n in tree.body), 1)

    def test_pii_address_spans_and_non_pii_preserved(self):
        for address in ('서울시 양천구 목동동 123-45', '강원도 춘천시 중앙로 10',
                        '부산광역시 해운대구', '서울시 강남구 테헤란로 123'):
            text = '주소: ' + address + '; 성적: 85/100'
            result = PIIMasker().mask(text)
            self.assertTrue(any(s['start'] <= 4 and s['end'] >= 4 + len(address)
                                for s in result.mask_spans), address)
            self.assertIn('85/100', result.masked_text)
        text = '서울 지역 과학 학습자료'
        self.assertEqual(PIIMasker().mask(text).masked_text, text)

    def test_audit_paths_redaction_and_search(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'HARNESS_AUDIT_ROOT': d}):
            root = Path(d)
            (root / 'safe.py').write_text('marker = 42\npassword = "synthetic-secret"', encoding='utf-8')
            for name in ('.secrets', '.security', '.venv-extra', 'canonical', 'evaluation_results'):
                (root / name).mkdir()
                (root / name / 'data.txt').write_text('private synthetic data')
                self.assertEqual(asyncio.run(audit.audit_read_file(name + '/data.txt'))['status'], 'denied')
            for path in ('../outside', 'C:relative.py', 'safe.py:stream', '..\\outside'):
                self.assertEqual(asyncio.run(audit.audit_read_file(path))['status'], 'denied')
            response = asyncio.run(audit.audit_read_file('safe.py'))
            self.assertNotIn('synthetic-secret', response['text'])
            self.assertEqual(len(asyncio.run(audit.audit_search_code('marker'))['matches']), 1)
            self.assertEqual(asyncio.run(audit.audit_file_info('safe.py'))['status'], 'ok')
            self.assertEqual(len(asyncio.run(audit.audit_list_files())['items']), 1)

    def test_python_execution_is_disabled_without_isolation(self):
        tree = ast.parse((ROOT / 'qwen_agent/sandbox.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SandboxPython')
        execute = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
        execute.decorator_list = []
        execute.returns = None
        for arg in execute.args.args:
            arg.annotation = None
        scope = {}
        exec(compile(ast.Module(body=[execute], type_ignores=[]), '<isolated-method>', 'exec'), scope)
        self.assertFalse(scope['execute']('raise RuntimeError("must not execute")')['success'])


if __name__ == '__main__':
    unittest.main()
