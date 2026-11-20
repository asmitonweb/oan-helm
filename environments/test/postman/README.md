# Agri Stack Composite: test collection

A bank's view of OpenG2P Agri Stack on registry-test, as requests you can run one by one. It replays OpenG2P's install test (`agri-stack/scripts/test_install.py`) in OpenG2P's reference topology: the **Exchange** (`agrix`: the Composite and its own Commons) and one **department** per registry (`farmer`, `crop`, `livestock`), each with its own Keycloak, Partner Management and Consent Manager.

**Run the folders in order:** 0 Setup → 1 Exchange → 2 Departments release data → 3 Bank onboarding (Exchange) → 4 Farmer profile query → 5 Registries refuse the bank.

| Folder | What it does |
| --- | --- |
| 0 Setup | Loads the signing library (jsrsasign, cdnjs), gets the Exchange's Partner Management staff token, makes the test bank's EC P-256 key the first time |
| 1 Exchange | OpenG2P's Exchange check: Composite ping, use cases, the farmer-profile use case (purpose and scopes per registry), JWKS, internal API not public, Exchange Consent Manager keys, the Composite's key in the Exchange's Partner Management, partner portal and Composite console up |
| 2 Departments release data | In each department's own Partner Management: checks it serves the Composite's key, gives the Composite a scope policy for its registry, approves, waits until served (OpenG2P install step 3) |
| 3 Bank onboarding (Exchange) | Onboards `partner_id` at the Exchange with its key and use-case policy, approves (when `auto_approve=true`), waits until served |
| 4 Farmer profile query | Signed query with the farmer's consent (pass: signed answer, farmer ok), the same query answered from the consent the Exchange Consent Manager stored (lookup), unknown farmer, no consent for another farmer (refused), tampered body (refused) |
| 5 Registries refuse the bank | The bank calls each registry directly: each department must refuse, since only the Composite is its partner |

**Before the first run:**
1. Set the four secret variables `exchange_client_secret`, `farmer_client_secret`, `crop_client_secret` and `livestock_client_secret`. Each is the `client_secret` key of Secret `commons-services-staff-portal` in that organisation's namespace (`agrix`, `farmer`, `crop`, `livestock`).
2. Leave the key variables empty. They are generated on the first run and kept as current values only.

**Changing environment:** every organisation is `<namespace>.{{parent_domain}}`, and each has its own Keycloak and Partner Management URL variables. Registry URLs, controllers, record types and search fields each have their own variable.

**Source:** `environments/test/postman/build.py` in `asmitonweb/oan-helm` (branch `agri-stack-composite`) writes this collection and its environment. Edit the script, not the JSON.
