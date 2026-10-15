# Deploy AppJuice with an Agent

This guide covers a dedicated Linux service on a VPS, personal Linux machine or
64-bit Raspberry Pi, accessed through Cloudflare Tunnel and Access. The same
Platform, App Runtime and interface run on every target. Approved server files,
protected commands and Agent tools remain available within their configured grants.

## Release availability

The public Hostless index is the authority for downloadable server releases:
`https://raw.githubusercontent.com/herrkaefer/appjuice-releases/main/hostless/index.json`.
Proceed only when its status is `published` and its supported-system entries include
the detected target. A `pending` index means qualification/publication is unfinished.
Do not substitute the latest desktop release, encrypted operator artifacts, private
source access or a different architecture's native dependencies.

## Prompt to give your Agent

> Help me deploy AppJuice as a Linux service. Read this deployment guide and the
> official Hostless release index. Inspect my target machine and existing services,
> detect its OS, CPU and userland architecture, and select a qualified package.
> Explain the missing prerequisites and the actions I need to complete. Use the
> official deployment tools, protect credentials and existing data, and continue
> after any required login or authorization. Verify external Access login and real
> App/Agent work, then report passed and pending checks plus maintenance instructions.
> Ask me for the target connection, hostname and administrator email if unavailable.

The Agent requires terminal/SSH access and a way to request your participation.
It does not need access to AppJuice's private source repository.

## What you prepare

1. An existing Linux machine with systemd, authorized SSH/local terminal and sudo
   access. Candidate systems are Ubuntu 24.04 x64 and Debian 12 / Raspberry Pi OS
   Bookworm ARM64. Actual advertised support comes from the published index.
2. A hostname in your Cloudflare-managed DNS zone and a Cloudflare Zero Trust team.
   Sign in or create/connect these if needed. Keep existing SSH recovery access.
3. Your administrator email, admitted through the chosen Access login method.
   Email one-time PIN is the default. An existing identity provider may supply
   password/SSO/MFA login; AppJuice does not add a second password store.
4. Complete the login/authorization screen opened by your Agent when needed. The
   Agent should use an already authorized Cloudflare connection or prepare the
   official OAuth-capable CLI/MCP and explain the requested account/permissions.
   You should not need to create API tokens, choose permission names, find IDs or
   save credential files yourself. The Agent handles resource discovery and secure
   credential storage. It asks only for required login, MFA and final consent.
5. An AI Provider to configure after login. Complete its authorization or enter its
   key through the administrator UI. Never paste keys into the deployment prompt.

The low-level token-file specification below is for the Agent or an operator with
existing automation credentials. It is an advanced fallback. When using OAuth/MCP,
the Agent prepares the Cloudflare resources through that authorized connection and
writes the protected server configuration through the same deployment contract.
Retained email-policy synchronization may use a separate restricted credential;
setup access must not silently become permanent broad runtime access.

Install `cloudflared` using Cloudflare's official Linux package instructions if it
is absent. Ensure outbound Tunnel connectivity is permitted. You do not need home
router port forwarding. The Agent should install missing runtime/inspection dependencies (including
`iproute2` for `ss`) and explain specific user actions only when required; it must preserve global sandbox restrictions and unrelated
Python/service configurations.

## Agent-managed Cloudflare authorization

