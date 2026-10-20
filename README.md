# AppJuice Releases

This repository publishes AppJuice release artifacts.

Website: https://appjuice.app

## Private website validation

`Validate private website` runs on standard public Linux runners. Every five minutes
(GitHub may delay schedules) it discovers current `appjuice-site/main` and open
same-repository PR heads. It validates exact SHAs and writes `website/public-ci`
commit statuses to the private website repository. Fork PRs are excluded. Completed
heads are skipped; pending checks older than one hour recover after interrupted runs.
Manual dispatch can rerun a current trusted head using `source_sha`.

The existing `APPJUICE_REPO_TOKEN` needs private website contents read and commit
statuses write permissions. `HOSTLESS_AGE_RECIPIENT` encrypts diagnostics using the
existing operator identity. Source scripts receive no Actions command channels or
repository token. No private source, dependency cache or plaintext log is uploaded;
encrypted diagnostic artifacts expire after one day. Failed checks link to the
public run; the operator decrypts the log with the existing private age identity.
The website's Cloudflare Pages deployment and release-history publication remain
separate from this validation workflow.
