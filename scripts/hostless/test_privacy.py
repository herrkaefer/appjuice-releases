import contextlib
import importlib.util
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('hostless_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class PrivacyTests(unittest.TestCase):
    def test_interruption_encryption_cleanup_and_unexpected_output_fail_closed(self):
        for failure in ['interrupt', 'encryption', 'cleanup', 'unexpected-output']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                previous = Path.cwd()
                real_remove, real_copy = shutil.rmtree, shutil.copyfile
                output = io.StringIO()
                encryptions = 0

                def run(runner, phase, args, cwd=None, env=None):
                    runner.phase = phase
                    runner.log.write_text('PRIVATE_FAILURE_CANARY\n')
                    if phase == 'native-build':
                        if failure == 'interrupt':
                            raise KeyboardInterrupt('PRIVATE_FAILURE_CANARY')
                        source = Path(cwd)
                        release = source / 'artifacts/linux-server-release'
                        release.mkdir(parents=True)
                        for name in ['AppJuice-Linux-x64.tar.gz', 'deploy-cloud-server.sh', 'install-linux.sh']:
                            (release/name).write_text('audited fixture')
                        (release/'SHA256SUMS').write_text(build.digest(release/'AppJuice-Linux-x64.tar.gz')+'  AppJuice-Linux-x64.tar.gz\n')
                        (release/'hostless-release.json').write_text(json.dumps({'schemaVersion':1,'sourceCommit':'a'*40,'sourceDirty':False,'arch':'x64','platform':'linux','version':'0.1.0'}))
                        for name in ['scripts/hostless/deploy.py', 'scripts/hostless/audit.py', 'docs/linux-server-deployment.md']:
                            target = source/name
                            target.parent.mkdir(parents=True,exist_ok=True)
                            target.write_text('reviewed public fixture')

                def encrypt(age, recipient, plaintext, target, runner):
                    nonlocal encryptions
                    encryptions += 1
                    target.write_bytes(b'age-encryption.org/v1\nfixture')
                    if failure == 'encryption' and encryptions == 2:
                        raise RuntimeError('PRIVATE_FAILURE_CANARY')

                def remove(target, *args, **kwargs):
                    if failure == 'cleanup' and Path(target).name.startswith('appjuice-confidential-'):
                        raise OSError('PRIVATE_FAILURE_CANARY')
                    return real_remove(target,*args,**kwargs)

                def copy(source, target, *args, **kwargs):
                    result = real_copy(source,target,*args,**kwargs)
                    if failure == 'unexpected-output' and Path(target).parent.name == 'release-output':
                        (Path(target).parent/'source.ts').write_text('PRIVATE_FAILURE_CANARY')
                    return result

                try:
                    os.chdir(root)
                    environment = {'RUNNER_TEMP':str(root),'HOSTLESS_SOURCE_SHA':'a'*40,'HOSTLESS_ARCH':'x64','HOSTLESS_AGE_RECIPIENT':'age1'+'a'*58,'HOSTLESS_SOURCE_SSH_KEY':'fixture','HOSTLESS_RELEASE_CANDIDATE':'1'}
                    with patch.dict(os.environ,environment), patch.object(build.platform,'system',return_value='Linux'), patch.object(build.platform,'machine',return_value='x86_64'), patch.object(build,'install_age',return_value=root/'age'), patch.object(build.PrivateRunner,'run',run), patch.object(build,'encrypt',encrypt), patch.object(build.shutil,'rmtree',remove), patch.object(build.shutil,'copyfile',copy), contextlib.redirect_stdout(output):
                        self.assertEqual(build.main(),1)
                    self.assertNotIn('PRIVATE_FAILURE_CANARY',output.getvalue())
                    self.assertFalse((root/'release-output').exists())
                    if failure == 'encryption':
                        self.assertEqual(list((root/'encrypted-output').iterdir()),[])
                    else:
                        build.audit_public(root/'encrypted-output','x64')
                finally:
                    os.chdir(previous)

    def test_private_stdout_stderr_and_workflow_commands_are_not_forwarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = build.PrivateRunner(Path(temporary) / 'private')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                runner.run('canary', ['python3', '-c', 'import sys;print("PRIVATE_SOURCE_LINE");print("::error::PRIVATE_SECRET",file=sys.stderr)'])
            self.assertNotIn('PRIVATE_SOURCE_LINE', output.getvalue())
            self.assertNotIn('PRIVATE_SECRET', output.getvalue())
            self.assertIn('PRIVATE_SOURCE_LINE', runner.log.read_text())
            self.assertIn('::error::PRIVATE_SECRET', runner.log.read_text())
            self.assertEqual(runner.log.stat().st_mode & 0o777, 0o600)

    def test_private_children_cannot_inherit_workflow_channels_and_credentials(self):
        with patch.dict(os.environ, {'GITHUB_OUTPUT': 'secret-channel', 'GITHUB_TOKEN': 'credential', 'ACTIONS_RUNTIME_TOKEN': 'credential', 'HOSTLESS_SOURCE_SSH_KEY': 'credential', 'GH_TOKEN': 'credential'}):
            child = build.child_environment()
            for key in ['GITHUB_OUTPUT', 'GITHUB_TOKEN', 'ACTIONS_RUNTIME_TOKEN', 'HOSTLESS_SOURCE_SSH_KEY', 'GH_TOKEN']:
                self.assertNotIn(key, child)

    def test_phase_name_cannot_inject_private_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = build.PrivateRunner(temporary)
            with self.assertRaises(ValueError):
                runner.run('private-source-content', ['true'])

    def test_public_output_rejects_plaintext_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'source.ts').write_text('confidential')
            with self.assertRaises(ValueError):
                build.audit_public(root, 'x64')
            (root / 'source.ts').unlink()
            (root / 'receipt.json').symlink_to('/etc/passwd')
            (root / 'SHA256SUMS').write_text('')
            with self.assertRaises(ValueError):
                build.audit_public(root, 'x64')

    def test_stale_or_dirty_release_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            release = source / 'artifacts/linux-server-release'
            release.mkdir(parents=True)
            for name in ['AppJuice-Linux-x64.tar.gz', 'deploy-cloud-server.sh', 'install-linux.sh']:
                (release / name).write_text('fixture')
            (release / 'SHA256SUMS').write_text(build.digest(release / 'AppJuice-Linux-x64.tar.gz') + '  AppJuice-Linux-x64.tar.gz\n')
            (release / 'hostless-release.json').write_text(json.dumps({'sourceCommit': 'a' * 40, 'sourceDirty': True, 'arch': 'x64', 'platform': 'linux', 'version': '0.1.0'}))
            with self.assertRaises(ValueError):
                build.validate_release(source, 'x64', 'a' * 40)

    @unittest.skipUnless(os.environ.get('HOSTLESS_TEST_AGE'), 'Set HOSTLESS_TEST_AGE to test real encryption')
    def test_failed_checkout_diagnostics_are_encrypted_and_wrong_key_cannot_read_them(self):
        age = Path(os.environ['HOSTLESS_TEST_AGE'])
        keygen = age.with_name('age-keygen')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ['identity', 'wrong']:
                subprocess.run([str(keygen), '-o', str(root / name)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            recipient = subprocess.check_output([str(keygen), '-y', str(root / 'identity')], text=True).strip()
            previous = Path.cwd()
            try:
                os.chdir(root)
                environment = {'RUNNER_TEMP': str(root), 'HOSTLESS_SOURCE_SHA': 'a' * 40, 'HOSTLESS_ARCH': 'x64', 'HOSTLESS_AGE_RECIPIENT': recipient, 'HOSTLESS_SOURCE_SSH_KEY': 'fixture-key'}
                real_run = build.PrivateRunner.run

                def fail_checkout(self, phase, args, **kwargs):
                    if phase == 'checkout':
                        raise RuntimeError('CONFIDENTIAL_ERROR_SOURCE')
                    return real_run(self, phase, args, **kwargs)

                output = io.StringIO()
                with patch.dict(os.environ, environment), patch.object(build.platform, 'system', return_value='Linux'), patch.object(build.platform, 'machine', return_value='x86_64'), patch.object(build, 'install_age', return_value=age), patch.object(build.PrivateRunner, 'run', fail_checkout), contextlib.redirect_stdout(output):
                    self.assertEqual(build.main(), 1)
                self.assertNotIn('CONFIDENTIAL_ERROR_SOURCE', output.getvalue())
                public = root / 'encrypted-output'
                build.audit_public(public, 'x64')
                ciphertext = public / 'Diagnostics-x64.tar.age'
                wrong = subprocess.run([str(age), '-d', '-i', str(root / 'wrong'), str(ciphertext)], capture_output=True)
                self.assertNotEqual(wrong.returncode, 0)
                self.assertFalse(wrong.stdout)
                plaintext = root / 'diagnostics.tar'
                subprocess.run([str(age), '-d', '-i', str(root / 'identity'), '-o', str(plaintext), str(ciphertext)], check=True)
                with tarfile.open(plaintext) as tar:
                    log = tar.extractfile('diagnostics/build.log').read()
                    self.assertIn(b'CONFIDENTIAL_ERROR_SOURCE', log)
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