Use the official [Cloudflare CLI](https://developers.cloudflare.com/cf/) from the
verified `cf` npm package when no suitable authorized connector is available. The
Agent can run it on its own machine with Node 22 or newer; it need not install
Node or the CLI on the destination server. Use an isolated installation/profile
with mode 0700 and a private log. For the tested CLI `1.0.0-beta.17`, request:

```sh
cf auth login --no-browser --scopes account:read zone:read dns.read dns.write argotunnel.read argotunnel.write access-app.read access-app.write access-policy.read access-policy.write access-idp.read access-org.read
```

The Agent opens the official device verification page, submits the current code,
and checks the account and exact requested permissions. The user completes only
required sign-in/MFA and the final authorization. Follow the tool's permission
policy; never silently approve a new scope. `offline_access` is added by the CLI
for refresh access. Explain that access can be revoked in Cloudflare's connected
applications. Verify `cf auth whoami` without printing credential values.

Discover the matching zone/account and the Access organization issuer through the
authorized API. Do not ask the user to copy IDs. The CLI stores its OAuth profile
under the selected configuration directory. Read that protected profile locally
without logging it and provide only its short-lived access bearer to the
root-owned `setupTokenFile` through authorized SSH/stdin or a protected transfer.
Never transfer the refresh token to the server or put either token in command
arguments, prompts, screenshots, reports or AppJuice's runtime environment.
Refresh through the official CLI when necessary. Remove temporary setup bearer
copies after provisioning; revoke the isolated connected-app session when testing
is finished. Ordinary future account changes can be handled by an Agent through
a fresh authorization; do not retain this broad setup session as a service token.

If `cloudflared` is absent, the Agent installs it from
[Cloudflare's signed package repository](https://pkg.cloudflare.com/) and verifies
its executable before continuing. Dependency installation, file permissions,
resource discovery and configuration are Agent tasks. A missing prerequisite is
not a reason to hand the user terminal commands.

## Download and verify deployment tooling

Resolve the index from the official public repository. Select a pinned version and
inspect its official release provenance/checksums before running downloaded code.
Obtain `deploy.py` and `audit.py` from that same version's approved release assets
and retain both in the same directory. The index supplies hashes for both tools,
the native archive and `deploy-cloud-server.sh`. Verify all downloaded file hashes.
The Agent must not execute a script obtained from an arbitrary search result.

## Specification and target detection

Write a non-secret JSON specification (example values below). Token values belong
in the referenced protected files, owned by the invoking user/root with mode 0600.
For sudo execution, provision root-owned secret files using an authorized secure
method. Avoid command-line token values, shell tracing and public terminal logs.

```json
{
  "version": "REPLACE_WITH_THE_PLANNED_PUBLISHED_VERSION",
  "hostname": "juice.example.com",
  "adminEmail": "owner@example.com",
  "issuer": "https://your-team.cloudflareaccess.com",
  "accountId": "YOUR_32_HEX_CLOUDFLARE_ACCOUNT_ID",
  "zoneId": "YOUR_32_HEX_CLOUDFLARE_ZONE_ID",
  "setupTokenFile": "/root/appjuice-setup.token",
  "syncTokenFile": "/root/appjuice-access-sync.token",
  "allowTaskInterruption": false
}
```

Omit `syncTokenFile` for manually managed email sign-in. The Agent obtains the real
team issuer/account/zone from your selected Cloudflare setup. It must not guess
these from the machine type. Run:

```sh
python3 deploy.py inspect
python3 deploy.py plan --spec deployment.json
```

`inspect` is read-only. It reports OS, CPU architecture, userland bits, libc,
systemd, disk space, existing installation, connector and safe-extraction support.
A 64-bit kernel with a 32-bit userland is unsupported. Omit `version` for the first read-only plan, then record its resolved version in the specification. `plan` resolves a published
server version and validates the specification before any changes.

JSON statuses are `ready`, `needs-user-action`, `unsupported`, `conflict` or
`failed`; only `ready` exits with zero. These are orchestration signals for the
Agent. First handle technical prerequisites, inspect protected local diagnostics,
and resolve safe retryable failures yourself. Ask the user only when their login,
MFA, explicit consent or an unavailable decision is actually required. Then wait
for that action and repeat the same step. Never treat a paused login as success.

## Configure, install and resume

```sh
sudo python3 deploy.py configure --spec deployment.json
sudo python3 deploy.py install --spec deployment.json
sudo python3 deploy.py verify --spec deployment.json
```

Each step revalidates current state. A root-protected record under
`/var/lib/appjuice-deploy` remembers the installation identity and created resource
IDs. Resume by repeating the interrupted step with the same specification/state.
Keep this state with protected operational backups. Concurrent deployments are
serialized. Do not delete state merely to bypass a conflict.

Configuration creates/reuses deployment-specific resources, protects the entire
hostname through Access, configures the Tunnel route, and starts a dedicated
connector. It accepts existing email OTP or supported SSO/password identity providers. If none
is configured, the Agent prepares the login method with official CLI/API/browser
tools and requests only the necessary consent. The default setup grant reads IdPs;
creating one needs separate IdP-write authorization or an approved dashboard action. It
refuses unrelated hostname/policy/Tunnel/service collisions. Existing operator
installations need deliberate reviewed adoption rather than an overwrite.

The installer validates the archive hash and inventory before immutable staging,
probes actual protected execution and managed Chromium as the service user,
creates a consistent backup and starts the pinned service. AppJuice listens on
loopback internally. Persisted data is `/var/lib/appjuice`; protected settings and
the persistent wrapping key are in `/etc/appjuice/server.env`. Never regenerate
that key on retry/update. The setup API token is not written into AppJuice's runtime
environment; keep or revoke it deliberately after setup. The optional narrower
sync token remains server-only. The connector token has its own protected file.

At least 4 GiB staging headroom plus sufficient space for an existing-data backup
is required. An older Python missing `tarfile.data_filter` needs a supported
security update or a scoped verified interpreter; never bypass safe extraction.
Ubuntu namespace restrictions need the provided executable-specific AppArmor
profiles, not a global security toggle or unsandboxed fallback.

## Debian 12 deployment interpreter

If `python3 -c 'import tarfile; assert hasattr(tarfile, "data_filter")'` fails,
the Agent prepares an isolated interpreter. Do not replace `/usr/bin/python3`,
change its alternatives, compile AppJuice, or remove the archive safety check.
The following Agent-only bootstrap was tested in a clean Debian 12 ARM64 system:

```python
# Run with authorized root access; uses only the existing Python standard library.
import hashlib, io, os, pathlib, platform, subprocess, tarfile, urllib.request
assert os.geteuid() == 0
arch = {"aarch64": "aarch64", "x86_64": "x86_64"}[platform.machine()]
expected = {
    "aarch64": "9041c73c99fdc5892cf128140beb354eca9231d502068cc36e6cb53a8e59ad14",
    "x86_64": "eadd9d27c134ab5ac1ffd4473b97a741407f3ea238288f03121fc4deddf90220",
}[arch]
root = pathlib.Path("/opt/appjuice-deploy")
assert not root.is_symlink()
root.mkdir(mode=0o700, exist_ok=True)
assert root.stat().st_uid == 0 and not root.stat().st_mode & 0o077
name = "uv-" + arch + "-unknown-linux-gnu"
url = "https://github.com/astral-sh/uv/releases/download/0.13.1/" + name + ".tar.gz"
with urllib.request.urlopen(url, timeout=120) as response:
    data = response.read(64 * 1024 * 1024)
assert hashlib.sha256(data).hexdigest() == expected
# Copy only one verified regular file: no archive extraction API or link handling.
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
    member = archive.getmember(name + "/uv")
    assert member.isfile()
    binary = archive.extractfile(member).read()
uv = root / "uv"
assert not uv.is_symlink()
if uv.exists():
    assert hashlib.sha256(uv.read_bytes()).digest() == hashlib.sha256(binary).digest()
else:
    with uv.open("xb") as output:
        output.write(binary)
    uv.chmod(0o700)
subprocess.run([str(uv), "python", "install", "3.12.15", "--no-config", "--no-bin",
    "--install-dir", str(root / "python"), "--cache-dir", str(root / "cache")], check=True)
python = root / "python" / ("cpython-3.12.15-linux-" + arch + "-gnu") / "bin/python3.12"
subprocess.run([str(python), "-c", "import tarfile; assert hasattr(tarfile, 'data_filter')"], check=True)
print(python)
```

The pinned uv archive hashes are from the official Astral release. uv uses its
managed Python distributions and checksums; keep TLS validation enabled. Use the
printed absolute interpreter for every `deploy.py` step. The deployer propagates
that interpreter's directory to installer subprocesses while leaving the OS Python
untouched. Keep this directory root-owned and protected. This environment is for
deployment tooling; it does not add a Python requirement to individual Apps.

## Acceptance and handover

`verify` checks the exact service version, service policy, persisted administrator,
loopback listeners, external Access redirect, connector and installed inventory.
It then explicitly requests remaining human/browser checks:

- Complete administrator OTP/SSO and verify the account/hostname.
- Configure a Provider and complete a real Runtime Agent turn with saved history.
- Import/start an App; verify approved file read/write and protected commands,
  denied outside-grant access, Coding/Tweak and the managed browser.
- Add an ordinary account, verify its real login, Use/Develop/App grants and
  disable/revoke behavior. Check automatic email-policy synchronization if enabled.
- Verify state after service restart; perform a reboot only with the user's
  authorization for interrupting this machine's work.

Report pass/pending/fail separately, with version, hostname, backup location and
maintenance instructions. Healthy local services do not establish real login,
Provider use, capacity or backup restore.

## Updates and recovery

Inspect running Apps/Agents and explain interruption before updating. Resolve and
verify an explicitly selected compatible release/index. Set `allowTaskInterruption`
to true only after the user authorizes the restart, then repeat install/verify.
The service retains Apps, account grants, config, wrapping key and supported history;
interrupted tasks do not automatically resume. The browser's update controls remain
operator-managed for this system service.

The installer records protected backups under `/var/backups/appjuice-cloud-update.*`
and restores the prior binary/unit/service state on failed promotion. A binary
rollback cannot undo incompatible data migrations. Before downgrade, check the
release's upgrade contract and test recovery with isolated data/ports. Never
restore a backup over live work without explicit direction.

Protect backups of `/var/lib/appjuice`, `/etc/appjuice` (including the key/connector
material), deployment state, relevant systemd units and `/home/appjuice/.gitconfig`.
For an isolated restore proof, verify the selected protected backup, then extract
its storage archive with `tarfile.data_filter` into a new private directory. Omit
`appjuice/run` and the derived `appjuice/apps/node_modules` link; Platform recreates
these runtime links for the restored location. Preserve the rest of the App/config
bytes and ownership. Copy the backed-up server environment privately, retain its
wrapping key, and explicitly change `APPJUICE_STORAGE_ROOT`, `SERVER_PORT`,
`APPJUICE_APP_SERVER_PORT` and `APPJUICE_GATEWAY_PORT` to isolated storage and unused
loopback ports. Start a temporary service with the same service user, sandbox
properties and verified program. Check both local health endpoints, anonymous
Gateway rejection, account records, conversation history and artifact hashes.
Stop the temporary service and delete its test-only storage/configuration after
recording sanitized results; it can contain copied Provider credentials. Do not
replace the live data, change its key, expose the restore publicly or count an
archive listing alone as a successful restore.

Maintain an off-device protected copy and retention policy. Inspect
`journalctl -u appjuice-cloud` and root-only deployment `operations.log` locally;
do not forward raw diagnostics or credentials into public reports.

## Pre-release operator qualification

Before publication, a designated test machine can install an exact trusted native
archive using `install --archive FILE --sums SHA256SUMS --installer deploy-cloud-server.sh`.
Record its expected version and full trusted `sourceCommit` in the specification.
The tool still validates hashes, recursive inventory and embedded clean-source
provenance. This explicit offline path neither publishes a release nor turns a
pending public index into a supported release. Configure and verify use the
recorded specification identity/version and do not require a public release.
