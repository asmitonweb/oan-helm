# Environments: New Dev and staging

Readings of 5 November 2026, 20:45 to 20:55 UTC. Source for every table unless stated: live reading
(`kubectl get ns,virtualservice,gateway -A`, `helm list -A`) and repository files at `main` commit `7db1f6a`.

## 1. Overview

| Item | New Dev | Staging |
| --- | --- | --- |
| Purpose | Integration environment; every merge to `develop` deploys here | Rehearsal of promoted charts; a merge to `staging` promotes the chart `develop` already built |
| Cluster | One node, RKE2 v1.35.8, Rancher 2.15.1 | One node, RKE2 v1.33.6, Rancher 2.12.3 |
| Public host pattern | `<name>.development.oanstaging.com` | `<name>.oanstaging.com` |
| Istio gateway for public hosts | `istio-system/development` (host `*.development.oanstaging.com`) | `istio-system/staging` (host `*.oanstaging.com`) |
| Old host names | Retired: since 9 November 2026 the `<name>-development.oanstaging.com` records are gone from Route 53 and those names reach staging through the `*.oanstaging.com` wildcard. The `istio-system/development-legacy` gateway and `environments/dev/legacy/` remain only as a record | None observed |
| Host reverse proxy | nginx file `oan-development-wildcard.conf` with server name `*.development.oanstaging.com` | nginx, one file per host in `/etc/nginx/sites-enabled/` (no file contains `*.oanstaging.com`) |
| Repository values | `environments/dev/` | `environments/staging/` |

Sources: live readings of nodes, gateways and `/etc/nginx/sites-enabled`; `environments/dev/endpoints.yaml`,
`environments/staging/endpoints.yaml`.

Not verified: the staging wildcard nginx site. The repository holds the proposal
`environments/staging/ingress/nginx.conf` (its header says "staging: confirm"). On 5 November 2026 the staging
host had only per-host files. See [operations-runbook.md](operations-runbook.md), section 7.

## 2. Namespaces and Helm release names

| Part | Release name | New Dev namespace | Staging namespace |
| --- | --- | --- | --- |
| Commons base | `commons` | `commons` | `commons` |
| Commons services | `commons-services` | `commons` | `commons` |
| Shared dashboard | `oan-dashboards` | `commons` | `commons` |
| Farmer registry | `farmer-registry` | `farmer` | `farmer` |
| Farmer dashboard | `farmer-registry-dashboard` | `farmer` | `farmer` |
| Farmer connector | `farmer-registry-connector`, `farmer-connector-credentials` | `farmer` | `farmer` |
| Crop sown registry | `cropsown-registry` | `crop` | `crop` |
| Crop sown dashboard | `cropsown-registry-dashboard` | `crop` | not installed |
| Crop sown connector | `cropsown-connector` | `crop` | `crop` |
| Livestock registry | `livestock-registry` | `livestock` | `live` |
| Livestock dashboard | `livestock-registry-dashboard` | `livestock` | `live` |
| Livestock connector | `livestock-connector` | `livestock` | `live` |
| Development Agent registry | `da-registry` | `da-registry` | `da-registry` |
| Logs | `loki`, `otel-agent`, `otel-gateway`, `grafana` (New Dev only) | `observability` | `observability` |

Note the Livestock namespace: `livestock` on New Dev and `live` on staging. Any command must use the
namespace of the environment it targets.

## 3. Public hostnames

Source: live reading of VirtualServices (`kubectl get virtualservice -A`). A dash means no VirtualService was
found for it.

### Registries

