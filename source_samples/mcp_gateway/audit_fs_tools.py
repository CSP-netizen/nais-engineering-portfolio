"""Restricted, read-only project inspection tools for LM Studio Qwen.

Files are opened only through this module; it never invokes a shell or writes.
This is a protective filter, NOT a comprehensive secrecy/security audit.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PureWindowsPath
import re

BLOCKED_DIRS = frozenset({
    '.git', '.backups', '.venv', 'venv', '__pycache__', 'node_modules',
    'agent_workspace', 'input_zone', 'output_zone', 'db', 'vector_db',
    'masked_data', 'data', 'logs', 'secrets', 'credentials', '.ssh',
    '.aws', '.config', '.vscode', '.idea', 'dist', 'build',
})
BLOCKED_SUFFIXES = frozenset({
    '.env', '.pem', '.key', '.p12', '.pfx', '.p8', '.p7b', '.jks',
    '.kdbx', '.sqlite', '.sqlite3', '.db', '.npy', '.npz', '.parquet',
    '.pickle', '.pkl', '.zip', '.7z', '.tar', '.gz', '.csv', '.xlsx',
    '.xls', '.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.webp',
    '.gif', '.mp4', '.mov', '.mp3', '.wav', '.bin', '.exe', '.dll',
})
ALLOWED_READ_SUFFIXES = frozenset({
    '.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.jsonl', '.md',
    '.txt', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.sh', '.ps1',
    '.html', '.css', '.xml', '.svg', '.sql', '.c', '.cpp', '.h',
    '.hpp', '.rs', '.go', '.java', '.kt', '.gradle', '.dockerignore',
})
SENSITIVE_NAME = re.compile(
    r'(^|[._-])(secret|secrets|credential|credentials|password|passwd|'
    r'private[_-]?key|api[_-]?key|access[_-]?token|refresh[_-]?token)'
    r'([._-]|$)', re.I,
)
MAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])')
PHONE = re.compile(r'(?<!\d)(?:\+?82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)')
ID_NUMBER = re.compile(r'(?<!\d)\d{6}[- ]?\d{7}(?!\d)')
CREDENTIAL_ASSIGNMENT = re.compile(
    r'(?i)(?:api[_-]?key|authorization|bearer|password|passwd|secret|'
    r'private[_-]?key|access[_-]?token|refresh[_-]?token)\s*[=:]\s*[^\s,;]{4,}'
)
MAX_LIST = 120
MAX_SCAN_FILES = 1200
MAX_FILE_BYTES = 150_000
MAX_READ_CHARS = 12_000
MAX_MATCHES = 45


def _root() -> Path:
    configured = os.environ.get('HARNESS_AUDIT_ROOT', '')
    if not configured:
        raise ValueError('audit_root_not_configured')
    root = Path(configured).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('audit_root_invalid')
    return root


def _blocked_name(name: str, is_dir: bool = False) -> bool:
    lower = name.lower()
    if is_dir and (lower in BLOCKED_DIRS or lower.startswith('.') or lower in {
        'evaluation_results', 'canonical', 'index', 'derived', 'sources', 'backups', 'control-state'
    }):
        return True
    if lower.startswith('.env') or SENSITIVE_NAME.search(lower):
        return True
    if not is_dir and (Path(lower).suffix in BLOCKED_SUFFIXES or lower.endswith('~')):
        return True
    return False


def _linked(path: Path) -> bool:
    # Windows junction은 symlink 검사만으로 차단되지 않는다.
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _safe(path: str, want_dir: bool | None = None) -> Path:
    if not isinstance(path, str) or len(path) > 400 or '\x00' in path:
        raise ValueError('invalid_path')
    root = _root()
    candidate = Path(path or '.')
    if (candidate.is_absolute() or PureWindowsPath(path).drive or ':' in path
            or '..' in candidate.parts or '..' in PureWindowsPath(path).parts):
        raise PermissionError('outside_project')
    current = root
    for part in candidate.parts:
        if part in ('.', ''):
            continue
        if _blocked_name(part, is_dir=False) or _blocked_name(part, is_dir=True):
            raise PermissionError('restricted_path')
        current = current / part
        if _linked(current):
            raise PermissionError('symlink_disallowed')
    resolved = current.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise PermissionError('outside_project')
    if not resolved.exists():
        raise FileNotFoundError('not_found')
    if want_dir is True and not resolved.is_dir():
        raise ValueError('not_directory')
    if want_dir is False and not resolved.is_file():
        raise ValueError('not_file')
    return resolved


def _rel(p: Path) -> str:
    return p.relative_to(_root()).as_posix() or '.'


def _text_filter(s: str) -> str:
    lines = []
    for line in s.splitlines():
        if CREDENTIAL_ASSIGNMENT.search(line):
            lines.append('[REDACTED: possible credential assignment]')
            continue
        line = MAIL.sub('[REDACTED_EMAIL]', line)
        line = PHONE.sub('[REDACTED_PHONE]', line)
        line = ID_NUMBER.sub('[REDACTED_ID]', line)
        lines.append(line)
    return '\n'.join(lines)


def _read(p: Path) -> str:
    if p.suffix.lower() not in ALLOWED_READ_SUFFIXES and p.name.lower() not in {
        'dockerfile', '.gitignore', '.dockerignore', 'makefile', 'license'
    }:
        raise PermissionError('unsupported_text_type')
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError('file_too_large')
    raw = p.read_bytes()
    if b'\x00' in raw:
        raise ValueError('binary_data')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('non_utf8') from None


def _fail(exc: Exception) -> dict:
    if isinstance(exc, PermissionError):
        return {'status': 'denied', 'reason': str(exc)}
    if isinstance(exc, FileNotFoundError):
        return {'status': 'not_found'}
    if isinstance(exc, ValueError):
        return {'status': 'invalid', 'reason': str(exc)}
    return {'status': 'error', 'reason': 'read_failed'}


async def audit_list_files(path: str = '.', offset: str = '0', recursive: str = 'false') -> dict:
    try:
        target = _safe(path, want_dir=True)
        start = int(offset)
        if not 0 <= start <= 200_000 or recursive not in ('true', 'false'):
            raise ValueError('invalid_pagination')
        found = []
        scanned = 0
        if recursive == 'true':
            for folder, dirs, files in os.walk(target, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not _blocked_name(d, True)
                                  and not _linked(Path(folder) / d))
                for name in sorted(dirs + files):
                    child = Path(folder) / name
                    if _blocked_name(name, child.is_dir()) or _linked(child):
                        continue
                    scanned += 1
                    if scanned > MAX_SCAN_FILES:
                        break
                    found.append({'path': _rel(child), 'type': 'dir' if child.is_dir() else 'file'})
                if scanned > MAX_SCAN_FILES:
                    break
        else:
            for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                if not _blocked_name(child.name, child.is_dir()) and not _linked(child):
                    found.append({'path': _rel(child), 'type': 'dir' if child.is_dir() else 'file'})
        return {'status': 'ok', 'items': found[start:start + MAX_LIST],
                'next_offset': str(start + MAX_LIST) if len(found) > start + MAX_LIST else None,
                'truncated_scan': scanned > MAX_SCAN_FILES,
                'excluded_dirs': sorted(BLOCKED_DIRS)}
    except Exception as exc:
        return _fail(exc)


async def audit_read_file(path: str) -> dict:
    try:
        target = _safe(path, want_dir=False)
        data = _text_filter(_read(target))
        return {'status': 'ok', 'path': _rel(target),
                'text': data[:MAX_READ_CHARS],
                'truncated': len(data) > MAX_READ_CHARS,
                'warning': 'Basic redaction only; avoid personal data and secrets.'}
    except Exception as exc:
        return _fail(exc)


async def audit_search_code(pattern: str) -> dict:
    try:
        if not isinstance(pattern, str) or not 2 <= len(pattern) <= 100:
            raise ValueError('invalid_pattern')
        root = _root()
        matches = []
        scanned = 0
        stopped = False
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not _blocked_name(d, True)
                              and not _linked(Path(folder) / d))
            for filename in sorted(files):
                candidate = Path(folder) / filename
                if _blocked_name(filename) or _linked(candidate):
                    continue
                if candidate.suffix.lower() not in ALLOWED_READ_SUFFIXES:
                    continue
                scanned += 1
                if scanned > MAX_SCAN_FILES:
                    stopped = True
                    break
                try:
                    content = _read(_safe(_rel(candidate), want_dir=False))
                except (OSError, ValueError, PermissionError):
                    continue
                for lineno, line in enumerate(content.splitlines(), 1):
                    if pattern.casefold() in line.casefold():
                        matches.append({'path': _rel(candidate), 'line': lineno,
                                        'preview': _text_filter(line)[:240]})
                        if len(matches) >= MAX_MATCHES:
                            stopped = True
                            break
                if stopped:
                    break
            if stopped:
                break
        return {'status': 'ok', 'pattern': pattern, 'matches': matches,
                'scanned_files': min(scanned, MAX_SCAN_FILES),
                'truncated': stopped}
    except Exception as exc:
        return _fail(exc)


async def audit_file_info(path: str) -> dict:
    try:
        p = _safe(path)
        st = p.stat()
        result = {'status': 'ok', 'path': _rel(p),
                  'type': 'dir' if p.is_dir() else 'file',
                  'size_bytes': st.st_size, 'modified_epoch': int(st.st_mtime)}
        if p.is_file() and st.st_size < MAX_FILE_BYTES and p.suffix.lower() in ALLOWED_READ_SUFFIXES:
            result['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        return result
    except Exception as exc:
        return _fail(exc)
