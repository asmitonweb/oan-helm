#!/usr/bin/env python3
"""Build the Agri Stack test collection and its registry-test environment (Postman v2.1 JSON).

The collection replays OpenG2P's install test (agri-stack scripts/test_install.py) as requests a person can run one
by one, in OpenG2P's reference topology: the Exchange (Composite, its own Commons) and one department per registry
(Farmer, Crop Sown, Livestock), each with its own Keycloak, Partner Management and Consent Manager. Folders: Composite
discovery; each department releasing its registry's data to the Composite (a scope policy for PARTNER_AGRI_COMPOSITE in
that department's Partner Management); the test bank onboarded at the Exchange with its use-case policy; the signed
farmer-profile query and its refusals; and the registries refusing the bank when it bypasses the Exchange. Everything
is a variable; the only secrets are the four Partner Management client secrets (exchange_client_secret and
<department>_client_secret, type secret, never stored here).

Signing: partner requests are ES256 (EC P-256) detached JWS over the canonical JSON of {header, message}, as the
OpenG2P services expect (sorted keys, compact). The "Load signing library" request fetches jsrsasign from cdnjs and the
scripts eval it; the partner key is generated on first run and kept in the environment's current values.

  python3 build.py            # writes agri-stack.postman_collection.json and registry-test.postman_environment.json
"""
import json
import pathlib
import uuid

HERE = pathlib.Path(__file__).resolve().parent
NS = uuid.UUID("6f1c2a52-6f0b-4a8e-9b1e-3c2b8a1d7e01")  # stable ids, so re-uploads update in place


def uid(name):
    return str(uuid.uuid5(NS, name))


# --- shared script code --------------------------------------------------------------------------------------------

# Loaded with eval(pm.collectionVariables.get("helpers_src")) by every script that signs or verifies.
HELPERS = r"""
var navigator = {}, window = {};
if (!pm.collectionVariables.get("jsrsasign_src")) { throw new Error("Run 0 Setup / Load signing library first"); }
eval(pm.collectionVariables.get("jsrsasign_src"));
var v = function (name) { return pm.variables.replaceIn(pm.variables.get(name) === undefined ? "" : "{{" + name + "}}"); };
var canonical = function (o) {
  if (o === null || typeof o !== "object") { return JSON.stringify(o); }
  if (Array.isArray(o)) { return "[" + o.map(canonical).join(",") + "]"; }
  return "{" + Object.keys(o).sort().filter(function (k) { return o[k] !== undefined; })
    .map(function (k) { return JSON.stringify(k) + ":" + canonical(o[k]); }).join(",") + "}";
};
var isoSeconds = function (d) { return d.toISOString().replace(/\.\d{3}Z$/, "+00:00"); };
var partnerKey = function () {
  var pem = pm.environment.get("partner_private_key_pem");
  if (!pem) { throw new Error("No partner key: run 0 Setup / Partner key first"); }
  return KEYUTIL.getKey(pem);
};
var signCompact = function (payloadStr) {
  var header = { alg: "ES256", typ: "JWT", kid: pm.environment.get("partner_kid") };
  return KJUR.jws.JWS.sign("ES256", JSON.stringify(header), payloadStr, partnerKey());
};
var signDetached = function (obj) {
  var p = signCompact(canonical(obj)).split(".");
  return p[0] + ".." + p[2];
};
var consentScopes = function () { return JSON.parse(pm.collectionVariables.get("consent_scopes") || "{}"); };
var makeConsent = function (subject) {
  // valid_from a minute back: the Composite refuses a consent whose valid_from is ahead of its own clock
  // (consent_not_yet_valid), and the caller's clock may run a little ahead of the server's.
  var now = new Date(Date.now() - 60000), until = new Date(now.getTime() + Number(v("consent_valid_days")) * 86400000);
  var scopes = consentScopes();
  var claims = {
    jti: uuid(), aud: v("partner_id"), subject_id: subject, purpose: { code: pm.collectionVariables.get("purpose") },
    grants: Object.keys(scopes).filter(function (c) { return scopes[c].length; })
      .map(function (c) { return { data_controller: c, data_scopes: scopes[c] }; }),
    fetch_type: "oneshot",
    validity: { valid_from: isoSeconds(now), valid_until: isoSeconds(until) },
    issued_at: isoSeconds(now)
  };
  return signCompact(canonical(claims));
};
var uuid = function () { return KJUR.crypto.Util.getRandomHexOfNbytes ? null : null; };
uuid = function () {
  var h = KJUR.crypto.Util.sha256(String(Math.random()) + Date.now()).substring(0, 32);
  return h.substring(0, 8) + "-" + h.substring(8, 12) + "-4" + h.substring(13, 16) + "-a" + h.substring(17, 20) + "-" + h.substring(20, 32);
};
var envelope = function (header, message) {
  return { signature: signDetached({ header: header, message: message }), header: header, message: message };
};
var verifyComposite = function (body) {
  var parts = ((body || {}).signature || "").split(".");
  if (parts.length !== 3) { return "MISSING"; }
  var full = parts[0] + "." + utf8tob64u(canonical({ header: body.header, message: body.message })) + "." + parts[2];
  var kid = JSON.parse(b64utoutf8(parts[0])).kid;
  var jwks = JSON.parse(pm.collectionVariables.get("composite_jwks") || "{\"keys\":[]}").keys;
  var jwk = jwks.filter(function (k) { return k.kid === kid; })[0];
  if (!jwk) { return "UNKNOWN KID " + kid; }
  return KJUR.jws.JWS.verify(full, KEYUTIL.getKey(jwk), ["ES256", "RS256"]) ? "valid" : "INVALID";
};
var staffApprove = function (requestId, done, org) {
  // org: "exchange" (default) or a department prefix (farmer, crop, livestock): whose Partner Management approves.
  org = org || "exchange";
  if (String(v("auto_approve")) !== "true") { console.log("approve request " + requestId + " in the " + org + " PM portal"); return done && done(); }
  pm.sendRequest({
    url: v(org + "_pm_staff_url") + "/partners/requests/" + requestId + "/approve", method: "POST",
    header: [{ key: "Authorization", value: "Bearer " + pm.collectionVariables.get(org + "_token") },
             { key: "Content-Type", value: "application/json" }],
    body: { mode: "raw", raw: JSON.stringify({ notes: "approved by the Agri Stack Postman collection" }) }
  }, function (err, res) {
    pm.test("request " + requestId + " approved", function () { pm.expect(err).to.equal(null); pm.expect(res.code).to.be.oneOf([200, 201]); });
    if (done) { done(); }
  });
};
var policyInput = function (o) {
  var body = { data_controller: o.data_controller || null, use_case: o.use_case || null,
    allowed_data_scopes: (o.scopes || []).slice().sort(), allowed_subject_id_types: v("subject_id_types").split(","),
    allowed_signing_algs: ["ES256"], max_validity_duration: v("policy_max_validity"), fetch_type: "oneshot",
    allow_partner_consents: o.partner_consents !== false };
  if (!o.use_case) { body.allowed_purposes = [pm.collectionVariables.get("purpose")]; }
  return body;
};
"""

