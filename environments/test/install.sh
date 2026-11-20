#!/usr/bin/env bash
# Install or upgrade the Commons of every organisation on registry-test, in OpenG2P's Agri Stack reference topology
# (https://docs.openg2p.org/products/open-agri-stack/deployment): one namespace per organisation, each with its own
# Commons and its own domain, calling the others only through public hostnames.
#
#   namespace  organisation           domain                           Commons role   then
#   farmer     Farmer department      *.farmer.test.oanstaging.com     department     install-registries.sh
#   crop       Crop Sown department   *.crop.test.oanstaging.com       department     install-registries.sh
#   livestock  Livestock department   *.livestock.test.oanstaging.com  department     install-registries.sh
#   agrix      The Exchange           *.agrix.test.oanstaging.com      exchange       the Composite (below)
#
# All charts are OpenG2P's, unmodified, fetched from the OpenG2P Helm repository at the versions pinned in *.chart
# ("<version> <sha256>") and checked against the sha256. Run on the node over SSH (never from Jenkins). Needs helm,
# kubectl, curl and sha256sum. HELM_TIMEOUT defaults to 40m; each step is helm upgrade --install, so a rerun upgrades
# in place. ONLY=<namespace> installs one organisation.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repository=${OPENG2P_HELM_REPOSITORY:-https://openg2p.github.io/openg2p-helm}
timeout=${HELM_TIMEOUT:-40m}
parent=test.oanstaging.com
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() {
  local chart=$1 pin=$2 version sha
  read -r version sha < "$pin"
  [[ "$version" && "$sha" =~ ^[0-9a-f]{64}$ ]] || { echo "$pin must be '<version> <sha256>'" >&2; exit 1; }
  [[ -f "$work/$chart.tgz" ]] || curl -sfL "$repository/$chart-$version.tgz" -o "$work/$chart.tgz"
  echo "$sha  $work/$chart.tgz" | sha256sum -c - >&2
  echo "$work/$chart.tgz"
}

# The namespace and its `internal` gateway for the organisation's domain: every OpenG2P VirtualService uses it. Host
# nginx terminates TLS for *.<org>.test.oanstaging.com (ingress/nginx.conf) and proxies to the ingress gateway.
namespace() {
  local ns=$1 domain=$2
  kubectl get ns "$ns" >/dev/null 2>&1 || kubectl create ns "$ns"
  kubectl apply -f - <<EOF
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata: {name: internal, namespace: $ns}
spec:
  selector: {istio: ingressgateway}
  servers:
  - hosts: ['*.$domain']
    port: {name: http, number: 8080, protocol: HTTP}
EOF
}

commons() {
  local ns=$1 role=$2 domain="$1.$parent" base services
  namespace "$ns" "$domain"
  base=$(fetch openg2p-commons-base "$here/commons-base.chart")
  helm upgrade --install commons "$base" -n "$ns" -f "$here/values/commons-base.yaml" \
    --set global.baseDomain="$domain" --wait --timeout "$timeout"
  local files=(-f "$here/values/commons-services-$role.yaml")
  if [[ "$ns" == crop || "$ns" == livestock ]]; then files+=(-f "$here/values/commons-services-no-esignet.yaml"); fi
  services=$(fetch openg2p-commons-services "$here/commons-services.chart")
  helm upgrade --install commons-services "$services" -n "$ns" "${files[@]}" \
    --set global.baseDomain="$domain" --wait --timeout "$timeout"
  # The staff and agent IAM APIs seed the shared iam.login_providers table at startup; on a fresh install the staff
  # API can lose that race and never seed its staff-realm provider, so every staff token is "Unknown Issuer" (the
  # IAM register jobs then retry forever). A restart seeds it; harmless when it is already there.
  kubectl rollout restart -n "$ns" deploy/commons-services-iam-staff-portal-api
  kubectl rollout status -n "$ns" deploy/commons-services-iam-staff-portal-api --timeout=5m
}

for entry in "farmer department" "crop department" "livestock department" "agrix exchange"; do
  set -- $entry
  [[ -z "${ONLY:-}" || "${ONLY}" == "$1" ]] || continue
  commons "$1" "$2"
  if [[ "$1" == agrix ]]; then
    composite=$(fetch openg2p-agri-composite "$here/agri-composite.chart")
    helm upgrade --install agri-composite "$composite" -n agrix -f "$here/values/agri-composite.yaml" \
      --wait --timeout "$timeout"
  fi
done
helm list -A | grep -E '^(commons|commons-services|agri-composite)\s' || true
