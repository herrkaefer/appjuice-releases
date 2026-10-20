"""Validate trusted private website heads without public source, logs or caches."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

REPO = 'herrkaefer/appjuice-site'
CONTEXT = 'website/public-ci'
COMMANDS = [('install', ['npm', 'ci']),
            ('worker-tests', ['npm', 'run', 'test:web-worker']),
            ('typecheck', ['npm', 'run', 'typecheck:web']),
            ('build-verification', ['npm', 'run', 'verify:web-build'])]


def api(path, token, data=None):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'},
        data=None if data is None else json.dumps(data).encode(),
        method='GET' if data is None else 'POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def child_env(source):
    # Source scripts cannot inherit PATs, Actions command channels or shared caches.
    allowed = ['PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'RUNNER_TEMP']
    env = {k: os.environ[k] for k in allowed if k in os.environ}
    env.update(HOME=str(source.parent / 'home'), npm_config_cache=str(source.parent / 'npm-cache'),
               CI='true', GIT_TERMINAL_PROMPT='0')
    Path(env['HOME']).mkdir(exist_ok=True)
    return env


def candidates(token):
    main = api('/commits/main', token)['sha']
    result = [main]
    # A repository collaborator controls same-repository branches; fork code is excluded.
    page = 1
    while True:
        pulls = api(f'/pulls?state=open&per_page=100&page={page}', token)
        for pr in pulls:
            if pr['head'].get('repo') and pr['head']['repo']['full_name'] == REPO:
                result.append(pr['head']['sha'])
        if len(pulls) < 100:
            break
        page += 1
    return list(dict.fromkeys(result))


def should_run(statuses, force=False):
    if force:
        return True
    status = next((s for s in statuses if s['context'] == CONTEXT), None)
    if status is None:
        return True
    if status['state'] != 'pending':
        return False
    from datetime import datetime, timezone
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(status['created_at'].replace('Z', '+00:00'))).total_seconds()
    return age > 3600


def main():
    os.umask(0o077)
    token = os.environ['WEBSITE_TOKEN']
    recipient = os.environ['WEBSITE_AGE_RECIPIENT']
    if not re.fullmatch(r'age1[a-z0-9]{58}', recipient):
        raise ValueError('Missing encryption recipient')
    heads = candidates(token)
    requested = os.environ.get('WEBSITE_SOURCE_SHA', '').strip()
    if requested and (not re.fullmatch('[a-f0-9]{40}', requested) or requested not in heads):
        raise ValueError('Only current trusted heads may be requested')
    targets = [requested] if requested else heads
    targets = [sha for sha in targets if should_run(api('/commits/' + sha + '/statuses', token), bool(requested))]
    if not targets:
        print('No new trusted website commits.', flush=True)
        return
    spec = importlib.util.spec_from_file_location('private_build', Path(__file__).parents[1] / 'hostless/build.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    output = Path('website-diagnostics')
    output.mkdir(exist_ok=True)
    failed = False
    with tempfile.TemporaryDirectory(prefix='private-website-') as directory:
        private = Path(directory)
        age = helper.install_age(private, 'x64')
        for sha in targets:
            log = private / (sha + '.log')
            source = private / sha
            url = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            def status(state, description):
                api('/statuses/' + sha, token, {'state': state, 'context': CONTEXT,
                    'description': description, 'target_url': url})
            status('pending', 'Website validation running on public runner')
            phase = 'checkout'
            ok = False
            try:
                env = child_env(source)
                with log.open('wb') as stream:
                    subprocess.run(['git', 'init', str(source)], env=env, stdout=stream, stderr=stream, check=True)
                    auth = base64.b64encode(('x-access-token:' + token).encode()).decode()
                    git_env = dict(env, GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                                   GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + auth)
                    subprocess.run(['git', '-C', str(source), 'fetch', '--depth=1',
                        'https://github.com/' + REPO + '.git', sha], env=git_env, stdout=stream, stderr=stream, check=True)
                    subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'],
                        env=env, stdout=stream, stderr=stream, check=True)
                    for phase, command in COMMANDS:
                        print('Website phase: ' + phase, flush=True)
                        subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=stream, check=True, timeout=900)
                ok = True
            except Exception:
                failed = True
            finally:
                # No decrypted diagnostics or private checkout are uploaded.
                subprocess.run([str(age), '-r', recipient, '-o', str(output / (sha + '.log.age')), str(log)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                status('success' if ok else 'failure', 'Website validation passed' if ok else 'Website validation failed: ' + phase)
                print('Website validation ' + ('passed.' if ok else 'failed; diagnostics encrypted.'), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print('Website orchestration failed; no private output published.', flush=True)
        raise SystemExit(1)