COLLECTION_PRE = r"""
// Derived ids, recomputed before every request: PM keeps partners as PARTNER_<ID> (upper case, '-' -> '_').
var ref = function (id) { return "PARTNER_" + String(id).replace(/-/g, "_").toUpperCase(); };
pm.collectionVariables.set("partner_ref", ref(pm.variables.replaceIn("{{partner_id}}")));
pm.collectionVariables.set("composite_ref", ref(pm.variables.replaceIn("{{composite_id}}")));
"""


def js(code):
    return [line for line in code.strip("\n").split("\n")]


def event(listen, code):
    return {"listen": listen, "script": {"type": "text/javascript", "exec": js(code)}}


def url(raw):
    # A plain string: Newman reads an object with only "raw" as an empty URL.
    return raw


def bearer(org="exchange"):
    return {"type": "bearer", "bearer": [{"key": "token", "value": "{{%s_token}}" % org, "type": "string"}]}


def token_req(org, label):
    return req(f"{label}: staff token", "POST",
               "{{%s_keycloak_url}}/realms/{{staff_realm}}/protocol/openid-connect/token" % org,
               form=[("grant_type", "client_credentials"), ("client_id", "{{client_id}}"),
                     ("client_secret", "{{%s_client_secret}}" % org)],
               desc=f"Client-credentials token for the {label}'s Partner Management staff API. {org}_client_secret is a "
                    f"secret environment variable: key client_secret of Secret commons-services-staff-portal in the "
                    f"{label}'s namespace ({{{{{org}_namespace}}}}).",
               test=f"""
pm.test("token issued", function () {{ pm.response.to.have.status(200); }});
pm.collectionVariables.set("{org}_token", pm.response.json().access_token || "");
""")


def req(name, method, raw_url, *, body=None, form=None, pre=None, test=None, auth=None, desc="", headers=None):
    r = {"method": method, "header": list(headers or []), "url": url(raw_url), "description": desc}
    if body is not None:
        r["header"].append({"key": "Content-Type", "value": "application/json"})
        r["body"] = {"mode": "raw", "raw": body, "options": {"raw": {"language": "json"}}}
    if form is not None:
        r["body"] = {"mode": "urlencoded", "urlencoded": [{"key": k, "value": v} for k, v in form]}
    r["auth"] = auth or {"type": "noauth"}
    item = {"id": uid(name), "name": name, "request": r, "event": []}
    if pre:
        item["event"].append(event("prerequest", pre))
    if test:
        item["event"].append(event("test", test))
    return item


def folder(name, desc, items):
    return {"id": uid("folder " + name), "name": name, "description": desc, "item": items}


H = 'eval(pm.collectionVariables.get("helpers_src"));\n'

# --- 0 Setup -------------------------------------------------------------------------------------------------------

