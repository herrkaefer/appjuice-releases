import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('prepare',Path(__file__).with_name('prepare-release.py'))
release=importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
class PublicationTests(unittest.TestCase):
 def fixture(self,root):
  folder=root/'candidates/x64';folder.mkdir(parents=True)
  meta={'schemaVersion':1,'version':'0.393.0','sourceCommit':'a'*40,'platform':'linux','arch':'x64'}
  (folder/'metadata-x64.json').write_text(json.dumps(meta))
  for name in ['AppJuice-Linux-x64.tar.gz','deploy-cloud-server.sh','deploy.py','audit.py','deployment.md']:(folder/name).write_text('fixture')
  proof={'version':'0.393.0','sourceCommit':'a'*40,'checks':{key:True for key in release.REQUIRED},'supportedSystems':[release.SYSTEMS[0]]}
  (root/'qualification').write_text(json.dumps(proof))
  return folder,proof
 def test_qualified_exact_allowlist_stages_release(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.fixture(root)
   release.prepare(root/'candidates',root/'qualification',root/'out')
   index=json.loads((root/'out/index.json').read_text());self.assertEqual(index['status'],'published')
   self.assertNotIn('arm64',index['assets'])
 def test_unqualified_and_unexpected_files_never_stage(self):
  for kind in ['missing-login','private-source','wrong-sha','symlink']:
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);folder,proof=self.fixture(root)
    if kind=='missing-login':proof['checks']['realLogin']=False;(root/'qualification').write_text(json.dumps(proof))
    if kind=='private-source':(folder/'source.ts').write_text('private')
    if kind=='wrong-sha':proof['sourceCommit']='b'*40;(root/'qualification').write_text(json.dumps(proof))
    if kind=='symlink':(folder/'deploy.py').unlink();(folder/'deploy.py').symlink_to('/etc/passwd')
    with self.assertRaises(ValueError):release.prepare(root/'candidates',root/'qualification',root/'out')
    self.assertFalse((root/'out').exists())
