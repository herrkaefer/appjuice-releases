#!/usr/bin/env python3
"""Agent-facing Linux service deployment. Standard library only; no private source needed."""
import argparse
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from audit import Audit

OFFICIAL = 'https://github.com/herrkaefer/appjuice-releases/releases/download/'
INDEX = 'https://raw.githubusercontent.com/herrkaefer/appjuice-releases/main/hostless/index.json'
class Stop(Exception):
    def __init__(self, status, action):
        self.status, self.action = status, action

def stop(status, action): raise Stop(status, action)
def capture(args):
    try: return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True, timeout=15).strip()
    except (OSError, subprocess.SubprocessError): return ''
def read_os(file='/etc/os-release'):
    try: return dict(line.split('=', 1) for line in Path(file).read_text().replace('"', '').splitlines() if '=' in line)
    except OSError: return {}
def inspect():
    info = read_os()
    machine = platform.machine()
    arch = {'x86_64':'x64', 'aarch64':'arm64'}.get(machine)
    bits = capture(['getconf', 'LONG_BIT'])
    libc = capture(['getconf', 'GNU_LIBC_VERSION'])
    supported = (platform.system() == 'Linux' and bits == '64' and
        ((arch == 'x64' and info.get('ID') == 'ubuntu' and info.get('VERSION_ID') == '24.04') or
         (arch == 'arm64' and info.get('ID') in ('debian', 'raspbian') and info.get('VERSION_ID') == '12')))
    return {'status': 'ready' if supported else 'unsupported', 'arch': arch, 'userlandBits': bits,
        'os': info.get('ID'), 'osVersion': info.get('VERSION_ID'), 'libc': libc,
        'systemd': Path('/run/systemd/system').is_dir(), 'freeBytes': shutil.disk_usage('/').free,
        'installed': Path('/opt/appjuice/current').exists(),
        'cloudflared': bool(shutil.which('cloudflared')),
        'safeExtraction': hasattr(__import__('tarfile'), 'data_filter')}

def protected_read(file):
    path = Path(file)
    if path.is_symlink(): stop('conflict', 'Secret/state file must not be a symlink.')
    mode = path.stat()
    if mode.st_uid != os.geteuid() or mode.st_mode & 0o077:
        stop('needs-user-action', 'Make the secret/state file owned by this user with mode 0600.')
    return path.read_text().strip()

def save(file, value):
    file = Path(file)
    if file.is_symlink(): stop('conflict', 'Refuse symlink configuration/state file.')
    file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=file.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, file)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def spec_read(path):
    spec = json.loads(Path(path).read_text())
    required = ['hostname', 'adminEmail', 'issuer', 'accountId', 'zoneId']
    if any(not isinstance(spec.get(key), str) for key in required):
        stop('needs-user-action', 'Supply hostname, adminEmail, issuer, accountId and zoneId in the deployment specification.')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', spec['hostname']) or '.' not in spec['hostname']:
        stop('failed', 'Invalid hostname.')
    if not re.fullmatch(r'[^\s@=]+@[^\s@=]+\.[^\s@=]+', spec['adminEmail']): stop('failed', 'Invalid administrator email.')
    if not re.fullmatch(r'https://[a-z0-9-]+\.cloudflareaccess\.com', spec['issuer']): stop('failed', 'Invalid Access team issuer.')
    if any(not re.fullmatch(r'[a-f0-9]{32}', spec[key]) for key in ['accountId', 'zoneId']): stop('failed', 'Invalid Cloudflare account/zone ID.')
    if 'allowTaskInterruption' in spec and not isinstance(spec['allowTaskInterruption'], bool):
        stop('failed', 'allowTaskInterruption must be a boolean.')
    return spec