setup = folder("0 Setup", "Signing library, the Exchange's Partner Management staff token, and the test bank's key.", [
    req("Load signing library", "GET", "{{jsrsasign_url}}",
        desc="jsrsasign from cdnjs: ES256 signing and verification for the other requests' scripts.",
        test="""
pm.test("library downloaded", function () { pm.response.to.have.status(200); });
pm.collectionVariables.set("jsrsasign_src", pm.response.text());
"""),
    token_req("exchange", "Exchange"),
    req("Partner key (generated once) and what PM serves", "GET", "{{exchange_pm_partner_url}}/keys/{{partner_ref}}",
        desc="Generates the test partner's EC P-256 key on first run (environment current values only), then lists the "
             "keys Partner Management serves for the partner.",
        pre=H + """
if (!pm.environment.get("partner_private_key_pem")) {
  var kp = KEYUTIL.generateKeypair("EC", "secp256r1");
  pm.environment.set("partner_private_key_pem", KEYUTIL.getPEM(kp.prvKeyObj, "PKCS8PRV"));
  pm.environment.set("partner_public_key_pem", KEYUTIL.getPEM(kp.pubKeyObj));
  var d = new Date().toISOString().substring(0, 10).replace(/-/g, "");
  pm.environment.set("partner_kid", v("partner_id") + "-postman-" + d + "-" + KJUR.crypto.Util.sha256(String(Math.random())).substring(0, 4));
  console.log("new partner key, kid " + pm.environment.get("partner_kid"));
}
""",
        test="""
var keys = pm.response.code === 200 ? (pm.response.json().keys || []) : [];
var kid = pm.environment.get("partner_kid");
pm.collectionVariables.set("partner_key_served", String(keys.some(function (k) { return k.kid === kid; })));
pm.test("PM answers (404 = partner not onboarded yet)", function () { pm.expect(pm.response.code).to.be.oneOf([200, 404]); });
"""),
])

# --- 1 Composite -----------------------------------------------------------------------------------------------------

composite = folder("1 Exchange", "OpenG2P's Exchange check: what the Composite publishes (use cases, the "
                   "farmer-profile use case with its purpose and scopes per registry, its signing keys, no public "
                   "internal API), the Exchange Consent Manager's keys, the Composite's key in the Exchange's Partner "
                   "Management, the partner portal and the Composite console.", [
    req("Ping", "GET", "{{composite_url}}/ping", test='pm.test("up", function () { pm.response.to.have.status(200); });'),
    req("List use cases", "GET", "{{composite_url}}/composite/v1/use-cases",
        test="""
pm.test("lists the use case", function () {
  pm.response.to.have.status(200);
  pm.expect(pm.response.text()).to.include(pm.variables.replaceIn("{{use_case}}"));
});
"""),
    req("Get use case", "GET", "{{composite_url}}/composite/v1/use-cases/{{use_case}}",
        desc="Stores the use case's name@major, purpose and consent scopes per registry for the later requests.",
        test="""
pm.test("use case served", function () { pm.response.to.have.status(200); });
var d = pm.response.json(), declared = d.consent_scopes || {}, scopes = {};
Object.keys(declared).forEach(function (c) {
  var s = (declared[c].required || []).concat(declared[c].optional || []);
  scopes[c] = s.filter(function (x, i) { return s.indexOf(x) === i; }).sort();
});
pm.collectionVariables.set("use_case_ref", d.use_case || pm.variables.replaceIn("{{use_case}}"));
pm.collectionVariables.set("purpose", d.purpose || "");
pm.collectionVariables.set("consent_scopes", JSON.stringify(scopes));
pm.test("names a purpose and registries", function () {
  pm.expect(d.purpose).to.be.a("string").and.not.empty;
  pm.expect(Object.keys(scopes)).to.not.be.empty;
});
"""),
    req("Signing keys (JWKS)", "GET", "{{composite_url}}/.well-known/jwks.json",
        test="""
pm.test("serves a key", function () { pm.response.to.have.status(200); pm.expect(pm.response.json().keys).to.not.be.empty; });
pm.collectionVariables.set("composite_jwks", pm.response.text());
"""),
    req("Internal API is not public", "GET", "{{composite_url}}/composite/v1/internal/consent-templates?partner={{partner_id}}",
        test='pm.test("404 on the public host", function () { pm.response.to.have.status(404); });'),
    req("Exchange CM signing keys (JWKS)", "GET", "{{exchange_cm_jwks_url}}",
        desc="The Exchange Consent Manager's public keys. Each department's Consent Manager reads them here to accept "
             "the consent tokens the Exchange CM issues (issuer agri-stack-exchange-cm).",
        test='pm.test("serves a key", function () { pm.response.to.have.status(200); '
             'pm.expect(pm.response.json().keys).to.not.be.empty; });'),
    req("Exchange PM and the Composite (informational)", "GET", "{{exchange_pm_partner_url}}/keys/{{composite_ref}}",
        desc="OpenG2P's Exchange check page expects the Exchange's own Partner Management to serve "
             "PARTNER_AGRI_COMPOSITE. Commons Services develop.340 onboards the Composite only in departments "
             "(values.yaml: 'Not at the Exchange: nothing there checks the Composite's signature'), so 404 is the "
             "chart's behaviour; test_install.py checks the departments only. Logged, not failed.",
        test="""
pm.test("200 (docs) or 404 (chart develop.340)", function () { pm.expect(pm.response.code).to.be.oneOf([200, 404]); });
console.log("Exchange PM " + (pm.response.code === 200 ? "serves" : "does not serve") + " the Composite's key");
"""),
    req("Partner portal is up", "GET", "{{partner_portal_url}}",
        desc="The banks' portal at the Exchange (Consent Manager Partner Portal? Yes): consents a partner collected.",
        test='pm.test("answers", function () { pm.expect(pm.response.code).to.be.oneOf([200, 301, 302, 303, 307]); });'),
    req("Composite console is up", "GET", "{{composite_console_url}}",
        desc="The Exchange's admin console: every call, its partner, sources and status (staff login).",
        test='pm.test("answers", function () { pm.expect(pm.response.code).to.be.oneOf([200, 301, 302, 303, 307]); });'),
])

# --- 2 Partner onboarding ---------------------------------------------------------------------------------------------

