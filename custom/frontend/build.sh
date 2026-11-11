#!/usr/bin/env bash
# Build the exact upstream IRIS frontend with the laboratory auto-refresh patch.
set -euo pipefail

UPSTREAM_REF='3e02ba0d221235968b188c440faaeac4169f0714'
IMAGE='localhost/iris-frontend-homelab:v3.0.0-beta.23-auto-refresh'
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

git clone --quiet --filter=blob:none --no-checkout \
  https://github.com/dfir-iris/iris-frontend.git "$WORK/source"
git -C "$WORK/source" checkout --quiet --detach "$UPSTREAM_REF"
git -C "$WORK/source" apply "$ROOT/alerts-auto-refresh.patch"

podman build --tag "$IMAGE" "$WORK/source"
printf 'Built %s from upstream %s + alerts-auto-refresh.patch\n' "$IMAGE" "$UPSTREAM_REF"
