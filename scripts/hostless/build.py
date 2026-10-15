#!/usr/bin/env python3
"""Public orchestration. Private commands never inherit public output channels."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import traceback
import urllib.request
import uuid

AGE_DIGESTS = {
    'x64': ('amd64', 'cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10'),
    'arm64': ('arm64', '6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4'),
}
GITHUB_HOST_KEY = 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n'
ALLOWED_PHASES = {'checkout', 'canary', 'native-build', 'provenance', 'encrypt'}


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def is_encrypted(file):
    with Path(file).open('rb') as stream:
        return stream.read(22) == b'age-encryption.org/v1\n'


def child_environment():
    # Do not give source code workflow-command files or Actions credentials.
    return {key: value for key, value in os.environ.items()
            if not key.startswith(('GITHUB_', 'ACTIONS_', 'HOSTLESS_SOURCE_'))
            and key not in {'GH_TOKEN', 'SSH_AUTH_SOCK'}}


class PrivateRunner:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.log = self.directory / 'build.log'
        self.phase = 'checkout'

    def run(self, phase, args, cwd=None, env=None):
        if phase not in ALLOWED_PHASES:
            raise ValueError('Unknown phase')
        self.phase = phase
        print(f'Hostless phase: {phase}', flush=True)
        with self.log.open('ab') as log:
            os.chmod(self.log, 0o600)
            subprocess.run(args, cwd=cwd, env=env or child_environment(),
                           stdout=log, stderr=subprocess.STDOUT, check=True)


def install_age(private, arch):
    machine, expected = AGE_DIGESTS[arch]
    archive = private / 'age.tar.gz'
    with urllib.request.urlopen(f'https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-{machine}.tar.gz', timeout=60) as response, archive.open('wb') as output:
        shutil.copyfileobj(response, output)
    if digest(archive) != expected:
        raise ValueError('Encryption tool checksum mismatch')
    with tarfile.open(archive) as tar:
        # Tool-only allowlist: no arbitrary archive paths or links.
        for name in ['age', 'age-keygen']:
            member = tar.getmember('age/' + name)
            if not member.isfile():
                raise ValueError('Invalid encryption tool')
            binary = private / name
            with binary.open('wb') as output:
                shutil.copyfileobj(tar.extractfile(member), output)
            binary.chmod(0o700)
    return private / 'age'


def encrypt(age, recipient, plaintext, output, runner):
    runner.run('encrypt', [str(age), '-r', recipient, '-o', str(output), str(plaintext)])
    if not is_encrypted(output):
        raise ValueError('Invalid encrypted output')


def validate_release(source, arch, sha):
    release = source / 'artifacts/linux-server-release'
    names = [f'AppJuice-Linux-{arch}.tar.gz', 'SHA256SUMS', 'hostless-release.json', 'deploy-cloud-server.sh', 'install-linux.sh']
    for name in names:
        if not (release / name).is_file() or (release / name).is_symlink():
            raise ValueError('Missing release payload')
    archive = release / names[0]
    matches = [line.split()[0] for line in (release / 'SHA256SUMS').read_text().splitlines() if line.split()[-1] == archive.name]
    if matches != [digest(archive)]:
        raise ValueError('Release checksum mismatch')
    metadata = json.loads((release / 'hostless-release.json').read_text())
    version = metadata.get('version', '')
    if (metadata.get('sourceCommit') != sha or metadata.get('sourceDirty') is not False
            or metadata.get('platform') != 'linux' or metadata.get('arch') != arch
            or not re.fullmatch(r'\d+\.\d+\.\d+', version)):
        raise ValueError('Release provenance mismatch')
    return release, names, version


def audit_public(directory, arch):
    allowed = {f'Hostless-Linux-{arch}.tar.age', f'Diagnostics-{arch}.tar.age', 'receipt.json', 'SHA256SUMS'}
    actual = {file.name for file in directory.iterdir()}
    if not actual <= allowed or not {'receipt.json', 'SHA256SUMS'} <= actual:
        raise ValueError('Unexpected public file')
    for file in directory.iterdir():
        if file.is_symlink() or not file.is_file():
            raise ValueError('Unexpected public file type')
        if file.name.endswith('.age') and not is_encrypted(file):
            raise ValueError('Plaintext in public output')
    receipt = json.loads((directory / 'receipt.json').read_text())
    if set(receipt) != {'schemaVersion', 'sourceCommit', 'arch', 'version', 'status', 'failedPhase', 'encryptedFiles'}:
        raise ValueError('Unexpected receipt field')


def main():
    os.umask(0o077)
    public = Path('encrypted-output').resolve()
    public.mkdir(exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix='appjuice-confidential-', dir=os.environ['RUNNER_TEMP']))
    runner = PrivateRunner(private / 'diagnostics')
    age = None
    success = False
    candidate = Path('release-output').resolve()
    publishable = os.environ.get('HOSTLESS_RELEASE_CANDIDATE') == '1'
    version = None
    sha = os.environ.get('HOSTLESS_SOURCE_SHA', '')
    arch = os.environ.get('HOSTLESS_ARCH', '')
    recipient = os.environ.get('HOSTLESS_AGE_RECIPIENT', '')
    try:
        if not re.fullmatch(r'[a-f0-9]{40}', sha) or arch not in AGE_DIGESTS or not re.fullmatch(r'age1[a-z0-9]{58}', recipient):
            raise ValueError('Invalid build configuration')
        if platform.system() != 'Linux' or platform.machine() != {'x64': 'x86_64', 'arm64': 'aarch64'}[arch]:
            raise ValueError('Native runner required')
        age = install_age(private, arch)
        canaries = {'stdout': 'PRIVATE_STDOUT_' + uuid.uuid4().hex, 'stderr': 'PRIVATE_STDERR_' + uuid.uuid4().hex}
        (runner.directory / 'canaries.json').write_text(json.dumps(canaries))
        runner.run('canary', [sys.executable, '-c', 'import sys;print(sys.argv[1]);print("::error::"+sys.argv[2],file=sys.stderr)', *canaries.values()])
        key = private / 'source-key'
        key.write_text(os.environ.pop('HOSTLESS_SOURCE_SSH_KEY').rstrip() + '\n')
        key.chmod(0o600)
        hosts = private / 'known_hosts'
        hosts.write_text(GITHUB_HOST_KEY)
        source = private / 'source'
        env = child_environment()
        env['GIT_SSH_COMMAND'] = f'ssh -i {key} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile={hosts}'
        try:
            runner.run('checkout', ['git', 'init', '-q', str(source)], env=env)
            runner.run('checkout', ['git', '-C', str(source), 'remote', 'add', 'origin', 'git@github.com:herrkaefer/appjuice.git'], env=env)
            runner.run('checkout', ['git', '-C', str(source), 'fetch', '--quiet', 'origin', 'master'], env=env)
            runner.run('checkout', ['git', '-C', str(source), 'merge-base', '--is-ancestor', sha, 'origin/master'], env=env)
            runner.run('checkout', ['git', '-C', str(source), 'checkout', '--quiet', '--detach', sha], env=env)
        finally:
            key.unlink(missing_ok=True)
        env = child_environment()
        env['HOSTLESS_ARCH'] = arch
        env['HOSTLESS_TEST_AGE'] = str(age)
        env['HOSTLESS_WRAPPER_SCRIPTS'] = str(Path(__file__).resolve().parent)
        env['APPJUICE_BUNDLE_OFFLINE'] = '0'
        runner.run('native-build', ['bash', str(Path(__file__).with_name('native-build.sh').resolve())], cwd=source, env=env)
        runner.phase = 'provenance'
        release, names, version = validate_release(source, arch, sha)
        inner = private / 'release.tar'
        with tarfile.open(inner, 'w') as tar:
            for name in names:
                tar.add(release / name, arcname=name, recursive=False)
        encrypt(age, recipient, inner, public / f'Hostless-Linux-{arch}.tar.age', runner)
        if publishable:
            # Source-owned audit runs with private output capture before any plaintext copy.
            runner.run('provenance', [sys.executable, str(source / 'scripts/hostless/audit.py'), str(release / names[0])])
            candidate.mkdir(exist_ok=False)
            for name in [names[0], 'deploy-cloud-server.sh']:
                shutil.copyfile(release / name, candidate / name)
            for name in ['deploy.py', 'audit.py']:
                shutil.copyfile(source / 'scripts/hostless' / name, candidate / name)
            shutil.copyfile(source / 'docs/linux-server-deployment.md', candidate / 'deployment.md')
            approved = {key: json.loads((release / 'hostless-release.json').read_text())[key]
                        for key in ['schemaVersion', 'version', 'sourceCommit', 'arch', 'platform']}
            (candidate / ('metadata-' + arch + '.json')).write_text(json.dumps(approved))
            allowed = {names[0], 'deploy-cloud-server.sh', 'deploy.py', 'audit.py', 'deployment.md', 'metadata-' + arch + '.json'}
            if {p.name for p in candidate.iterdir()} != allowed or any(p.is_symlink() or not p.is_file() for p in candidate.iterdir()):
                raise ValueError('Unexpected release output')
        success = True
    except BaseException:
        try:
            with runner.log.open('a') as log:
                traceback.print_exc(file=log)
        except BaseException:
            # A full disk or log-write failure must not send a traceback to Actions.
            pass
        print('Hostless build did not complete; raw diagnostics remain confidential.', flush=True)
    finally:
        failed_phase = None if success else runner.phase
        try:
            if age:
                diagnostics = private / 'diagnostics.tar'
                with tarfile.open(diagnostics, 'w') as tar:
                    tar.add(runner.directory, arcname='diagnostics')
                encrypt(age, recipient, diagnostics, public / f'Diagnostics-{arch}.tar.age', runner)
                encrypted = sorted(file.name for file in public.glob('*.age'))
                receipt = {'schemaVersion': 1, 'sourceCommit': sha, 'arch': arch, 'version': version,
                           'status': 'success' if success else 'failure', 'failedPhase': failed_phase, 'encryptedFiles': encrypted}
                (public / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
                (public / 'SHA256SUMS').write_text(''.join(digest(public / name) + '  ' + name + '\n' for name in encrypted))
                audit_public(public, arch)
            else:
                success = False
        except BaseException:
            # Fail closed: even partial ciphertext or unsafe receipts aren't published.
            success = False
            shutil.rmtree(public)
            public.mkdir()
            print('Encrypted output preparation failed; no files will be uploaded.', flush=True)
        try:
            shutil.rmtree(private)
        except BaseException:
            success = False
            print('Confidential workspace cleanup failed; ephemeral runner teardown is required.', flush=True)
    if not success and candidate.exists():
        shutil.rmtree(candidate)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