POLICY_COVERS = r"""
var covers = function (policies) {
  var have = policies.map(function (p) { return p.use_case || ("dc:" + p.data_controller); });
  var need = [pm.collectionVariables.get("use_case_ref")];
  return need.filter(function (n) { return have.indexOf(n) < 0; });
};
"""

onboarding = folder("3 Bank onboarding (Exchange)", "Onboards the test bank in the Exchange's Partner Management: its "
                    "key and a policy for the use case (name@major). The bank is a partner of the Exchange only; no "
                    "department knows it. Every write is skipped when Partner Management already has it; with "
                    "auto_approve=true each request is approved at once.", [
    req("Get partner", "GET", "{{exchange_pm_staff_url}}/partners/{{partner_ref}}", auth=bearer(),
        test="""
pm.test("200 or 404", function () { pm.expect(pm.response.code).to.be.oneOf([200, 404]); });
pm.collectionVariables.set("partner_exists", String(pm.response.code === 200));
"""),
    req("Onboard partner", "POST", "{{exchange_pm_staff_url}}/partners/requests/onboarding", auth=bearer(), body="{{onboarding_body}}",
        desc="Skipped when the partner exists. Raises the onboarding request with the partner's key and its "
             "use-case policy, then approves it.",
        pre=H + """
if (pm.collectionVariables.get("partner_exists") === "true") { pm.execution.skipRequest(); }
pm.collectionVariables.set("onboarding_body", JSON.stringify({
  partner_id: pm.collectionVariables.get("partner_ref"), name: "TEST " + v("partner_id"), org_name: "TEST " + v("partner_id"),
  description: "agri-stack-postman: test partner",
  keys: [{ public_key: pm.environment.get("partner_public_key_pem"), kid: pm.environment.get("partner_kid"), algorithm: "ES256" }],
  policies: [policyInput({ use_case: pm.collectionVariables.get("use_case_ref") })]
}));
""",
        test=H + """
pm.test("onboarding request raised", function () { pm.expect(pm.response.code).to.be.oneOf([200, 201]); });
staffApprove(pm.response.json().id);
"""),
    req("Update partner key", "POST", "{{exchange_pm_staff_url}}/partners/requests/key-update", auth=bearer(), body="{{key_update_body}}",
        desc="Only when the partner existed and PM does not serve this environment's kid (e.g. a new key).",
        pre=H + """
if (pm.collectionVariables.get("partner_exists") !== "true" || pm.collectionVariables.get("partner_key_served") === "true") {
  pm.execution.skipRequest();
}
pm.collectionVariables.set("key_update_body", JSON.stringify({
  partner_id: pm.collectionVariables.get("partner_ref"), description: "agri-stack-postman: key " + pm.environment.get("partner_kid"),
  keys: [{ public_key: pm.environment.get("partner_public_key_pem"), kid: pm.environment.get("partner_kid"), algorithm: "ES256" }]
}));
""",
        test=H + """
pm.test("key-update request raised", function () { pm.expect(pm.response.code).to.be.oneOf([200, 201]); });
staffApprove(pm.response.json().id);
"""),
    req("Raise missing policies", "POST", "{{exchange_pm_staff_url}}/partners/requests/policy", auth=bearer(), body="{{policy_body}}",
        desc="Adds the use-case policy when the bank lacks it, with partner-signed consents allowed (the bank signs "
             "the farmer's consent). Skipped when PM already serves it.",
        pre=H + POLICY_COVERS + """
var send = this;
pm.sendRequest({ url: v("exchange_pm_partner_url") + "/policies/" + pm.collectionVariables.get("partner_ref") }, function (err, res) {
  var served = (!err && res.code === 200) ? (res.json().policies || []) : [];
  var missing = covers(served);
  if (!missing.length) { console.log("all policies served"); pm.execution.skipRequest(); return; }
  var scopes = consentScopes();
  pm.collectionVariables.set("policy_body", JSON.stringify({
    partner_id: pm.collectionVariables.get("partner_ref"), description: "agri-stack-postman: " + missing.join(", "),
    policies: missing.map(function (m) {
      return m.indexOf("dc:") === 0 ? policyInput({ data_controller: m.substring(3), scopes: scopes[m.substring(3)] })
                                    : policyInput({ use_case: m });
    })
  }));
});
""",
        test=H + """
pm.test("policy request raised", function () { pm.expect(pm.response.code).to.be.oneOf([200, 201]); });
staffApprove(pm.response.json().id);
"""),
    req("Wait until PM serves key and policies", "GET", "{{exchange_pm_partner_url}}/policies/{{partner_ref}}",
        desc="Polls (wait_attempts x wait_ms) until the Exchange's Partner Management serves the use-case policy "
             "and the bank's kid.",
        test=H + POLICY_COVERS + """
var served = pm.response.code === 200 ? (pm.response.json().policies || []) : [];
var missing = covers(served), n = Number(pm.collectionVariables.get("wait_n") || 0);
pm.sendRequest({ url: v("exchange_pm_partner_url") + "/keys/" + pm.collectionVariables.get("partner_ref") }, function (err, res) {
  var kid = pm.environment.get("partner_kid");
  var keyOk = !err && res.code === 200 && (res.json().keys || []).some(function (k) { return k.kid === kid; });
  if ((missing.length || !keyOk) && n < Number(v("wait_attempts"))) {
    pm.collectionVariables.set("wait_n", String(n + 1));
    console.log("waiting for PM: missing " + missing.join(", ") + (keyOk ? "" : " key " + kid));
    setTimeout(function () { pm.execution.setNextRequest(pm.info.requestName); }, Number(v("wait_ms")));
    return;
  }
  pm.collectionVariables.set("wait_n", "0");
  pm.test("PM serves the partner's key", function () { pm.expect(keyOk).to.equal(true); });
  pm.test("PM serves every policy", function () { pm.expect(missing).to.eql([]); });
});
"""),
])