| Registry | Part | New Dev host | Staging host |
| --- | --- | --- | --- |
| Farmer | Staff user interface | `farmer-registry.development.oanstaging.com` | `farmer-registry.oanstaging.com` |
| Farmer | Staff API | `staff-farmer.development.oanstaging.com` | `staff-farmer.oanstaging.com` |
| Farmer | Partner API | `partner-farmer.development.oanstaging.com` | `partner-farmer.oanstaging.com` |
| Farmer | Id generator | `idgenerator-farmer.development.oanstaging.com` | `idgenerator-farmer.oanstaging.com` |
| Farmer | Connector | `connector-farmer-registry.development.oanstaging.com` | `connector-farmer-registry.oanstaging.com` |
| Farmer | Dashboard | `farmer-registry-dashboard.development.oanstaging.com` | `farmer-registry-dashboard.oanstaging.com` |
| Crop sown | Staff user interface | `crop-registry.development.oanstaging.com` | `crop-registry.oanstaging.com` |
| Crop sown | Staff API | `staff-crop.development.oanstaging.com` | `staff-crop-registry.oanstaging.com` |
| Crop sown | Partner API | `partner-crop.development.oanstaging.com` | `partner-crop-registry.oanstaging.com` |
| Crop sown | Id generator | `idgenerator-crop.development.oanstaging.com` | internal host only |
| Crop sown | Connector | `connector-cropsown-registry.development.oanstaging.com` | `connector-cropsown-registry.oanstaging.com` |
| Crop sown | Dashboard | `cropsown-registry-dashboard.development.oanstaging.com` | - |
| Livestock | Staff user interface | `livestock-registry.development.oanstaging.com` | `livestock-registry.oanstaging.com` |
| Livestock | Staff API | `staff-livestock.development.oanstaging.com` | `staff-livestock.oanstaging.com` |
| Livestock | Partner API | `partner-livestock.development.oanstaging.com` | `partner-livestock.oanstaging.com` |
| Livestock | Id generator | `idgenerator-livestock.development.oanstaging.com` | `idgenerator-livestock.oanstaging.com` |
| Livestock | Connector | `connector-livestock-registry.development.oanstaging.com` | `connector-livestock.oanstaging.com` |
| Livestock | Dashboard | `livestock-registry-dashboard.development.oanstaging.com` | `livestock-registry-dashboard.oanstaging.com` (a second host, `livestock-dashboard.oanstaging.com`, also exists) |
| Development Agent | Staff user interface | `da-registry.development.oanstaging.com` | - |
| Development Agent | Staff API | `staff-da-registry.development.oanstaging.com` | - |
| Development Agent | Partner API | `partner-da-registry.development.oanstaging.com` | - |
| Development Agent | Id generator | `idgenerator-da.development.oanstaging.com` | `idgenerator-da.oanstaging.com` |

Drift: the Crop sown host names on staging (`staff-crop-registry`, `partner-crop-registry`) differ from the names
in `environments/staging/endpoints.yaml` (`staff-crop`, `partner-crop`). Livestock follows the file on staging
for the staff and partner APIs. The Crop sown staging VirtualServices use the namespace gateway `crop/internal`,
not `istio-system/staging`.

### Commons services

| Service | New Dev host | Staging host |
| --- | --- | --- |
| Keycloak | `keycloak.development.oanstaging.com` | `keycloak.oanstaging.com` |
| Staff portal | `staff-portal.development.oanstaging.com` | `staff-portal.oanstaging.com` |
| Identity staff API (also the Partner Management staff API on New Dev) | `staff-iam.development.oanstaging.com` | `staff-iam.oanstaging.com` |
| Identity staff user interface | `iam-staff-ui.development.oanstaging.com` | `iam-staff-ui.oanstaging.com` |
| Partner Management user interface | `partner-management.development.oanstaging.com` | `partner-management.oanstaging.com` |
| Partner Management partner API | `partner-management-partner-api.development.oanstaging.com` | `partner-management-partner-api.oanstaging.com` |
| Approval Workflow Engine | `awe.development.oanstaging.com` | `awe.oanstaging.com` |
| Master Data API and user interface | `master-data.development.oanstaging.com`, `master-data-ui.development.oanstaging.com` | `master-data.oanstaging.com`, `master-data-ui.oanstaging.com` |
| Consent Manager (staff, partner, partner portal) | `consent-manager.`, `consent-manager-partner.`, `consent-partner-portal.` + `development.oanstaging.com` | same names + `oanstaging.com` |
| Aggregation | `aggregation.development.oanstaging.com` | `aggregation.oanstaging.com` |
| ODK Central | `odk-central.development.oanstaging.com` | `odk-central.oanstaging.com` |
| MinIO (files, console) | `minio-farmer.development.oanstaging.com`, `minio-console.development.oanstaging.com` | `minio-farmer.oanstaging.com`, `minio-console.oanstaging.com` |
| Audit manager | `auditmanager.development.oanstaging.com` | `auditmanager.oanstaging.com` |
| eSignet | `esignet.development.oanstaging.com` | `esignet.oanstaging.com` |
| Shared dashboard (private) | `oan-dashboard.development.oanstaging.com` | `oan-dashboard.oanstaging.com` |
| Logs (Grafana) | `logs.development.oanstaging.com` | - |

## 4. Which Jenkins job deploys what

Source: Jenkins reading of the job tree, job configuration and the latest console text; `Jenkinsfile`,
`ci/pipelines/dev.groovy` and `ci/pipelines/staging.groovy` of each registry at `origin/develop`.

