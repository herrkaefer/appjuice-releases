#!/usr/bin/env bash
set -euo pipefail

corepack enable
corepack prepare "$(node -p 'require("./package.json").packageManager')" --activate

sudo apt-get update
sudo apt-get install -y build-essential python3 libcurl4-openssl-dev libexpat1-dev zlib1g-dev libsecret-1-dev bubblewrap zip unzip
if sudo aa-status --enabled 2>/dev/null; then
  sudo install -m 644 templates/server/apparmor-appjuice-bwrap /etc/apparmor.d/appjuice-bwrap
  sudo apparmor_parser -r /etc/apparmor.d/appjuice-bwrap
fi
bwrap --die-with-parent --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-net --ro-bind / / --dev /dev --proc /proc -- /bin/true

pnpm install --frozen-lockfile
sh scripts/ci/prepare-coding-browser.sh
# Platform imports Runtime's generated exports on a clean checkout.
pnpm --filter @appjuice/app-runtime build
pnpm --filter @appjuice/platform typecheck
pnpm --filter @appjuice/app-runtime typecheck
pnpm --filter @appjuice/frontend typecheck

node --test --test-concurrency=1 scripts/cloud-service.test.mjs scripts/deploy-cloud-server.test.mjs scripts/install-linux.test.mjs
sudo env APPJUICE_SYSTEM_SERVICE_TESTS=1 "$(command -v node)" --test scripts/cloud-service.test.mjs
pnpm --filter @appjuice/app-runtime exec node --import tsx --test test/app-module-loader.test.ts
pnpm --filter @appjuice/platform test test/app-stop-state.test.ts test/terminal-app-stop.test.ts test/app-controls.test.ts test/process-manager-lifecycle.test.ts test/system-resources.test.ts test/system-api.test.ts test/app-runtime-leftovers.test.ts
pnpm --filter @appjuice/frontend exec tsx --test test/stop-apps-dialog.test.ts test/system-resource-monitor.test.ts
pnpm --filter @appjuice/platform test test/coding-browser-service.test.ts test/coding-browser-auth.test.ts test/chat-cdp-availability.test.ts test/host-cdp-service.test.ts test/server-coding-exec.test.ts
pnpm --filter @appjuice/platform test test/server-gateway.test.ts test/server-access-identity.test.ts test/server-accounts.test.ts
node --import ./packages/platform/node_modules/tsx/dist/loader.mjs --test scripts/pi-cdp-selection.test.ts
pnpm --filter @appjuice/frontend exec tsx --test test/coding-browser-exit.test.ts test/coding-event-stream-lifecycle.test.ts test/coding-session-window-state.test.ts test/chat-composer-keydown.test.ts test/coding-composer-layout.test.ts test/provider-brand-icon.test.ts
pnpm --filter @appjuice/frontend exec tsx --test test/platform-update-placement.test.ts test/system-update-panel.test.ts test/hostless-server-panel.test.ts test/getting-started-navigation.test.ts test/app-install-guide-dialog.test.ts test/app-list-responsive-layout.test.ts test/platform-access.test.ts test/server-accounts.test.ts

pnpm bundle:linux-server
BUNDLE="artifacts/esbuild-bundle/appjuice-$(node -p 'require("./package.json").version')-linux-$HOSTLESS_ARCH"
node "$BUNDLE/scripts/prepare-coding-browser.mjs" --root "$BUNDLE" --probe
node scripts/smoke-test-esbuild-bundle.mjs --bundle-root "$BUNDLE"
node scripts/smoke-test-hostless-app-loading.mjs "$BUNDLE"
node scripts/smoke-test-hostless-app-loading.mjs "$BUNDLE" --preload-baseline

node scripts/smoke-test-linux-server-bundle.mjs \
  artifacts/linux-server-release/AppJuice-Linux-$HOSTLESS_ARCH.tar.gz \
  --sums artifacts/linux-server-release/SHA256SUMS
