#!/usr/bin/env python3
"""Operator-side verification. The identity is never needed by Actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--arch', choices=['x64', 'arm64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--age', default='age')
    parser.add_argument('--public-log', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    assert re.fullmatch(r'[a-f0-9]{40}', args.source_sha)
    receipt = json.loads((args.artifact / 'receipt.json').read_text())
    assert receipt['sourceCommit'] == args.source_sha and receipt['arch'] == args.arch
    assert receipt['status'] in ['success', 'failure']
    names = {f'Diagnostics-{args.arch}.tar.age'}
    if receipt['status'] == 'success':
        names.add(f'Hostless-Linux-{args.arch}.tar.age')
    assert set(receipt['encryptedFiles']) == names
    assert {p.name for p in args.artifact.iterdir()} == names | {'receipt.json', 'SHA256SUMS'}
    checksums = dict(line.split()[::-1] for line in (args.artifact / 'SHA256SUMS').read_text().splitlines())
    assert set(checksums) == names
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in sorted(names):
        ciphertext = args.artifact / name
        assert not ciphertext.is_symlink() and digest(ciphertext) == checksums[name]
        plaintext = args.output / name.removesuffix('.age')
        # Never forward decrypted diagnostics to a public output channel.
        subprocess.run([args.age, '-d', '-i', str(args.identity), '-o', str(plaintext), str(ciphertext)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with tarfile.open(plaintext) as tar:
            if name.startswith('Hostless-'):
                expected = {f'AppJuice-Linux-{args.arch}.tar.gz', 'SHA256SUMS', 'hostless-release.json', 'deploy-cloud-server.sh', 'install-linux.sh'}
                assert set(tar.getnames()) == expected
                destination = args.output / 'release'
            else:
                assert set(tar.getnames()) == {'diagnostics', 'diagnostics/build.log', 'diagnostics/canaries.json'}
                destination = args.output
            for member in tar.getmembers():
                assert member.isfile() or member.isdir()
            tar.extractall(destination, filter='data')
    canaries = json.loads((args.output / 'diagnostics/canaries.json').read_text())
    private_log = (args.output / 'diagnostics/build.log').read_text()
    for value in canaries.values():
        assert value in private_log
        if args.public_log:
            assert value not in args.public_log.read_text()
    if receipt['status'] == 'success':
        release = args.output / 'release'
        metadata = json.loads((release / 'hostless-release.json').read_text())
        assert metadata['sourceCommit'] == args.source_sha and metadata['sourceDirty'] is False
        assert metadata['platform'] == 'linux' and metadata['arch'] == args.arch and metadata['version'] == receipt['version']
        archive = release / f'AppJuice-Linux-{args.arch}.tar.gz'
        matches = [line.split()[0] for line in (release / 'SHA256SUMS').read_text().splitlines() if line.split()[-1] == archive.name]
        assert matches == [digest(archive)]
        # Inspect without running binaries or installing anything on the operator.
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            root = f'appjuice-{metadata["version"]}-linux-{args.arch}'
            for member in members:
                assert member.name.split('/')[0] == root
                tarfile.data_filter(member, args.output / 'archive-audit')
                relative = member.name.removeprefix(root + '/')
                assert '.git' not in Path(relative).parts
                assert not relative.endswith('.map')
                for package in ['platform', 'app-runtime', 'frontend']:
                    assert not relative.startswith(f'packages/{package}/src/')
            embedded = json.load(tar.extractfile(root + '/hostless-release.json'))
            for key in ['sourceCommit', 'sourceDirty', 'platform', 'arch', 'version']:
                assert embedded[key] == metadata[key]
    print(json.dumps({'verified': True, 'arch': args.arch, 'status': receipt['status'], 'version': receipt['version'], 'sourceCommit': args.source_sha, 'logCanariesConfidential': bool(args.public_log)}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Encrypted Hostless verification failed; no private diagnostics printed.')