# --- 2 Departments release data to the Composite -------------------------------------------------------------------

DEPT_COVERS = r"""
var scopes = consentScopes()[v("%P%_controller")] || [];
var policyOk = function (policies) {
  return policies.some(function (p) {
    return p.data_controller === v("%P%_controller") &&
      scopes.every(function (s) { return (p.allowed_data_scopes || []).indexOf(s) >= 0; });
  });
};
"""


def department(prefix, label):
    covers = DEPT_COVERS.replace("%P%", prefix)
    return [
        token_req(prefix, label),
        req(f"{label}: PM serves the Composite's key", "GET", "{{%s_pm_partner_url}}/keys/{{composite_ref}}" % prefix,
            desc=f"The {label}'s Partner Management onboards the Composite by itself (Commons role department), reading "
                 "its keys from https://agri-composite.<Exchange domain>/.well-known/jwks.json.",
            test="""
pm.test("Composite key served", function () {
  pm.response.to.have.status(200);
  var jwks = JSON.parse(pm.collectionVariables.get("composite_jwks") || "{\\"keys\\":[]}").keys.map(function (k) { return k.kid; });
  var served = (pm.response.json().keys || []).map(function (k) { return k.kid; });
  pm.expect(served.filter(function (k) { return jwks.indexOf(k) >= 0; })).to.not.be.empty;
});
"""),
        req(f"{label}: release data to the Composite", "POST",
            "{{%s_pm_staff_url}}/partners/requests/policy" % prefix, auth=bearer(prefix), body="{{%s_policy_body}}" % prefix,
            desc=f"The {label} decides what the Exchange may read: a scope policy for the Composite on data controller "
                 f"{{{{{prefix}_controller}}}} with the use case's scopes and purpose (no partner-signed consents: the "
                 "Exchange Consent Manager's token is the consent). Skipped when already served.",
            pre=H + covers + """
pm.sendRequest({ url: v("%P%_pm_partner_url") + "/policies/" + pm.collectionVariables.get("composite_ref") }, function (err, res) {
  var served = (!err && res.code === 200) ? (res.json().policies || []) : [];
  if (policyOk(served)) { console.log("%L% already releases its data to the Composite"); pm.execution.skipRequest(); return; }
  pm.collectionVariables.set("%P%_policy_body", JSON.stringify({
    partner_id: pm.collectionVariables.get("composite_ref"), description: "agri-stack-postman: %L% scope policy",
    policies: [policyInput({ data_controller: v("%P%_controller"), scopes: scopes, partner_consents: false })]
  }));
});
""".replace("%P%", prefix).replace("%L%", label),
            test=H + """
pm.test("policy request raised", function () { pm.expect(pm.response.code).to.be.oneOf([200, 201]); });
staffApprove(pm.response.json().id, null, "%P%");
""".replace("%P%", prefix)),
        req(f"{label}: wait until served", "GET", "{{%s_pm_partner_url}}/policies/{{composite_ref}}" % prefix,
            desc="Polls (wait_attempts x wait_ms) until the scope policy is served.",
            test=H + covers + """
var served = pm.response.code === 200 ? (pm.response.json().policies || []) : [];
var n = Number(pm.collectionVariables.get("wait_n") || 0);
if (!policyOk(served) && n < Number(v("wait_attempts"))) {
  pm.collectionVariables.set("wait_n", String(n + 1));
  setTimeout(function () { pm.execution.setNextRequest(pm.info.requestName); }, Number(v("wait_ms")));
} else {
  pm.collectionVariables.set("wait_n", "0");
  pm.test("%L% releases its data to the Composite", function () { pm.expect(policyOk(served)).to.equal(true); });
}
""".replace("%L%", label)),
    ]


departments = folder("2 Departments release data", "OpenG2P install step 3, once per department: each department's "
                     "Partner Management (its own Keycloak and client) gives the Composite a scope policy for its "
                     "registry. Until then the registry releases nothing to the Composite.",
                     department("farmer", "Farmer department") + department("crop", "Crop Sown department")
                     + department("livestock", "Livestock department"))

# --- 3 Farmer profile query ------------------------------------------------------------------------------------------

QUERY_PRE = H + r"""
var subject = { type: v("subject_type"), value: v("%SUBJECT%") };
var header = { version: "1.0.0", message_id: uuid(), message_ts: new Date().toISOString(), action: "query",
               sender_id: v("partner_id"), receiver_id: v("composite_id") };
var message = { subject: subject, parameters: JSON.parse(v("query_parameters") || "{}") };
if (%CONSENT%) { message.consent_jws = makeConsent(subject); }
var env = envelope(header, message);
if (%TAMPER%) { env.message.subject.value = "000000000000"; }
pm.collectionVariables.set("query_body", JSON.stringify(env));
"""

