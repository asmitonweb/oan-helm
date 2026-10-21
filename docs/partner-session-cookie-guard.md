# Dev Partner Management session cookie guard

Deployed on 21 October 2026 to the existing `commons-services` release's
`commons-services-pm-staff-portal-ui` Deployment in namespace `commons`.
The upstream image remains `openg2p/partner-management-staff-portal-ui:1.0.2`.

## Failure and behavior

A staging `X-Access-Token` cookie scoped to `.oanstaging.com` is also sent to
`partner-management.development.oanstaging.com`. With both staging and dev
cookies, Next.js can select the staging value and IAM correctly returns
`G2P-AUT-401: Unknown Issuer. https://keycloak.oanstaging.com/realms/staff`.
Creating the parent cookie after a valid dev session reproduced this failure.

The Node preload selects access and ID cookies whose decoded issuer exactly
matches `https://keycloak.development.oanstaging.com/realms/staff`, before
Next.js collapses duplicate names. This selects a token; it does not authenticate
it. The unchanged token still passes through IAM's signature and claims checks.
Foreign-only access cookies become missing credentials, invoking the existing
dev sign-in flow. Browser cookies are neither deleted nor rewritten.

## Deployment and reconciliation

`scripts/partner_session_guard.py` prepares a scoped, additive template change:

- ConfigMap `commons-services-pm-session-cookie-guard`, owned by the existing
  `commons-services` Helm release, with a read-only JavaScript file mount.
- `NODE_OPTIONS` appends `--require=/opt/oan/session-cookie-guard.cjs`.
- `OAN_SESSION_COOKIE_GUARD=1` and `OAN_SESSION_EXPECTED_ISSUER` select dev.
- A SHA256 pod-template annotation rolls the UI when the module changes.

The live repair created that ConfigMap and patched only the UI pod template
after API-server dry runs. A JSON Patch `test` guarded against concurrent edits.
No Helm upgrade or initialization jobs were run. The Deployment completed its
rollout, with one ready replica. Images, Secret references, IAM providers,
resources and other workload specifications were preserved.

The live patch is **not recorded in the existing Helm revision**. Future dev
Commons upgrades must use the updated `scripts/dev-domain-post-renderer.py`
to retain it, or equivalent reviewed chart support. Ship the renderer together
with both sibling files `partner_session_guard.py` and
`partner-session-cookie-guard.cjs`; copying the renderer alone is insufficient.
This guard explicitly rejects a PM deployment configured for another issuer.
Do not apply it to staging.

## Validation

Run:

```sh
node --test scripts/test-partner-session-cookie-guard.cjs
python scripts/test_partner_session_guard.py
python scripts/test_dev_domain.py
python scripts/test_legacy_compatibility.py
```

Seven Node tests and four deployment/renderer tests exercise cookie order,
malformed and foreign sessions, exact issuer matching, unchanged signature
bytes, the HTTP request hook, preservation and full-render idempotence.

The exact released UI image was also run locally against an HTTP IAM fixture:
the original returned 401 for the collision; the guarded UI passed six cases.
That fixture does not establish cryptographic validation.

Actual dev Chrome tests after deployment established:

- Fresh login: `/api/me` 200.
- Parent-domain staging cookie before or after dev cookies: `/api/me` 200.
- Requests and Partners API lists: 200, Requests page rendered.
- Foreign-only cookie: `G2P-AUT-LOGIN-REQUIRED`, followed by successful dev login.
- Parent-domain test cookie remained unchanged after that login.
- A token naming the correct issuer but with a corrupted signature: IAM 401
  `BadSignatureError`, proving the selector does not bypass authentication.

Tests used the existing approved dev account and read-only list/profile calls.
No partners, roles, staging resources or business records were modified.

## Rollback and evidence

The operator workspace retains the original template, forward and inverse JSON
patches, ConfigMap and sanitized results under
`Temp/partner-management-dev-20261021/`. Credentials and token values were not
saved in the test output. The rollback patch tests that the current template
still equals the deployed candidate, then restores the original template.

From the same operator workspace, rollback with:

```powershell
py -3.14 Temp/partner-management-dev-20261021/deploy-guard.py rollback
py -3.14 Temp/partner-management-dev-20261021/deploy-guard.py status
```

Review any drift if the comparison fails; do not force a replacement. Only after
the original pods are ready may the newly created guard ConfigMap be removed.
Also remove the renderer integration if intentionally reverting the fix in
source. No rollback was needed for the successful dev rollout.
