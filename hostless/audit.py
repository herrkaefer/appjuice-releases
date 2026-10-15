#!/usr/bin/env python3
"""Bounded, non-extracting inspection of distribution trees and nested archives."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

LIMIT = 8 * 1024 * 1024 * 1024
class AuditError(ValueError):
    pass

class Audit:
    def __init__(self):
        self.files = 0
        self.bytes = 0

    def name(self, name):
        path = PurePosixPath(name)
        parts = path.parts
        if path.is_absolute() or '..' in parts or '\\' in name:
            raise AuditError('Unsafe package path')
        # Seed Apps/templates deliberately remain editable source packages.
        if '.git' in parts or '.env' in parts or any(x in parts for x in ('plans', 'coverage')):
            raise AuditError('Private repository content')
        if re.search(r'packages/(platform|app-runtime|frontend)/(src|test)(/|$)', name):
            raise AuditError('Private implementation source')
        if name.endswith(('.map', '.d.ts', '.d.cts', '.d.mts')):
            raise AuditError('Source/debug metadata')
        if re.search(r'(^|/)scripts/.*\.(ts|tsx)$', name):
            raise AuditError('Original platform script')

    def content(self, name, data, depth=0):
        self.name(name)
        self.files += 1
        self.bytes += len(data)
        if self.files > 200000 or self.bytes > LIMIT or depth > 5:
            raise AuditError('Package inspection budget exceeded')
        if name.endswith(('.js', '.mjs', '.cjs', '.html', '.json')) and not any(p in PurePosixPath(name).parts for p in ('node_modules', 'vendor')):
            if re.search(rb'(?:^|\n)\s*//[#@]\s*sourceMappingURL\s*=\s*data:', data):
                raise AuditError('Embedded original source map')
        if name.endswith('.json'):
            try:
                obj = json.loads(data)
                if isinstance(obj, dict) and 'sourcesContent' in obj and 'mappings' in obj:
                    raise AuditError('Embedded original source map')
            except (ValueError, UnicodeDecodeError) as error:
                if isinstance(error, AuditError): raise
        stream = io.BytesIO(data)
        if name.endswith('.zip'):
            with zipfile.ZipFile(stream) as archive:
                for item in archive.infolist():
                    self.name(item.filename)
                    if item.file_size + self.bytes > LIMIT:
                        raise AuditError('Archive inspection budget exceeded')
                    if (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise AuditError('Nested ZIP symlink')
                    if not item.is_dir():
                        self.content(item.filename, archive.read(item), depth + 1)
        elif name.endswith(('.tar.gz', '.tgz', '.tar')):
            with tarfile.open(fileobj=stream, mode='r:*') as archive:
                for item in archive:
                    self.name(item.name)
                    if item.issym() or item.islnk():
                        # Resolve links lexically inside this archive, never follow them.
                        base = PurePosixPath(item.name).parent if item.issym() else PurePosixPath('.')
                        level = 0
                        if PurePosixPath(item.linkname).is_absolute():
                            raise AuditError('Absolute archive link')
                        for part in (base / item.linkname).parts:
                            level += -1 if part == '..' else 0 if part == '.' else 1
                            if level < 0:
                                raise AuditError('Escaping archive link')
                        self.name(str(base / item.linkname).replace('../', ''))
                    elif item.isfile():
                        if item.size + self.bytes > LIMIT:
                            raise AuditError('Archive inspection budget exceeded')
                        self.content(item.name, archive.extractfile(item).read(), depth + 1)
                    elif not item.isdir():
                        raise AuditError('Special archive member')

    def run(self, target):
        target = Path(target)
        if target.is_dir():
            for item in target.rglob('*'):
                self.name(item.relative_to(target).as_posix())
                if item.is_symlink():
                    try:
                        resolved = item.resolve(strict=True)
                    except (OSError, RuntimeError):
                        raise AuditError('Invalid installed link')
                    if target.resolve() not in resolved.parents:
                        raise AuditError('Escaping installed link')
                elif item.is_file():
                    if item.stat().st_size + self.bytes > LIMIT:
                        raise AuditError('Package inspection budget exceeded')
                    self.content(item.relative_to(target).as_posix(), item.read_bytes())
        else:
            self.content(target.name, target.read_bytes())
        return {'status': 'ready', 'files': self.files, 'inspectedBytes': self.bytes}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target')
    args = parser.parse_args()
    try:
        print(json.dumps(Audit().run(args.target)))
    except Exception:
        print(json.dumps({'status': 'failed', 'reason': 'Package confidentiality inspection failed'}))
        raise SystemExit(1)