CACHE_RETRY = r"""
// Composite and Consent Manager cache Partner Management answers: retry a refusal for a while after a PM change.
var b = {}; try { b = pm.response.json(); } catch (e) {}
var err = ((b.message || {}).error) || {}, n = Number(pm.collectionVariables.get("retry_n") || 0);
// Right after onboarding, the Composite still holds Partner Management's earlier "no such partner" answer.
console.log("answer: " + pm.response.code + " " + JSON.stringify(err));
var refused = pm.response.code === 403 && ["partner_not_allowed", "partner_unknown", "unknown_partner", "partner_key_unknown"]
  .indexOf(err.code) >= 0 || JSON.stringify(b).indexOf("unknown_partner") >= 0;
if (refused && n < Number(v("cache_retries"))) {
  pm.collectionVariables.set("retry_n", String(n + 1));
  console.log("refused (cached PM answer?), retry " + (n + 1));
  setTimeout(function () { pm.execution.setNextRequest(pm.info.requestName); }, Number(v("wait_ms")));
  return;
}
pm.collectionVariables.set("retry_n", "0");
"""


def query_req(name, desc, subject="subject_value", consent=True, tamper=False, test=""):
    pre = QUERY_PRE.replace("%SUBJECT%", subject).replace("%CONSENT%", str(consent).lower()).replace(
        "%TAMPER%", str(tamper).lower())
    return req(name, "POST", "{{composite_url}}/composite/v1/use-cases/{{use_case}}/query", body="{{query_body}}",
               pre=pre, desc=desc, test=H + "(function () {\n" + (CACHE_RETRY if consent and not tamper else "") + test + "\n})();")


SOURCES = r"""
var sources = ((b.message || {}).sources) || {};
console.log("sources: " + JSON.stringify(sources));
"""

query = folder("4 Farmer profile query", "The signed query a bank sends to the Exchange: the Composite has the "
               "farmer's consent checked by the Exchange Consent Manager, which gives each registry its own consent "
               "token; each department's Consent Manager accepts it. Then the refusals that must happen.", [
    query_req("Query with consent", "The partner signs a consent with one grant per registry and the query envelope. "
              "Pass = 200, a valid Composite signature, farmer ok, crops and livestock ok or no_record.", test=SOURCES + """
pm.test("200", function () { pm.response.to.have.status(200); });
pm.test("Composite signature valid", function () { pm.expect(verifyComposite(b)).to.equal("valid"); });
pm.test("header.status succ", function () { pm.expect(b.header.status).to.equal("succ"); });
pm.test("farmer ok", function () { pm.expect((sources.farmer || {}).status).to.equal("ok"); });
["crops", "livestock"].forEach(function (s) {
  pm.test(s + " ok or no_record", function () { pm.expect((sources[s] || {}).status).to.be.oneOf(["ok", "no_record"]); });
});
pm.test("farmer data returned", function () { pm.expect(b.message.data.farmer).to.be.an("object"); });
"""),
    query_req("Unknown farmer", "A FAN no registry knows: the mandatory farmer source answers no_record.",
              subject="unknown_subject_value", test=SOURCES + """
pm.test("signed answer", function () { pm.expect(verifyComposite(b)).to.equal("valid"); });
pm.test("farmer no_record", function () { pm.expect((sources.farmer || {}).status).to.equal("no_record"); });
"""),
    query_req("Stored consent (lookup)", "No consent_jws: the Exchange Consent Manager stored the consent sent with "
              "'Query with consent' and finds it for this bank and farmer (OpenG2P's main path, test.consent: lookup). "
              "Pass = 200, signed, farmer ok, the stored consent_id.", consent=False, test="""
var b = {}; try { b = pm.response.json(); } catch (e) {}
var m = b.message || {};
pm.test("200", function () { pm.response.to.have.status(200); });
pm.test("Composite signature valid", function () { pm.expect(verifyComposite(b)).to.equal("valid"); });
pm.test("answered from a stored consent", function () { pm.expect(m.consent_id).to.be.a("string").and.not.empty; });
pm.test("farmer ok", function () { pm.expect(((m.sources || {}).farmer || {}).status).to.equal("ok"); });
"""),
    query_req("No consent for this farmer is refused", "No consent_jws, for a farmer this bank never had a consent "
              "for: the Exchange Consent Manager finds none, so the query must not return data.",
              subject="unconsented_subject_value", consent=False, test="""
var b = {}; try { b = pm.response.json(); } catch (e) {}
var data = ((b.message || {}).data) || {};
console.log("answer: " + pm.response.code + " " + JSON.stringify(((b.message || {}).error) || (b.header || {}).status || ""));
pm.test("refused (4xx or rjct)", function () {
  pm.expect(pm.response.code >= 400 || (b.header || {}).status === "rjct").to.equal(true);
});
pm.test("no farmer data", function () { pm.expect(data.farmer === undefined || data.farmer === null).to.equal(true); });
"""),
    query_req("Tampered message is refused", "The body is changed after signing: the signature check must reject it.",
              tamper=True, test="""
pm.test("401/400/403", function () { pm.expect(pm.response.code).to.be.oneOf([400, 401, 403]); });
"""),
])

# --- 4 Registries (DCI) -----------------------------------------------------------------------------------------------


