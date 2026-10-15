#!/usr/bin/env python3
"""Render reviewed public note fields; private evidence is never accepted."""
import argparse
import datetime
import json
from pathlib import Path
import re

TYPES = {'new':'New', 'improved':'Improved', 'fixed':'Fixed', 'maintenance':'Maintenance'}

def render(note, version, published_at, prerelease=False):
    if set(note) != {'schemaVersion','version','items'} or note['schemaVersion'] != 1 or note['version'] != version or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid public note identity')
    if not isinstance(prerelease, bool): raise ValueError('Invalid release state')
    date = datetime.datetime.fromisoformat(published_at.replace('Z','+00:00'))
    if date.tzinfo is None: raise ValueError('Publication timestamp needs a timezone')
    items = note['items']
    if not isinstance(items,list) or not 1 <= len(items) <= 500: raise ValueError('Missing approved items')
    for item in items:
        if not isinstance(item,dict) or set(item) != {'type','text'} or item['type'] not in TYPES: raise ValueError('Non-public note fields')
        text=item['text']
        if not isinstance(text,str) or not 1 <= len(text) <= 2000 or text != text.strip() or any(x in text for x in ['\n','\r','<!--','-->']) or re.search(r'</?[a-z][^>]*>|[\u3400-\u9fff]',text,re.I):
            raise ValueError('Invalid English public text')
    lines=['# AppJuice Server '+version,'','Released: '+published_at[:10],'']
    for kind,label in TYPES.items():
        selected=[item for item in items if item['type']==kind]
        if selected:lines += ['## '+label,'']+['- '+item['text'] for item in selected]+['']
    lines += ['[View all release notes](https://appjuice.app/guide/releases/)','']
    marker={**note,'publishedAt':published_at,'prerelease':prerelease}
    lines += ['<!-- appjuice-release-notes:v1 '+json.dumps(marker,separators=(',',':'))+' -->','']
    return '\n'.join(lines)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['note','version','output']:parser.add_argument('--'+name,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--published-at');group.add_argument('--metadata')
    args=parser.parse_args()
    metadata=json.loads(Path(args.metadata).read_text()) if args.metadata else {'publishedAt':args.published_at,'isPrerelease':False}
    if args.metadata and (metadata.get('tagName')!='v'+args.version or metadata.get('isDraft') is not False):raise ValueError('Release identity/state mismatch')
    body=render(json.loads(Path(args.note).read_text()),args.version,metadata['publishedAt'],metadata['isPrerelease'])
    Path(args.output).write_text(body)
