# AppJuice Releases

This repository publishes AppJuice desktop release artifacts.

- `main` contains this release README and the GitHub Actions workflow used to publish releases.
- GitHub Releases in this repository provide the downloadable desktop installers.
- The public AppJuice website is no longer hosted from this repository.

Release builds are triggered from tagged source snapshots in
[`herrkaefer/appjuice`](https://github.com/herrkaefer/appjuice). The workflow
builds and uploads the supported macOS desktop packages:

- `AppJuice-macOS-arm64.dmg`
- `AppJuice-macOS-x64.dmg`

## macOS unsigned app notice

Current macOS builds are unsigned. After downloading the `.dmg`, drag
`AppJuice.app` into `/Applications` as usual. If macOS blocks the app because it
cannot verify the developer, remove the quarantine marker from the installed app:

```bash
xattr -dr com.apple.quarantine /Applications/AppJuice.app
```

Then open AppJuice again from `/Applications`.