def dci_req(label, prefix):
    pre = H + r"""
var subject = { type: v("subject_type"), value: v("subject_value") };
var q = {}; q[v("%P%_search_field")] = { "$eq": v("subject_value") };
var ts = new Date().toISOString(), rid = uuid();
var header = { version: "1.0.0", message_id: uuid(), message_ts: ts, action: "search", sender_id: v("partner_id"),
               receiver_id: v("%P%_controller"), total_count: 1, is_msg_encrypted: false };
var message = { transaction_id: rid, search_request: [{ reference_id: rid + "-%P%", timestamp: ts, locale: "eng",
  search_criteria: { version: "1.0.0", reg_type: v("%P%_reg_type"), reg_record_type: v("%P%_reg_record_type"),
    query_type: "expression", query: { type: "expression", value: { expression: { query: q } } },
    pagination: { page_size: 20, page_number: 1 }, authorize: { consent_jws: makeConsent(subject) } } }] };
pm.collectionVariables.set("dci_body", JSON.stringify(envelope(header, message)));
""".replace("%P%", prefix)
    test = H + "(function () {\nvar b = {}; try { b = pm.response.json(); } catch (e) {}\n" + """
var r = ((b.message || {}).search_response || [])[0] || {};
var records = ((r.data || {}).reg_records) || [];
console.log("%L%: " + (r.status || pm.response.code) + ", " + records.length + " record(s) " + (r.status_reason_message || ""));
pm.test("no records for a bank that is not the department's partner", function () { pm.expect(records.length).to.equal(0); });
pm.test("refused (4xx or not succ)", function () { pm.expect(pm.response.code >= 400 || r.status !== "succ").to.equal(true); });
""".replace("%L%", label) + "\n})();"
    return req(f"{label} search", "POST", "{{%s_dci_url}}" % prefix, body="{{dci_body}}", pre=pre, test=test,
               desc=f"The bank calls the {label} registry directly, signed, with its own consent, by "
                    f"{{{{{prefix}_search_field}}}}. The bank is a partner of the Exchange only, so the department "
                    "must refuse: data leaves a department only through the Composite.")


registries = folder("5 Registries refuse the bank", "The bank tries each registry directly (signed DCI envelope, "
                    "expression query, its own consent). Each department must refuse it: only the Composite is its "
                    "partner.", [
    dci_req("Farmer", "farmer"), dci_req("Crop Sown", "crop"), dci_req("Livestock", "livestock"),
])

# --- assemble --------------------------------------------------------------------------------------------------------

RUNTIME = ["partner_ref", "composite_ref", "jsrsasign_src", "exchange_token", "farmer_token", "crop_token",
           "livestock_token", "farmer_policy_body", "crop_policy_body", "livestock_policy_body", "use_case_ref",
           "purpose", "consent_scopes",
           "composite_jwks", "partner_exists", "partner_key_served", "onboarding_body", "key_update_body",
           "policy_body", "query_body", "dci_body", "wait_n", "retry_n"]

