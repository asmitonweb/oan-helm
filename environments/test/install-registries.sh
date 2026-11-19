#!/usr/bin/env bash
# Install or upgrade the OAN Farmer, Crop Sown and Livestock registries on registry-test, over SSH on the node (no
# Jenkins: the test server is never a pipeline target). Run after install.sh. Charts are the OAN builds New Dev runs,
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
  kubectl get ns "$ns" >/dev/null 2>&1 || kubectl create ns "$ns"
  kubectl apply -f - <<EOF
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata: {name: internal, namespace: $ns}
spec:
  selector: {istio: ingressgateway}
  servers:
  - hosts: ['*.test.oanstaging.com']
    port: {name: http, number: 8080, protocol: HTTP}
EOF
  # The registry charts read these Commons Secrets in their own namespace. On New Dev they were copied by hand (no
  # owner, not Helm-managed); here they are copied from commons on every run, so a rotated value follows.
  # Entries are <commons secret>[:<name here>[:<commons key>=<key here>]]: OpenG2P Commons develop.340 keeps the
  # Master Data DB password in master-data-db/master-data-db-user, where the OAN charts read
  # master-data-db-user/master-data-db-user-password (the db-seed hook fails with "secret not found" otherwise).
  local s
  for s in commons-postgresql commons-keycloak commons-minio commons-services-staff-portal awe-db-user master-data \
           master-data-db:master-data-db-user:master-data-db-user=master-data-db-user-password; do
    kubectl get secret "${s%%:*}" -n commons -o json \
      | python3 -c 'import json,sys; s=json.load(sys.stdin); ns, spec = sys.argv[1], sys.argv[2].split(":")
name = spec[1] if len(spec) > 1 else s["metadata"]["name"]
data = s["data"]
if len(spec) > 2:
    src, dst = spec[2].split("=")
    data = {dst: data[src]}
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": s["type"], "data": data,
                  "metadata": {"name": name, "namespace": ns,
                               "labels": {"oan.org/copied-from": "commons"}}}))' "$ns" "$s" \
      | kubectl apply -f -
  done
  # OAN's Commons also keeps the Master Data DB password in master-data/master-data-db-user (the reporting-views hooks
  # read it there); OpenG2P's keeps it only in master-data-db.
  kubectl patch secret master-data -n "$ns" --type merge -p "{\"data\": {\"master-data-db-user\": \"$(
    kubectl get secret master-data-db -n commons -o jsonpath='{.data.master-data-db-user}')\"}}"
  # The registry charts call Commons services by short name (e.g. AUTH_PROVIDER_API_URL
  # http://commons-services-iam-staff-portal-api), which only resolves inside commons. New Dev has hand-applied
  # ExternalName Services in each registry namespace for this (not Helm-managed); without the IAM one the staff API
  # cannot look up the login provider and the portal loops back to its home screen after sign-in. New Dev also aliases
  # commons-services-keymanager, which OpenG2P Commons develop.340 does not run.
  local svc
  for svc in auditmanager awe cm-api cm-partner-api iam-staff-portal-api master-data-api pm-partner-api \
             pm-staff-portal-api; do
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata: {name: commons-services-$svc, namespace: $ns, labels: {oan.org/alias-of: commons}}
spec: {type: ExternalName, externalName: commons-services-$svc.commons.svc.cluster.local, ports: [{port: 80}]}
EOF
  done
  if [[ "$name" == cropsown ]]; then
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata: {name: awe, namespace: $ns, labels: {oan.org/alias-of: commons}}
spec: {type: ExternalName, externalName: commons-services-awe.commons.svc.cluster.local, ports: [{port: 80}]}
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