Every registry repository has one Jenkins multibranch job. Its `Jenkinsfile` loads `ci/pipelines/staging.groovy`
for the branch `staging` and `ci/pipelines/dev.groovy` for every other branch. The branch source includes only
the branches `dev`, `main`, `develop` and `staging`. Deploy stages run on the agent labelled `oan-ci-deploy`
(node `oan-ci-deploy-agent-1`, the one that reaches the clusters); build stages run on any build agent.

| Registry | Jenkins job | `develop` branch deploys to | `staging` branch deploys to | Credential name for the cluster |
| --- | --- | --- | --- | --- |
| Farmer | `Gen2-Package/farmer-registry` | New Dev, release `farmer-registry`, namespace `farmer` | staging, same names | `farmer-dev-kubeconfig`; `staging-farmer-kubeconfig` |
| Crop sown | `Gen2-Package/cropsown-regsitry` | New Dev, release `cropsown-registry`, namespace `crop` | staging, namespace `crop`, through `scripts/ci/deliver_staging.sh` | `crop-dev-kubeconfig`; `staging-rke2-kubeconfig` |
| Livestock | `Gen2-Package/livestock-registry` | New Dev, namespace `livestock` | staging, namespace `live`, through `deliver_staging.sh` | `livestock-dev-kubeconfig`; `staging-rke2-kubeconfig` |
| Development Agent | `DA/da-registry` | New Dev, namespace `da-registry` | staging, namespace `da-registry`, through `deliver_staging.sh` | `da-registry-newdev-kubeconfig`; `staging-rke2-kubeconfig` |
| Registry seed data | `Gen2-Package/openg2p-data` | `develop` only (no `staging` branch) | - | Not verified |
| Master Data | `MDS/mds` | job exists for `develop` and `staging`; last runs started by timer | - | Not verified: the target of each branch |
| Registry dashboards | inside the registry jobs on New Dev (`ci/dashboard/deploy-ui.sh`) | New Dev | staging script `scripts/ci/deliver_staging_dashboards.sh` | - |
| Farmer connector on staging | script `scripts/ci/deliver_staging_farmer_connector.sh` | - | staging | - |
| Commons services | `ci/jenkins/staging-commons.Jenkinsfile` on `main` (the Jenkins job is still to be created; until then the last staging upgrade, revision 16 on 5 Nov 2026, was by hand) | - | staging, release `commons-services`, namespace `commons`, through `scripts/ci/deliver_staging_commons.sh` | `staging-commons-deployer-kubeconfig` (ServiceAccount `commons/commons-deployer`, `environments/staging/rbac/commons-deployer-rbac.yaml`); `staging-commons-secret-values` |

### Commons base on staging

Both Commons deliveries run as ServiceAccount `commons/commons-deployer`
(`environments/staging/rbac/commons-deployer-rbac.yaml`, applied once by the cluster admin). The registry
deployer `live/livestock-ci` has no rights in `commons`. This ServiceAccount has rights in `commons` only, but there
it can read every Secret, including the Keycloak and Postgres admin passwords. Helm keeps its release revisions as
Secrets and the charts own password Secrets, so this cannot be narrowed. The file explains how to build the
kubeconfig for Jenkins credential `staging-commons-deployer-kubeconfig` without printing the token.

Before Commons services, every build of `main` runs `scripts/ci/deliver_staging_commons_base.sh` for the base
release `commons` (chart `openg2p-commons-base`). No parameters, no click.

1. `environments/staging/commons-base.chart` pins `<version> <sha256>`. The archive is downloaded from the OpenG2P
   Helm repository and checked against the sha256, because OpenG2P can republish a version.
2. The release keeps its saved values. They are a full copy of the chart defaults with the staging passwords and
   cannot be rebuilt from git. `environments/staging/values/commons-base.yaml` is applied over them with
   `--reuse-values`.
3. `--reuse-values` does not pick up a new chart version's defaults, so the script delivers only the version the
   release already runs. It refuses a pin with another version. A version change is a reviewed manual upgrade,
   after which the pin is moved to match.
4. ConfigMap `commons-base-delivery` records the pin, the archive sha256 and the sha256 of the overlay. If staging
   already runs exactly that, the script stops. Otherwise it runs a server-side dry run, then
   `helm upgrade --reuse-values --atomic --wait`, then writes the record.

