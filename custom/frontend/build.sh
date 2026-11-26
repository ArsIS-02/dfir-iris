#!/usr/bin/env bash
# Build the exact upstream IRIS frontend with laboratory patches.
set -euo pipefail

UPSTREAM_REF='3e02ba0d221235968b188c440faaeac4169f0714'
IMAGE='localhost/iris-frontend-homelab:v3.0.0-beta.23-dfir'
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
WORK=$(mktemp -d)

storage_container_ids() {
  podman ps -a --external --format '{{.ID}}|{{.Status}}' |
    awk -F'|' '$2 == "Storage" {print $1}'
}

BUILD_CONTAINERS_BEFORE=$(storage_container_ids | sort)
cleanup() {
  rc=$?
  trap - EXIT
  rm -rf "$WORK" || true
  # --force-rm handles normal build failures. This EXIT cleanup also removes
  # storage containers left by this run if Podman could not remove them itself.
  comm -13 \
    <(printf '%s\n' "$BUILD_CONTAINERS_BEFORE" | sort) \
    <(storage_container_ids | sort) |
    xargs -r podman rm -f || true
  exit "$rc"
}
trap cleanup EXIT

: "${TB_KEY:?Set TB_KEY for the TicketBridge case action}"
: "${TB_TICKETBRIDGE_URL:?Set TB_TICKETBRIDGE_URL for the TicketBridge case action}"

git clone --quiet --filter=blob:none --no-checkout \
  https://github.com/dfir-iris/iris-frontend.git "$WORK/source"
git -C "$WORK/source" checkout --quiet --detach "$UPSTREAM_REF"
git -C "$WORK/source" apply "$ROOT/alerts-auto-refresh.patch"
git -C "$WORK/source" apply "$ROOT/case-velociraptor.patch"
git -C "$WORK/source" apply "$ROOT/case-opened-at.patch"
git -C "$WORK/source" apply "$ROOT/case-closed-at.patch"
git -C "$WORK/source" apply "$ROOT/incident-terminology.patch"
git -C "$WORK/source" apply "$ROOT/evidence-download.patch"
sed -i -e "s/__TB_KEY__/${TB_KEY}/g" \
  -e "s#__TB_URL__#${TB_TICKETBRIDGE_URL%/}#g" \
  "$WORK/source/src/routes/(app)/case/[case_id]/components/VelociraptorCollectDialog.svelte" \
  "$WORK/source/src/routes/(app)/case/[case_id]/components/VelociraptorJobsCard.svelte"
! grep -rqE '__TB_(KEY|URL)__' "$WORK/source/src"

podman build --force-rm --tag "$IMAGE" "$WORK/source"
printf 'Built %s from upstream %s + laboratory patches\n' "$IMAGE" "$UPSTREAM_REF"
