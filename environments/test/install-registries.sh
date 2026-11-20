#!/usr/bin/env bash
# Install or upgrade the OAN Farmer, Crop Sown and Livestock registries on registry-test, over SSH on the node (no
# Jenkins: the test server is never a pipeline target). Run after install.sh: each registry goes into its department's
# namespace (farmer, crop, livestock), next to that department's own Commons, as in OpenG2P's Agri Stack topology. Charts are the OAN builds New Dev runs,
# from this repository's repository/develop/, pinned in <registry>.chart ("<path> <sha256>"); values are
# values/<registry>.yaml. Farmer is rendered through its repository's post-renderer (ci/deploy/oan_compat.py) as on
# New Dev: FARMER_REGISTRY_SRC is a checkout of Centre-for-Open-Societal-Systems/farmer-registry.
# Needs helm, kubectl, python3 with PyYAML, sha256sum. HELM_TIMEOUT defaults to 30m. ONLY=farmer|cropsown|livestock
# installs one.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../.." && pwd)
timeout=${HELM_TIMEOUT:-30m}
export FARMER_REGISTRY_SRC=${FARMER_REGISTRY_SRC:-/opt/src/farmer-registry}

install_registry() {
  local name=$1 release=$2 ns=$3 path sha chart
  read -r path sha < "$here/$name.chart"
  chart="$root/repository/$path"
  echo "$sha  $chart" | sha256sum -c - >&2
  kubectl get ns "$ns" >/dev/null 2>&1 || { echo "namespace $ns has no Commons: run install.sh first" >&2; exit 1; }
  # Secret names the OAN registry charts read that OpenG2P Commons develop.340 spells differently, in the same
  # namespace: the Master Data DB password lives in master-data-db/master-data-db-user, where the OAN charts read
  # master-data-db-user/master-data-db-user-password (db-seed hook) and master-data/master-data-db-user (reporting
  # views).
  local mdpw; mdpw=$(kubectl get secret master-data-db -n "$ns" -o jsonpath='{.data.master-data-db-user}')
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata: {name: master-data-db-user, namespace: $ns, labels: {oan.org/copied-from: master-data-db}}
type: Opaque
data: {master-data-db-user-password: $mdpw}
EOF
  if kubectl get secret master-data -n "$ns" >/dev/null 2>&1; then
    kubectl patch secret master-data -n "$ns" --type merge -p "{\"data\": {\"master-data-db-user\": \"$mdpw\"}}"
  else
    kubectl create secret generic master-data -n "$ns" --from-literal=master-data-db-user="$(echo "$mdpw" | base64 -d)"
  fi
  # Crop Sown calls AWE by the short name `awe` (New Dev aliases it); here it is this department's own AWE.
  if [[ "$name" == cropsown ]]; then
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata: {name: awe, namespace: $ns, labels: {oan.org/alias-of: commons-services-awe}}
spec: {type: ExternalName, externalName: commons-services-awe.$ns.svc.cluster.local, ports: [{port: 80}]}
EOF
  fi
  # Crop Sown and Livestock sign their Farmer lookups with an Ed25519 key (<ns>-farmer-lookup-signing-ed25519). On New
  # Dev it was made by hand; here it is generated on the node the first time and kept on later runs. The private key
  # never leaves the cluster.
  if [[ "$name" == cropsown || "$name" == livestock ]]; then
    local ks="$ns-farmer-lookup-signing-ed25519"
    if ! kubectl get secret "$ks" -n "$ns" >/dev/null 2>&1; then
      local tmp; tmp=$(mktemp -d)
      openssl genpkey -algorithm ed25519 -out "$tmp/private-key.pem"
      openssl pkey -in "$tmp/private-key.pem" -pubout -out "$tmp/public-key.pem"
      kubectl create secret generic "$ks" -n "$ns" --from-literal=algorithm=EdDSA \
        --from-literal=kid="$ns-lookup-ed25519-$(openssl rand -hex 8)" \
        --from-file=private-key.pem="$tmp/private-key.pem" --from-file=public-key.pem="$tmp/public-key.pem"
      rm -rf "$tmp"
    fi
  fi
  local extra=()
  if [[ "$name" == farmer ]]; then
    test -f "$FARMER_REGISTRY_SRC/ci/deploy/oan_compat.py" || { echo "FARMER_REGISTRY_SRC has no ci/deploy/oan_compat.py" >&2; exit 1; }
    extra=(--post-renderer "$here/farmer-post-renderer.sh")
    export HELM_NAMESPACE=$ns HELM_RELEASE=$release OAN_TEST_VALUES="$here/values/$name.yaml"
  fi
  # No --wait-for-jobs: some charts give plain Jobs a TTL, and Helm then fails looking for a Job that finished and was
  # deleted. Hook Jobs (seed, IAM registration, sanity) are waited for regardless.
  helm upgrade --install "$release" "$chart" -n "$ns" -f "$here/values/$name.yaml" "${extra[@]}" \
    --wait --timeout "$timeout"
}

for entry in "farmer farmer-registry farmer" "cropsown cropsown-registry crop" "livestock livestock-registry livestock"; do
  set -- $entry
  [[ -z "${ONLY:-}" || "${ONLY}" == "$1" ]] || continue
  install_registry "$@"
done
helm list -A | grep -E 'registry' || true
