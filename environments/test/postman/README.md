# Agri Stack Composite: test collection

A bank's view of OpenG2P Agri Stack on registry-test, as requests you can run one by one. It replays OpenG2P's install test (`agri-stack/scripts/test_install.py`).

**Run the folders in order:** 0 Setup → 1 Composite → 2 Partner onboarding → 3 Farmer profile query → 4 Registries.

| Folder | What it does |
| --- | --- |
| 0 Setup | Loads the signing library (jsrsasign, cdnjs), gets a Partner Management staff token, makes the test partner's EC P-256 key the first time |
| 1 Composite | Use cases, JWKS, internal API not public, Composite key in Partner Management |
| 2 Partner onboarding | Onboards `partner_id` with its key and use-case policy, gives it a scope policy per registry, approves (when `auto_approve=true`), waits until Partner Management serves them |
| 3 Farmer profile query | Signed query with consent (pass), unknown farmer, no consent, tampered body |
| 4 Registries (DCI) | Farmer, Crop Sown and Livestock searched directly, with the partner's consent |

**Before the first run:**
1. Set `client_secret` (secret) in the environment. It is the `client_secret` key of Secret `commons-services-staff-portal` in namespace `commons`.
2. Leave the key variables empty. They are generated on the first run and kept as current values only.

**Changing environment:** every host is built from `base_domain`. Registry URLs, controllers, record types and search fields each have their own variable.

**Source:** `environments/test/postman/build.py` in `asmitonweb/oan-helm` (branch `agri-stack-composite`) writes this collection and its environment. Edit the script, not the JSON.
