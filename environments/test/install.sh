#!/usr/bin/env bash
# Install or upgrade the Commons layer of the test environment (registry-test, *.test.oanstaging.com), in order:
# OpenG2P Commons base, OpenG2P Commons services, then the OpenG2P Agri Stack Composite (in place of the OAN
# Aggregation API). All three are OpenG2P charts, unmodified, fetched from the OpenG2P Helm repository at the
# versions pinned in *.chart ("<version> <sha256>") and checked against the sha256.
# Run on the cluster node (or with KUBECONFIG pointing at it). Needs helm, kubectl, curl and sha256sum.
# HELM_TIMEOUT defaults to 40m. Each step is helm upgrade --install, so a rerun upgrades in place.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ns=commons
repository=${OPENG2P_HELM_REPOSITORY:-https://openg2p.github.io/openg2p-helm}
timeout=${HELM_TIMEOUT:-40m}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() {
  local chart=$1 pin=$2 version sha
  read -r version sha < "$pin"
  [[ "$version" && "$sha" =~ ^[0-9a-f]{64}$ ]] || { echo "$pin must be '<version> <sha256>'" >&2; exit 1; }
  curl -sfL "$repository/$chart-$version.tgz" -o "$work/$chart.tgz"
  echo "$sha  $work/$chart.tgz" | sha256sum -c - >&2
  echo "$work/$chart.tgz"
}

kubectl get ns "$ns" >/dev/null 2>&1 || kubectl create ns "$ns"
kubectl apply -f "$here/ingress/gateway.yaml"

base=$(fetch openg2p-commons-base "$here/commons-base.chart")
helm upgrade --install commons "$base" -n "$ns" -f "$here/values/commons-base.yaml" --wait --timeout "$timeout"

services=$(fetch openg2p-commons-services "$here/commons-services.chart")
helm upgrade --install commons-services "$services" -n "$ns" -f "$here/values/commons-services.yaml" \
  --wait --timeout "$timeout"

composite=$(fetch openg2p-agri-composite "$here/agri-composite.chart")
helm upgrade --install agri-composite "$composite" -n "$ns" -f "$here/values/agri-composite.yaml" \
  --wait --timeout "$timeout"

helm list -n "$ns"
