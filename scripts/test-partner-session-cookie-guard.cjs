const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const { filterAuthCookies, install } = require('./partner-session-cookie-guard.cjs');
const issuer = 'https://keycloak.development.oanstaging.com/realms/staff';
const staging = 'https://keycloak.oanstaging.com/realms/staff';
const jwt = (iss, extra = {}) => 'e30.' + Buffer.from(JSON.stringify({ iss, ...extra })).toString('base64url') + '.signature';
const dev = jwt(issuer);
const foreign = jwt(staging);

for (const [label, header] of [
  ['staging first', `X-Access-Token=${foreign}; X-Access-Token=${dev}`],
  ['staging last', `X-Access-Token=${dev}; X-Access-Token=${foreign}`],
]) {
  test(`selects the dev session with ${label}`, () => {
    assert.equal(filterAuthCookies(header, issuer), `X-Access-Token=${dev}`);
  });
}

test('foreign-only session becomes missing credentials without altering browser cookies', () => {
  assert.equal(filterAuthCookies(`X-Access-Token=${foreign}; X-ID-Token=${jwt(issuer)}; preference=keep`, issuer), 'preference=keep');
});

test('rejects malformed cookies and exact issuer mismatches', () => {
  for (const value of ['not-a-token', '%ZZ', jwt(issuer + '/'), jwt(issuer + '.attacker.invalid'), jwt(staging)]) {
    assert.equal(filterAuthCookies(`X-Access-Token=${value}`, issuer), '');
  }
});

test('retains other cookies and selects an ID token from the same issuer', () => {
  const header = `X-ID-Token=${foreign}; preference=a=b; X-Session-Id=keep; X-Access-Token=${dev}; X-ID-Token=${dev}`;
  assert.equal(filterAuthCookies(header, issuer), `preference=a=b; X-Session-Id=keep; X-Access-Token=${dev}; X-ID-Token=${dev}`);
});

test('does not treat matching issuer text as authenticated or rewrite a signature', () => {
  const forged = jwt(issuer, { sub: 'untrusted' });
  assert.equal(filterAuthCookies(`X-Access-Token=${forged}`, issuer), `X-Access-Token=${forged}`);
  // The untouched token must still be validated by the downstream IAM service.
});

test('actual HTTP listener receives selected cookies in parsed and raw headers', async () => {
  install(issuer);
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ cookie: request.headers.cookie, raw: request.rawHeaders }));
  }).listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    const result = await fetch(`http://127.0.0.1:${server.address().port}`, {
      headers: { Cookie: `X-Access-Token=${dev}; X-Access-Token=${foreign}` },
    }).then(response => response.json());
    assert.equal(result.cookie, `X-Access-Token=${dev}`);
    const cookieIndex = result.raw.findIndex(item => item.toLowerCase() === 'cookie');
    assert.equal(result.raw[cookieIndex + 1], `X-Access-Token=${dev}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});
