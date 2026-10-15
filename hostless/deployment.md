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
4. A scoped setup API token for the selected account/zone: Zone Read/DNS Edit,
   Cloudflare Tunnel Edit, and Access applications/policies and identity-provider
   read access as required by your account. Use Cloudflare's current token permission
   names. A Global API Key is unnecessary. Keep the token in a mode-0600 file.
5. Optionally, a distinct retained token restricted to Access Apps and Policies Edit
   for automatic account-email synchronization. Without it, maintain Access's email
   Allow list manually when adding/disabling AppJuice accounts.
6. An AI Provider to configure after login. Complete its authorization or enter its
   key through the administrator UI. Never paste keys into the deployment prompt.

Install `cloudflared` using Cloudflare's official Linux package instructions if it
is absent. Ensure outbound Tunnel connectivity is permitted. You do not need home
router port forwarding. The Agent should diagnose missing dependencies and explain
specific user actions; it must preserve global sandbox restrictions and unrelated
Python/service configurations.

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
A 64-bit kernel with a 32-bit userland is unsupported. `plan` resolves a published
server version and validates the specification before any changes.

JSON statuses are `ready`, `needs-user-action`, `unsupported`, `conflict` or
`failed`; only `ready` exits with zero. Explain an action to the user, wait for its
completion and repeat the same step. Never treat a paused human login as success.

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
connector. It stops for user action if a human login provider is missing. It
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
Maintain an off-device protected copy and retention policy. Inspect
`journalctl -u appjuice-cloud` and root-only deployment `operations.log` locally;
do not forward raw diagnostics or credentials into public reports.
