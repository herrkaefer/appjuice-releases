#!/usr/bin/env python3
"""Stage exact approved candidate assets; never read source or raw build diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

REQUIRED = {'packagePrivacy','publicBuildPrivacy','cleanInstall','realLogin','agentWork','updateRestore','desktopRegression'}
SYSTEMS = [{'os':'ubuntu','version':'24.04','arch':'x64'}, {'os':'debian','version':'12','arch':'arm64'}, {'os':'raspbian','version':'12','arch':'arm64'}]

def prepare(candidates, qualification, output):
    proof = json.loads(Path(qualification).read_text())
    version, sha = proof.get('version',''), proof.get('sourceCommit','')
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or not re.fullmatch('[a-f0-9]{40}',sha): raise ValueError('Invalid release identity')
    if set(proof.get('checks',{})) != REQUIRED or any(v is not True for v in proof['checks'].values()): raise ValueError('Incomplete release qualification')
    rows = proof.get('supportedSystems',[])
    if not rows or any(row not in SYSTEMS for row in rows): raise ValueError('Unqualified system row')
    root = Path(output)
    if root.exists(): raise ValueError('Use a new staging directory')
    root.mkdir(mode=0o700)
    try:
        hashes = {}; assets = {}; tools = {}
        for arch in sorted({r['arch'] for r in rows}):
            folder = Path(candidates)/arch
            metadata = json.loads((folder/('metadata-'+arch+'.json')).read_text())
            if metadata != {'schemaVersion':1,'version':version,'sourceCommit':sha,'platform':'linux','arch':arch}: raise ValueError('Candidate identity mismatch')
            names = {f'AppJuice-Linux-{arch}.tar.gz','deploy-cloud-server.sh','deploy.py','audit.py','deployment.md',f'metadata-{arch}.json'}
            if {p.name for p in folder.iterdir()} != names: raise ValueError('Unexpected candidate file')
            for name in names:
                file = folder/name
                if not file.is_file() or file.is_symlink(): raise ValueError('Invalid candidate file type')
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                if name in hashes and hashes[name] != digest: raise ValueError('Architecture-independent payloads differ')
                hashes[name]=digest
                shutil.copyfile(file,root/name)
            base='https://github.com/herrkaefer/appjuice-releases/releases/download/v'+version+'/'
            def asset(name): return {'url':base+name,'sha256':hashes[name]}
            assets[arch]={'archive':asset(f'AppJuice-Linux-{arch}.tar.gz'),'installer':asset('deploy-cloud-server.sh')}
            tools={name:asset(name) for name in ['deploy.py','audit.py','deployment.md']}
        index={'schemaVersion':1,'status':'published','version':version,'sourceCommit':sha,'supportedSystems':rows,'assets':assets,'tools':tools}
        (root/'index.json').write_text(json.dumps(index,indent=2)+'\n')
        (root/'SHA256SUMS').write_text(''.join(digest+'  '+name+'\n' for name,digest in sorted(hashes.items())))
    except BaseException:
        shutil.rmtree(root)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['candidates','qualification','output']: parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        prepare(args.candidates,args.qualification,args.output)
        print('Release assets staged from qualified candidates.')
    except Exception:
        print('Release qualification or candidate verification failed; nothing staged.')
        raise SystemExit(1)
