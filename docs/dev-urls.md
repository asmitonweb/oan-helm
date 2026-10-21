# Development wildcard URLs

The dev environment uses `<service>.development.oanstaging.com`. New chart
version **`1.0.0-dev.4`** contains the new URL defaults and shared Gateway settings;
older archives retain their historical configuration.

The migration keeps installed chart/image versions intact using URL-only private
values and the compatibility post-renderer. Selecting a new chart is a separate
review: installing new chart defaults must not replace current live application
images or settings accidentally. Current live results are recorded in
`releases/live-domain-migration.json`.

The 21 October Crop/Livestock routing repair and follow-up checks are recorded in
[`live-registry-routing-20261021.json`](../releases/live-registry-routing-20261021.json).
Their later revision-16 deployments had restored old hosts with the `internal`
Gateway while legacy browser redirects still selected the canonical URLs.
Both existing releases now use revision 17 with their original chart versions,
images, resource names and Helm ownership.

| Service | Canonical URL |
| --- | --- |
| keycloak | `https://keycloak.development.oanstaging.com` |
| iam | `https://staff-iam.development.oanstaging.com` |
| agentIam | `https://agent-iam.development.oanstaging.com` |
| staffPortal | `https://staff-portal.development.oanstaging.com` |
| iamUi | `https://iam-staff-ui.development.oanstaging.com` |
| awe | `https://awe.development.oanstaging.com` |
| masterData | `https://master-data.development.oanstaging.com` |
| masterDataUi | `https://master-data-ui.development.oanstaging.com` |
| consent | `https://consent-manager.development.oanstaging.com` |
| consentPartner | `https://consent-manager-partner.development.oanstaging.com` |
| partnerManagement | `https://partner-management.development.oanstaging.com` |
| partnerManagementApi | `https://partner-management-partner-api.development.oanstaging.com` |
| odk | `https://odk-central.development.oanstaging.com` |
| minio | `https://minio-farmer.development.oanstaging.com` |
| minioConsole | `https://minio-console.development.oanstaging.com` |
| audit | `https://auditmanager.development.oanstaging.com` |
| esignet | `https://esignet.development.oanstaging.com` |
| farmer | `https://farmer-registry.development.oanstaging.com` |
| farmerStaff | `https://staff-farmer.development.oanstaging.com` |
| farmerPartner | `https://partner-farmer.development.oanstaging.com` |
| farmerId | `https://idgenerator-farmer.development.oanstaging.com` |
| cropsown | `https://crop-registry.development.oanstaging.com` |
| cropsownStaff | `https://staff-crop.development.oanstaging.com` |
| cropsownPartner | `https://partner-crop.development.oanstaging.com` |
| livestock | `https://livestock-registry.development.oanstaging.com` |
| livestockStaff | `https://staff-livestock.development.oanstaging.com` |
| livestockPartner | `https://partner-livestock.development.oanstaging.com` |
| livestockId | `https://idgenerator-livestock.development.oanstaging.com` |

Connectors use `connector-farmer-registry.development.oanstaging.com`,
`connector-cropsown-registry.development.oanstaging.com` and
`connector-livestock-registry.development.oanstaging.com`. The shared dashboard is
`oan-dashboard.development.oanstaging.com`; Kafka UI is
`kafka.development.oanstaging.com`. Preserve their existing access restrictions.

The environment has one wildcard DNS record and certificate, Nginx forwards to
Istio, and public VirtualServices use `istio-system/development`. Rancher and
Jenkins retain their existing management URLs. Exact DNS records override the
wildcard and must be checked when troubleshooting unexpected destinations.

## Login and application settings

The staff issuer is `https://keycloak.development.oanstaging.com/realms/staff`.
Application cookies use `.development.oanstaging.com`. Exact client redirects,
web origins, logout URLs, IAM login-provider records and application links must
be migrated together. Users must sign in again; old tokens may carry the former
issuer. Internal Service/JWKS/database addresses retain their existing namespaces.

The URL overlays under `environments/dev/values/` are public configuration only.
Saved private lists, clients and custom environment values require reconciliation;
replacing an entire list can discard existing settings. The legacy compatibility
renderer migrates literal URLs and encoded configuration, retains private/test
route gateways, and can suppress initialization Jobs for this URL-only operation.
Use `--no-hooks` and `--post-renderer-args --skip-initialization-jobs` only for the
reviewed URL migration, not as a general substitute for required initialization.

## Cutover and recovery

Both URL schemes remain available during completion of the migration. The
`*-development.oanstaging.com` records and original TLS certificates are restored.
HTML GET/HEAD browser navigation gets a temporary 307 redirect to the matching
canonical hostname, preserving path and query. API/JSON requests and POSTs are
proxied through temporary environment-owned aliases without changing method,
body or original Host. The MinIO object API always proxies, including browser
requests, to preserve signed download URLs. Keycloak continues to advertise the
new issuer.

