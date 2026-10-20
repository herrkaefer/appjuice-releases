import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('website', Path(__file__).with_name('validate.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ValidationTests(unittest.TestCase):
    def test_fork_prs_excluded_and_heads_deduplicated(self):
        pulls = [{'head': {'sha': 'b'*40, 'repo': {'full_name': m.REPO}}},
                 {'head': {'sha': 'c'*40, 'repo': {'full_name': 'outsider/site'}}},
                 {'head': {'sha': 'a'*40, 'repo': {'full_name': m.REPO}}}]
        with patch.object(m, 'api', side_effect=[{'sha': 'a'*40}, pulls]):
            self.assertEqual(m.candidates('secret'), ['a'*40, 'b'*40])

    def test_completed_failure_is_not_repeated_on_schedule(self):
        self.assertFalse(m.should_run([{'context': m.CONTEXT, 'state': 'failure'}]))
        self.assertTrue(m.should_run([{'context': m.CONTEXT, 'state': 'failure'}], True))

    def test_abandoned_pending_can_recover(self):
        self.assertTrue(m.should_run([{'context': m.CONTEXT, 'state': 'pending', 'created_at': '2020-01-01T00:00:00Z'}]))

    def test_source_scripts_have_no_tokens_or_actions_command_channels(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'WEBSITE_TOKEN': 'secret', 'GITHUB_ENV': '/tmp/commands', 'GH_TOKEN': 'secret', 'ACTIONS_RUNTIME_TOKEN': 'secret'}):
            env = m.child_env(Path(d)/'source')
            self.assertFalse(any(k.startswith(('WEBSITE_', 'GITHUB_', 'ACTIONS_', 'GH_')) for k in env))
            self.assertEqual(env['HOME'], d+'/home')

if __name__ == '__main__': unittest.main()