class Cloudflare:
    def __init__(self, token): self.token = token
    def api(self, route, method='GET', body=None):
        if not route.startswith(('/accounts/', '/zones/')) or '..' in route: stop('failed', 'Invalid resource route.')
        request = urllib.request.Request('https://api.cloudflare.com/client/v4' + route,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization':'Bearer ' + self.token, 'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response: result = json.load(response)
        except (urllib.error.URLError, ValueError): stop('needs-user-action', 'Cloudflare request failed. Check scoped token permissions and network; resume afterward.')
        if result.get('success') is not True: stop('needs-user-action', 'Cloudflare did not confirm the operation. Check permissions; resume afterward.')
        return result['result']

def configure(cf, spec, state, persist):
    account = '/accounts/' + spec['accountId']
    zone = '/zones/' + spec['zoneId']
    origin = 'https://' + spec['hostname']
    def remember(key, value):
        state[key] = value
        persist()
    zone_info = cf.api(zone)
    if zone_info['account']['id'] != spec['accountId'] or not (spec['hostname'].endswith('.' + zone_info['name'])):
        stop('conflict', 'Hostname/zone/account do not match.')
    def listing(route):
        result = []
        for page in range(1, 101):
            items = cf.api(route + ('&' if '?' in route else '?') + 'per_page=100&page=' + str(page))
            result.extend(items)
            if len(items) < 100: return result
        stop('conflict', 'Too many resources for safe discovery.')
    # Discover incomplete API effects by the persisted deployment-specific name.
    name = 'AppJuice-' + state['deploymentId']
    policies = listing(account + '/access/policies')
    policies = [p for p in policies if p['name'] == name]
    if len(policies) > 1: stop('conflict', 'Multiple deployment policies found.')
    if 'policyId' not in state:
        p = policies[0] if policies else cf.api(account + '/access/policies', 'POST',
            {'name':name, 'decision':'allow', 'include':[{'email':{'email':spec['adminEmail'].lower()}}]})
        remember('policyId', p['id'])
    policy = cf.api(account + '/access/policies/' + state['policyId'])
    if policy.get('name') != name or policy.get('decision') != 'allow' or policy.get('app_count', 0) > 1:
        stop('conflict', 'Access policy is shared or belongs to another deployment.')
    apps = listing(account + '/access/apps')
    apps = [a for a in apps if a.get('domain') == spec['hostname']]
    if len(apps) > 1: stop('conflict', 'Multiple Access applications match this hostname.')
    if 'appId' not in state:
        if apps and apps[0].get('name') != name: stop('conflict', 'Hostname already has an independently managed Access application.')
        app = apps[0] if apps else cf.api(account + '/access/apps', 'POST',
            {'name':name, 'domain':spec['hostname'], 'type':'self_hosted', 'session_duration':'24h',
             'policies':[{'id':state['policyId'], 'precedence':1}]})
        remember('appId', app['id'])
    app = cf.api(account + '/access/apps/' + state['appId'])
    if app.get('domain') != spec['hostname'] or app.get('name') != name or not any(p.get('id') == state['policyId'] for p in app.get('policies', [])):
        stop('conflict', 'Access application/policy association changed.')
    remember('audience', app['aud'])
    providers = cf.api(account + '/access/identity_providers')
    if not any(p.get('type') == 'onetimepin' for p in providers):
        stop('needs-user-action', 'Enable One-time PIN or your selected human identity provider in Cloudflare Access, then resume.')
    tunnels = listing(account + '/cfd_tunnel?is_deleted=false&name=' + name)
    tunnels = [t for t in tunnels if t['name'] == name]
    if len(tunnels) > 1: stop('conflict', 'Multiple deployment tunnels found.')
    if 'tunnelId' not in state:
        tunnel = tunnels[0] if tunnels else cf.api(account + '/cfd_tunnel', 'POST', {'name':name, 'config_src':'cloudflare'})
        remember('tunnelId', tunnel['id'])
    tunnel = cf.api(account + '/cfd_tunnel/' + state['tunnelId'])
    if tunnel.get('name') != name: stop('conflict', 'Tunnel ownership changed.')
    cf.api(account + '/cfd_tunnel/' + state['tunnelId'] + '/configurations', 'PUT',
        {'config':{'ingress':[{'hostname':spec['hostname'], 'service':'http://127.0.0.1:8787'}, {'service':'http_status:404'}]}})
    records = listing(zone + '/dns_records?name=' + spec['hostname'])
    target = state['tunnelId'] + '.cfargotunnel.com'
    if any(r.get('type') != 'CNAME' or r.get('content') != target or not r.get('proxied') for r in records):
        stop('conflict', 'Existing DNS record does not match this deployment tunnel.')
    if not records:
        record = cf.api(zone + '/dns_records', 'POST', {'type':'CNAME', 'name':spec['hostname'], 'content':target, 'proxied':True})
        remember('dnsId', record['id'])
    token = cf.api(account + '/cfd_tunnel/' + state['tunnelId'] + '/token')
    return token

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as response: return json.load(response)

def select_release(index, arch):
    if index.get('schemaVersion') != 1 or index.get('status') != 'published':
        stop('needs-user-action', 'No qualified public Hostless release is available. Do not use desktop latest or operator ciphertext.')
    version = index.get('version', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version): stop('failed', 'Invalid server release version.')
    artifact = index.get('assets', {}).get(arch, {})
    for name in ['archive', 'installer']:
        item = artifact.get(name, {})
        if not re.fullmatch(re.escape(OFFICIAL + 'v' + version + '/') + r'[A-Za-z0-9._-]+', item.get('url', '')) or not re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')):
            stop('failed', 'Invalid official artifact URL or checksum.')
    return version, artifact

def command(args, log):
    if Path(log).is_symlink(): stop('conflict', 'Operations log must not be a symlink.')
    with open(log, 'ab') as output:
        os.chmod(log, 0o600)
        subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect', 'plan', 'configure', 'install', 'verify'])
    parser.add_argument('--spec')
    parser.add_argument('--state', default='/var/lib/appjuice-deploy/state.json')
    parser.add_argument('--index', default=INDEX)
    args = parser.parse_args()
    report = inspect()
    if args.action == 'inspect': return report
    if report['status'] != 'ready' or not report['systemd']:
        stop('unsupported', 'Use a supported 64-bit Linux/systemd target; see the deployment guide.')
    if not args.spec: stop('needs-user-action', 'Provide --spec with the deployment inputs described in the guide.')
    spec = spec_read(args.spec)
    index = fetch_json(args.index)
    version, assets = select_release(index, report['arch'])
    row = {'os':report['os'], 'version':report['osVersion'], 'arch':report['arch']}
    if row not in index.get('supportedSystems', []):
        stop('unsupported', 'This OS/architecture has not passed this release qualification.')
    if args.action == 'plan': return {**report, 'version':version, 'hostname':spec['hostname'], 'next':'configure; install; verify'}
    if os.geteuid() != 0: stop('needs-user-action', 'Run mutation/verification steps with authorized sudo access.')
    import fcntl
    state_path = Path(args.state)
    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_info = state_path.parent.stat()
    if parent_info.st_uid != 0 or parent_info.st_mode & 0o077:
        stop('conflict', 'Deployment state directory must be root-owned with mode 0700.')
    if state_path.parent.is_symlink(): stop('conflict', 'Deployment state directory must not be a symlink.')
    lock_path = state_path.parent / 'lock'
    if lock_path.is_symlink(): stop('conflict', 'Deployment lock must not be a symlink.')
    with lock_path.open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: stop('conflict', 'Another deployment is active.')
        state = json.loads(protected_read(state_path)) if state_path.exists() else {'deploymentId':secrets.token_hex(12)}
        identity = {k:spec[k] for k in ['hostname', 'adminEmail', 'accountId', 'zoneId', 'issuer']}
        if state.get('identity', identity) != identity: stop('conflict', 'Specification differs from persisted deployment identity.')
        state['identity'] = identity
        persist = lambda: save(state_path, json.dumps(state, indent=2))
        persist()
        log = str(state_path.parent / 'operations.log')
        if args.action == 'configure':
            if Path('/etc/appjuice/server.env').exists() and 'audience' not in state:
                stop('conflict', 'Existing installation requires deliberate configuration adoption; do not overwrite it.')
            binary = shutil.which('cloudflared')
            if not binary or not re.fullmatch(r'/[A-Za-z0-9_./-]+', binary):
                stop('needs-user-action', 'Install cloudflared from Cloudflare official packages, then resume.')
            cf = Cloudflare(protected_read(spec['setupTokenFile']))
            token = configure(cf, spec, state, persist)
            env_path = Path('/etc/appjuice/server.env')
            values = {'APPJUICE_ACCESS_ISSUER':spec['issuer'], 'APPJUICE_ACCESS_AUDIENCE':state['audience'],
                'APPJUICE_PUBLIC_ORIGIN':'https://' + spec['hostname'], 'APPJUICE_SERVER_ADMIN_EMAIL':spec['adminEmail'].lower()}
            if env_path.exists():
                existing = dict(line.split('=',1) for line in protected_read(env_path).splitlines() if line and not line.startswith('#') and '=' in line)
                if any(existing.get(k) != v for k,v in values.items()): stop('conflict', 'Existing server identity differs; configuration was preserved.')
            else:
                existing = {**values, 'APPJUICE_AI_CREDENTIALS_ENCRYPTION_KEY':base64.b64encode(secrets.token_bytes(32)).decode()}
            if 'syncTokenFile' in spec:
                existing.update({'APPJUICE_CLOUDFLARE_ACCOUNT_ID':spec['accountId'], 'APPJUICE_CLOUDFLARE_ACCESS_APP_ID':state['appId'],
                    'APPJUICE_CLOUDFLARE_ACCESS_POLICY_ID':state['policyId'], 'APPJUICE_CLOUDFLARE_API_TOKEN':protected_read(spec['syncTokenFile'])})
            if any('\n' in v or '\r' in v for v in existing.values()): stop('failed', 'Invalid multiline configuration value.')
            save(env_path, ''.join(k+'='+v+'\n' for k,v in existing.items()))
            save('/etc/appjuice/tunnel.token', token)
            unit = '[Unit]\nDescription=AppJuice dedicated Tunnel\nAfter=network-online.target\n[Service]\nDynamicUser=yes\nLoadCredential=token:/etc/appjuice/tunnel.token\nExecStart='+binary+' tunnel --no-autoupdate run --token-file %d/token\nRestart=on-failure\nNoNewPrivileges=yes\n[Install]\nWantedBy=multi-user.target\n'
            unit_path = Path('/etc/systemd/system/cloudflared-appjuice.service')
            if unit_path.exists() and 'connectorConfigured' not in state: stop('conflict', 'Existing connector service requires deliberate adoption.')
            save(unit_path, unit)
            state['connectorConfigured'] = True
            persist()
            command(['systemctl', 'daemon-reload'], log)
            command(['systemctl', 'enable', '--now', 'cloudflared-appjuice.service'], log)
            return {'status':'ready', 'stage':'configured', 'next':'install'}
        if args.action == 'install':
            if not state.get('connectorConfigured'): stop('needs-user-action', 'Complete configure first, including any required user actions.')
            backup_size = capture(['du', '-sk', '/var/lib/appjuice']).split()
            backup_bytes = int(backup_size[0])*1024 if backup_size else 0
            if report['freeBytes'] < 4 * 1024**3 + backup_bytes: stop('needs-user-action', 'Free at least 4 GiB plus space for a consistent existing-data backup.')
            if not report['safeExtraction']: stop('needs-user-action', 'Use Python with tarfile.data_filter from a supported security update; preserve system Python and archive safety.')
            if report['installed'] and not spec.get('allowTaskInterruption'): stop('needs-user-action', 'Review active work and set allowTaskInterruption only after authorizing the update restart.')
            with tempfile.TemporaryDirectory(prefix='appjuice-deploy-') as folder:
                paths = {}
                for key in ['archive', 'installer']:
                    item = assets[key]
                    file = Path(folder) / ('payload.tar.gz' if key == 'archive' else 'deploy.sh')
                    with urllib.request.urlopen(item['url'], timeout=120) as response, file.open('wb') as output: shutil.copyfileobj(response, output)
                    if hashlib.sha256(file.read_bytes()).hexdigest() != item['sha256']: stop('failed', 'Downloaded artifact checksum mismatch.')
                    paths[key] = file
                Audit().run(paths['archive'])
                import tarfile
                with tarfile.open(paths['archive'], 'r:gz') as archive:
                    metadata = [m for m in archive if m.name.count('/') == 1 and m.name.endswith('/hostless-release.json')]
                    if len(metadata) != 1: stop('failed', 'Missing unique package provenance.')
                    provenance = json.load(archive.extractfile(metadata[0]))
                    if provenance.get('version') != version or provenance.get('arch') != report['arch'] or provenance.get('sourceDirty') is not False or provenance.get('sourceCommit') != index.get('sourceCommit'):
                        stop('failed', 'Package provenance differs from approved server release.')
                sums = Path(folder) / 'SHA256SUMS'
                sums.write_text(assets['archive']['sha256']+'  AppJuice-Linux-'+report['arch']+'.tar.gz\n')
                command(['bash', str(paths['installer']), '--archive', str(paths['archive']), '--sums', str(sums), '--install-deps'], log)
            state['version'] = version
            persist()
            return {'status':'ready', 'stage':'installed', 'next':'verify and complete human login/Provider checks'}
        if args.action == 'verify':
            node = '/opt/appjuice/current/bin/node'
            command([node, '/opt/appjuice/current/scripts/check-hosted-linux-service.mjs', '--version', version,
                '--admin', spec['adminEmail'].lower(), '--origin', 'https://'+spec['hostname'], '--related', 'cloudflared-appjuice.service'], log)
            Audit().run('/opt/appjuice/current')
            return {'status':'needs-user-action', 'stage':'service-verified', 'action':'Complete real administrator/ordinary login, Provider and App/Agent checks in the guide; service health alone is insufficient.'}

if __name__ == '__main__':
    try:
        result = main()
    except Stop as error:
        result = {'status':error.status, 'action':error.action}
    except Exception:
        result = {'status':'failed', 'action':'Operation did not complete. Inspect root-protected operations.log locally; no credentials or raw errors are included in this report.'}
    print(json.dumps(result))
    sys.exit(0 if result['status'] == 'ready' else 2)