The compatibility configuration is in `environments/dev/legacy/`; refresh its
aliases when canonical service routing changes. Retain old DNS/TLS and renew the
legacy certificates until the user explicitly confirms completion. Do not remove
compatibility on a timer. Other servers and Rancher/Jenkins management URLs remain
outside this change. Private backups retain the exact pre-cutover records and
identity/release settings for recovery.

ODK also retains `odk.commons-dev.oanstaging.com` as a proxy alias for existing
Enketo survey references. Its existing Commons wildcard Nginx/TLS configuration
forwards the original Host, so both the legacy Gateway and ODK VirtualService
must list this hostname. `prepare-legacy-compatibility.py` retains it whenever
the canonical ODK route is present. On 21 October, the missing alias caused
Farmer form retrieval to return 404; adding only these two host entries restored
authenticated formList, form XML and all four media downloads. Canonical URLs
and document storage were preserved; no Farmer code or form republish was needed.

The migration does not enable Aggregation, DA or unavailable components. Reserved
future hostnames are not evidence of running services. Use the
[service onboarding and enablement guide](service-onboarding.md) for new services.

## Preventing a deployment from restoring old routes

The OAN charts from dev.4 onward already select the canonical hosts and shared
Gateway. Keep the current release name and namespace when upgrading in Rancher;
reconcile private saved values before changing charts or images.

Application-repository deployment settings are a separate source of overrides.
At inspection, Crop's `ci/deploy-crop-dev.sh` explicitly writes old public hosts
after reading saved release values. Livestock's `Jenkinsfile` selects
`helm/openg2p-livestock-registry/values-new-dev.yaml`, which also contains old
hosts. Merely saving corrected values in Rancher cannot override those inputs.
Application CI was outside the authorized chart-repository scope and was not
changed. **Those older Jenkins deployments can still revert this repair** until
their deployment inputs adopt the canonical environment profile/renderer.

For Crop, the existing script's environment inputs must select
`REGISTRY_HOST=crop-registry.development.oanstaging.com`,
`STAFF_API_HOST=staff-crop.development.oanstaging.com`,
`PARTNER_API_HOST=partner-crop.development.oanstaging.com`,
`KEYCLOAK_URL=https://keycloak.development.oanstaging.com`,
`MINIO_HOST=minio-farmer.development.oanstaging.com`,
`STAFF_IAM_URL=https://staff-iam.development.oanstaging.com`, and
`COOKIE_DOMAIN=.development.oanstaging.com`. The public VirtualServices must
also select `istio-system/development`; changing hostnames alone is insufficient.
Livestock needs the corresponding canonical values from
[`environments/dev/values/livestock.yaml`](../environments/dev/values/livestock.yaml).
Review these URL profiles against saved private configuration rather than
replacing whole custom lists. Do not expose private dashboard/test routes.

Before any deployment, inspect the rendered public hosts, Gateway and image
diff. For a legacy chart, retain the URL compatibility post-renderer. URL-only
repairs must suppress initialization Jobs as well as hooks: Jobs already cleaned
up by TTL are recreated by Helm even if their manifests are unchanged. In the
21 October repair six such ordinary initialization Jobs were recreated and
completed; database seed hooks did not run, and release Secret values and the
synthetic fixtures remained unchanged. Retain the private release backup and
assess initialization/migration behavior before any future upgrade.

After deployment, run the independent public routing regression:

```sh
python scripts/check-registry-public-urls.py
```

It performs 14 credential-free GET requests and 28 assertions against both
registries: canonical UI/API responses, temporary browser redirects with path
and query preservation, and old JSON/API proxy compatibility. It must pass in
addition to internal registry/data tests. A missing route or mismatched response
exits nonzero. It is also a preflight in the automated staff regression; it does
not itself prevent a deployment or reconcile cluster resources.

For a real browser check through the shared IAM/Keycloak login form, install
Playwright/Chromium as for the partner browser test, then run:

```sh
python scripts/test-registry-public-browser.py --output .build/registry-browser
```

This checks anonymous navigation, including the expected `/api/me` 401 that
starts sign-in. It does not submit credentials or prove an authenticated registry
session. CI chart validation remains independent of live cluster reachability.

The dev Commons renderer also preserves the
[Partner Management session cookie guard](partner-session-cookie-guard.md).
It selects dev cookies when a staging parent-domain cookie has the same name.
Ship the renderer with `partner_session_guard.py` and
`partner-session-cookie-guard.cjs`. The live repair was a guarded Deployment
patch; the current Helm revision does not contain it until reconciled through
the updated renderer. Keep this integration on subsequent dev upgrades.
