# AppJuice Releases

This repository publishes AppJuice release artifacts.

Website: https://appjuice.app

The release workflow has an opt-in `include_hostless` flag (default false).
When enabled, use a version tag or full source commit SHA. Independent native Ubuntu
24.04 x64/arm64 jobs validate and build the Linux server archives, test packaged
Pi/Runtime/CLI and isolated installation, then stage the archives, checksums and
`deploy-cloud-server.sh`. Public publication waits for these jobs to pass.
The default Mac release path does not require Linux builds. This flag prepares
formal release distribution; private build verification is performed in the
source repository's Build Bundles workflow with `server_only=true`.

Only invoke this workflow when an actual public release is authorized and the
source snapshot has approved complete release notes. Cloud installer usage and
first-run Cloudflare requirements are documented in the source repository's
`docs/cloud-server.md`. The installer does not configure Cloudflare automatically.
