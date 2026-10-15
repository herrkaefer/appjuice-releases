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

note_spec=importlib.util.spec_from_file_location('render_note',Path(__file__).with_name('render-note.py'))
notes=importlib.util.module_from_spec(note_spec);note_spec.loader.exec_module(notes)
class PublicNoteTests(unittest.TestCase):
 def test_release_marker_contains_actual_date_and_only_reviewed_fields(self):
  note={'schemaVersion':1,'version':'0.393.0','items':[{'type':'new','text':'Deploy verified Linux packages.'}]}
  body=notes.render(note,'0.393.0','2026-10-15T18:00:00Z')
  marker=json.loads(body.split('<!-- appjuice-release-notes:v1 ')[1].split(' -->')[0])
  self.assertEqual(marker,{**note,'publishedAt':'2026-10-15T18:00:00Z','prerelease':False})
  self.assertNotIn('evidence',body)
 def test_private_evidence_wrong_version_and_invalid_date_refused(self):
  note={'schemaVersion':1,'version':'0.393.0','items':[{'type':'new','text':'Deploy verified Linux packages.'}]}
  for kind in ['evidence','version','date','html']:
   with self.subTest(kind=kind):
    value=json.loads(json.dumps(note));version='0.393.0';date='2026-10-15T18:00:00Z'
    if kind=='evidence':value['items'][0]['evidence']=['private/path']
    if kind=='version':version='0.392.0'
    if kind=='date':date='2026-10-15'
    if kind=='html':value['items'][0]['text']='<script>private</script>'
    with self.assertRaises(ValueError):notes.render(value,version,date)
