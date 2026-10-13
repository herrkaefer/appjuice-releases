# Encrypted private Hostless builds

The public workflow builds the private AppJuice project on native standard
GitHub-hosted x64 and ARM64 runners. It does not publish a Release, deploy to a
server, or change the desktop release workflow.

## Access and encryption

- `HOSTLESS_SOURCE_SSH_KEY` is a repository Secret containing a **read-only
  deploy key for the private source repository only**. It is not the wider
  desktop-release token. The runner pins GitHub's Ed25519 host key and removes
  the temporary private key before running source build scripts.
- `HOSTLESS_AGE_RECIPIENT` is a repository Variable containing an age X25519
  public recipient. Only the public recipient reaches Actions. Keep the matching
  private identity on the operator's machine, mode 0600, with a protected backup.
  The identity is never a GitHub Secret and never enters the workflow.
- Source input is a full lowercase commit SHA reachable from private `master`.
  Forks, PR events and arbitrary source repositories are not accepted.
- The encryption executable is age 1.3.2, downloaded for the native architecture
  and checked against committed SHA256 digests before source access.

## Build

```sh
gh workflow run hostless-private-build.yml -R herrkaefer/appjuice-releases \
  -f source_sha=FULL_TRUSTED_SOURCE_SHA
```

The workflow retains the source pipeline's native dependency setup, package
typechecks, service/auth/browser regressions, system-service isolation gate,
bundle/Pi/Runtime/CLI checks and isolated archive installation/App lifecycle
acceptance. It does not substitute an older native archive.

Every private command's stdout and stderr go to a mode-0600 diagnostic file
outside the public workspace. Children do not inherit GitHub workflow-command
files or Actions tokens. Public output contains only fixed phase/status labels.
Canaries written to both output streams test the boundary in actual runs.
Failure paths also encrypt diagnostics; if encryption is unavailable, they upload
nothing. Full logs are never printed in public on success or failure.

The artifact allowlist is:

- `Hostless-Linux-ARCH.tar.age` on success: encrypted tar containing the native
  installation archive, checksums, provenance and two installer scripts.
- `Diagnostics-ARCH.tar.age`: encrypted diagnostics and output-stream canaries.
- `receipt.json`: schema, source commit, architecture, version, status, failed
  phase and encrypted filenames only.
- `SHA256SUMS`: checksums of ciphertext files only.

There is no public Actions cache. Artifacts expire after one day. Public readers
can download the ciphertext and approved receipt metadata, not plaintext source,
compiled JavaScript, installer scripts or build logs. Ciphertext is authenticated
by age, but encryption alone does not authenticate the publisher: download from
the intended run and verify its workflow commit/source SHA before use.

## Download, decrypt and verify

```sh
gh run download RUN_ID -R herrkaefer/appjuice-releases \
  -n AppJuice-Hostless-Encrypted-x64 -D encrypted-x64
# Save the public run log locally without echoing it into another workflow.
gh run view RUN_ID -R herrkaefer/appjuice-releases --log > public-run.log
python3 scripts/hostless/verify.py --artifact encrypted-x64 \
  --identity /protected/path/age-identity.txt --source-sha FULL_TRUSTED_SOURCE_SHA \
  --arch x64 --output decrypted-x64 --public-log public-run.log
```

Use Python 3.12+ (or a security-backported `tarfile.data_filter`), age, and a new
private output directory. Repeat for ARM64. The verifier checks ciphertext hashes,
decrypts without forwarding logs, validates strict inner file lists, tests log
canary confidentiality, checks plaintext archive hashes and embedded clean-source
provenance, and audits archive paths/links plus Platform source/map exclusion.
It does not execute foreign binaries or install anything on the operator machine.
Inspect raw diagnostics locally only. For an early checkout failure there is no
installation archive; the encrypted diagnostics and failure receipt remain usable.

After verification, use the existing checksum-verified operator deployment flow.
Keep server data, wrapping keys, prior releases and rollback backups separate from
CI. Existing production servers are not automatically updated by this workflow.

## Security checks

```sh
HOSTLESS_TEST_AGE=/path/to/age python3 scripts/hostless/test_privacy.py
```

The tests cover private output/workflow-command capture, credential/channel
removal, fixed phase labels, artifact allowlists, stale/dirty provenance, encrypted
failure diagnostics and rejection by an unrelated identity. This boundary trusts
approved source commits and the runner/GitHub administrators. It is not a sandbox
against deliberately malicious approved source or compromised dependencies.
