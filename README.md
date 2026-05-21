# AppJuice Releases

This repository publishes AppJuice desktop release artifacts.

## macOS unsigned app notice

Current macOS builds are unsigned. After downloading the `.dmg`, drag
`AppJuice.app` into `/Applications` as usual. If macOS blocks the app because it
cannot verify the developer, remove the quarantine marker from the installed app:

```bash
xattr -dr com.apple.quarantine /Applications/AppJuice.app
```

Then open AppJuice again from `/Applications`.