collection = {
    "info": {
        "_postman_id": uid("collection"),
        "name": "Agri Stack Composite",
        "description": (HERE / "README.md").read_text(encoding="utf-8"),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [setup, composite, departments, onboarding, query, registries],
    "event": [event("prerequest", COLLECTION_PRE)],
    "variable": [{"key": "helpers_src", "value": HELPERS.strip(), "type": "string",
                  "description": "Shared script code; eval'd by signing scripts. Generated by build.py."}]
                + [{"key": k, "value": "", "type": "string", "description": "set by the scripts at run time"} for k in RUNTIME],
}

ENV = [
    ("parent_domain", "test.oanstaging.com", "default", "Each organisation is <namespace>.{{parent_domain}}"),
    ("exchange_namespace", "agrix", "default", "The Exchange (Composite): Kubernetes namespace"),
    ("exchange_domain", "{{exchange_namespace}}.{{parent_domain}}", "default", "The Exchange (Composite): its domain"),
    ("exchange_keycloak_url", "https://keycloak.{{exchange_domain}}", "default", "The Exchange (Composite): Keycloak"),
    ("exchange_pm_staff_url", "https://pm-staff-portal.{{exchange_domain}}", "default", "The Exchange (Composite): Partner Management staff API"),
    ("exchange_pm_partner_url", "https://partner-management-partner-api.{{exchange_domain}}", "default", "The Exchange (Composite): Partner Management partner API"),
    ("exchange_client_secret", "", "secret", "The Exchange (Composite): Secret commons-services-staff-portal key client_secret in namespace agrix"),
    ("farmer_namespace", "farmer", "default", "Farmer department: Kubernetes namespace"),
    ("farmer_domain", "{{farmer_namespace}}.{{parent_domain}}", "default", "Farmer department: its domain"),
    ("farmer_keycloak_url", "https://keycloak.{{farmer_domain}}", "default", "Farmer department: Keycloak"),
    ("farmer_pm_staff_url", "https://pm-staff-portal.{{farmer_domain}}", "default", "Farmer department: Partner Management staff API"),
    ("farmer_pm_partner_url", "https://partner-management-partner-api.{{farmer_domain}}", "default", "Farmer department: Partner Management partner API"),
    ("farmer_client_secret", "", "secret", "Farmer department: Secret commons-services-staff-portal key client_secret in namespace farmer"),
    ("crop_namespace", "crop", "default", "Crop Sown department: Kubernetes namespace"),
    ("crop_domain", "{{crop_namespace}}.{{parent_domain}}", "default", "Crop Sown department: its domain"),
    ("crop_keycloak_url", "https://keycloak.{{crop_domain}}", "default", "Crop Sown department: Keycloak"),
    ("crop_pm_staff_url", "https://pm-staff-portal.{{crop_domain}}", "default", "Crop Sown department: Partner Management staff API"),
    ("crop_pm_partner_url", "https://partner-management-partner-api.{{crop_domain}}", "default", "Crop Sown department: Partner Management partner API"),
    ("crop_client_secret", "", "secret", "Crop Sown department: Secret commons-services-staff-portal key client_secret in namespace crop"),
    ("livestock_namespace", "livestock", "default", "Livestock department: Kubernetes namespace"),
    ("livestock_domain", "{{livestock_namespace}}.{{parent_domain}}", "default", "Livestock department: its domain"),
    ("livestock_keycloak_url", "https://keycloak.{{livestock_domain}}", "default", "Livestock department: Keycloak"),
    ("livestock_pm_staff_url", "https://pm-staff-portal.{{livestock_domain}}", "default", "Livestock department: Partner Management staff API"),
    ("livestock_pm_partner_url", "https://partner-management-partner-api.{{livestock_domain}}", "default", "Livestock department: Partner Management partner API"),
    ("livestock_client_secret", "", "secret", "Livestock department: Secret commons-services-staff-portal key client_secret in namespace livestock"),
    ("composite_url", "https://agri-composite.{{exchange_domain}}", "default", "The Composite, at the Exchange"),
    ("composite_console_url", "https://agri-composite-console.{{exchange_domain}}", "default", "The Composite console (staff)"),
    ("exchange_cm_jwks_url", "https://consent-manager-partner.{{exchange_domain}}/api/consent-manager-partner/.well-known/jwks.json", "default", "The Exchange Consent Manager's public keys"),
    ("partner_portal_url", "https://consent-partner-portal.{{exchange_domain}}", "default", "The partner portal (banks), at the Exchange"),
    ("composite_id", "agri-composite", "default", "The Composite's partner id (DCI receiver_id of a query; PM PARTNER_AGRI_COMPOSITE)"),
    ("staff_realm", "staff", "default", ""),
    ("client_id", "commons-services-staff-portal", "default", "Partner Management admin client (client credentials), the same name in every organisation"),
    ("partner_id", "postman-test-bank", "default", "The test bank; PM id PARTNER_<ID>, at the Exchange only"),
    ("use_case", "farmer-profile", "default", ""),
    ("subject_type", "FAYDA_FAN", "default", "Master Data SUBJECT_ID_TYPE"),
    ("subject_value", "502628318720", "default", "Sample farmer ETH-IND-0001 (synthetic, openg2p-data ETH-OAN)"),
    ("unknown_subject_value", "999999999999", "default", "A FAN no registry knows"),
    ("unconsented_subject_value", "888888888888", "default", "A FAN this bank never sends a consent for"),
    ("subject_id_types", "FAYDA_FAN", "default", "Comma-separated, for the partner's policies"),
    ("query_parameters", "{}", "default", "JSON object, the use case's parameters"),
    ("auto_approve", "true", "default", "true: the collection approves its own PM requests"),
    ("policy_max_validity", "P90D", "default", ""),
    ("consent_valid_days", "1", "default", ""),
    ("wait_attempts", "30", "default", "PM serving poll: attempts"),
    ("wait_ms", "10000", "default", "PM serving poll / cache retry: pause"),
    ("cache_retries", "9", "default", "Query retries on a cached PM refusal"),
    ("farmer_dci_url", "https://partner-farmer.{{farmer_domain}}/dci/registry/sync/search", "default", ""),
    ("farmer_controller", "farmer-registry", "default", ""),
    ("farmer_reg_type", "Farmer", "default", ""),
    ("farmer_reg_record_type", "spdci-extensions-dci:FarmerRecord", "default", ""),
    ("farmer_search_field", "foundational_id", "default", ""),
    ("crop_dci_url", "https://partner-crop.{{crop_domain}}/dci/registry/sync/search", "default", ""),
    ("crop_controller", "cropsown-registry", "default", ""),
    ("crop_reg_type", "CropSown", "default", ""),
    ("crop_reg_record_type", "spdci-extensions-dci:CropSownRecord", "default", ""),
    ("crop_search_field", "fayda_fan_id", "default", ""),
    ("livestock_dci_url", "https://partner-livestock.{{livestock_domain}}/dci/registry/sync/search", "default", ""),
    ("livestock_controller", "livestock-registry", "default", ""),
    ("livestock_reg_type", "Livestock", "default", ""),
    ("livestock_reg_record_type", "spdci-extensions-dci:LivestockRecord", "default", ""),
    ("livestock_search_field", "fayda_fan_id", "default", ""),
    ("jsrsasign_url", "https://cdnjs.cloudflare.com/ajax/libs/jsrsasign/11.1.0/jsrsasign-all-min.js", "default", ""),
    ("partner_private_key_pem", "", "secret", "Generated on first run; current value only"),
    ("partner_public_key_pem", "", "default", "Generated on first run"),
    ("partner_kid", "", "default", "Generated on first run"),
]
environment = {
    "id": uid("environment registry-test"), "name": "registry-test (OpenG2P topology, *.test.oanstaging.com)",
    "values": [{"key": k, "value": val, "type": t, "enabled": True, "description": d} for k, val, t, d in ENV],
    "_postman_variable_scope": "environment",
}

(HERE / "agri-stack.postman_collection.json").write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8", newline="\n")
(HERE / "registry-test.postman_environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8", newline="\n")
print("collection", sum(len(f["item"]) for f in collection["item"]), "requests;", len(ENV), "environment variables")