The first delivery applies the overlay as it is on `main`, including the Kafka controller heap and memory limit
(#153).

### Commons services on staging

Every build of `main` runs `scripts/ci/deliver_staging_commons.sh`. Staging follows `environments/staging/commons-services.chart`
(the chart version, an archive in `repository/`) and `environments/staging/values/commons-services.yaml`. No
parameters, no click.

1. Checks the pinned archive against `repository/SHA256SUMS`.
2. Compares the pin and the sha256 of the values and secret files with ConfigMap `commons-services-delivery` in
   namespace `commons`, the record of the last successful delivery. If they match, it stops. Otherwise it delivers,
   so a failed delivery is retried by the next build of `main`.
3. Fails if the release's saved values hold a key that neither the staging values nor the secret values file
   sets. `--reset-values` would drop it. The merged values are rendered by `helm template` of a throwaway chart,
   so the deploy agent needs no YAML library. Only key names are printed.
4. Runs a server-side dry run, then `helm upgrade --reset-values --atomic --wait`, then writes the record.

The first delivery is not a no-op. It applies `master-data.geoSeed.load.samples: true` (#151), so the geo-seed hook
loads the pack's sample people. Until staging Master Data is on the pack's geography, the hook warns that their
place codes are not published.

The secret values file (Jenkins secret-file credential `staging-commons-secret-values`) holds the values that are
not kept in git: `keymanager.p12KeystorePass` and
`odk-central.odk-central-enketo.{enketoSecret,enketoLessSecret}`. Create it once from the saved values on the
staging host (JSON is valid YAML for Helm), then upload it as that credential and delete the file:

```
sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml helm get values commons-services -n commons -o json | python3 -c '
import json, sys
v = json.load(sys.stdin)
out = {"keymanager": {"p12KeystorePass": v["keymanager"]["p12KeystorePass"]},
       "odk-central": {"odk-central-enketo": {k: v["odk-central"]["odk-central-enketo"][k]
                                               for k in ("enketoSecret", "enketoLessSecret")}}}
print(json.dumps(out))' > commons-secret-values.yaml
```

Not verified: which job or person runs `deliver_staging_dashboards.sh` and
`deliver_staging_farmer_connector.sh`. No Jenkins job in the job tree references them. They are scripts that
run from a checkout of this repository.

Latest builds read on 5 November 2026:

| Job and branch | Build | Result | Started by |
| --- | --- | --- | --- |
| Farmer `develop` | 150 | aborted (timeout exceeded) | push event |
| Farmer `staging` | 28 | success | user `admin` |
| Crop sown `develop` | 255 | success | push event |
| Crop sown `staging` | 28 | failure (upgrade timed out, rollback also failed) | user `admin` |
| Livestock `develop` | 188 | aborted by `admin` | branch indexing |
| Livestock `staging` | 11 | success | user `admin` |
| Development Agent `staging` | 6 | failure (post-upgrade hook timed out, rolled back) | user `admin` |

The folder `Gen2-Package` has a "no automatic triggers" property for branches matching `^(develop|staging)$`
with strategy `NONE`. Even so, recent `develop` builds were started by push events. Not verified: exactly which
events start a build today.

## 5. Staging state at the time of reading

| Registry | Staging state |
| --- | --- |
| Farmer | Release deployed (revision 4, chart rc.813) |
| Livestock | Release deployed (revision 57, chart rc.432) |
| Crop sown | Release `failed` at revision 21; three new pods in `ImagePullBackOff`; the older pods from 17 days ago still run; see [operations-runbook.md](operations-runbook.md) section 5 |
| Development Agent | Release revision 3 (a rollback to revision 1). Deployments: only `da-registry-id-generator`. A seed job `da-registry-db-seed` has run for more than 30 minutes in `Init:1/2` |

## 6. Where New Dev and staging differ

See [versions.md](versions.md) section 6 for versions. In addition:

| Difference | New Dev | Staging |
| --- | --- | --- |
| Approval policy keys in the Approval Workflow Engine database | 36 keys, including `registry.change_request.da`, `registry.intake_form.da`, `registry.change_request.cropsown-farmer.default` and the `livestock-farmer` pair | 25 keys; no Development Agent policy and no `cropsown-farmer` policy; extra keys named `...stgserver_cropsown` |
| Partner ids registered in Partner Management | 20 | 8 |

Source: live read-only queries of the tables `approval_policy` (database `awe`) and `pm_partners` (database
`partner_management`) in `commons-postgresql-0`. The partner ids are listed in
[integration-contracts.md](integration-contracts.md).
