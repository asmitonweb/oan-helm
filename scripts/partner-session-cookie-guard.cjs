'use strict';

// Select cookies for this portal's issuer before Next.js collapses duplicate
// cookie names. This is routing only: IAM still verifies signatures and claims.
const AUTH_NAMES = new Set(['X-Access-Token', 'X-ID-Token']);

function tokenIssuer(value) {
  try {
    const raw = decodeURIComponent(value.replace(/^"|"$/g, ''));
    const parts = raw.split('.');
    if (parts.length !== 3 || raw.length > 32768) return undefined;
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
    return typeof payload.iss === 'string' ? payload.iss : undefined;
  } catch {
    return undefined;
  }
}

function filterAuthCookies(header, issuer) {
  if (!header) return header;
  const others = [];
  const selected = new Map();
  let hadAccessToken = false;
  for (const part of header.split(';')) {
    const cookie = part.trim();
    const separator = cookie.indexOf('=');
    if (separator < 1) continue;
    const name = cookie.slice(0, separator).trim();
    if (!AUTH_NAMES.has(name)) {
      others.push(cookie);
      continue;
    }
    if (name === 'X-Access-Token') hadAccessToken = true;
    if (tokenIssuer(cookie.slice(separator + 1).trim()) === issuer) {
      selected.set(name, cookie);
    }
  }
  // A foreign access cookie must start a fresh login, rather than trigger the
  // UI's "oversized token" branch merely because an ID cookie remains.
  if (hadAccessToken && !selected.has('X-Access-Token')) selected.delete('X-ID-Token');
  return [...others, ...selected.values()].join('; ');
}

function install(issuer) {
  const url = new URL(issuer);
  if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash || url.username || url.password) {
    throw new Error('Session cookie guard requires a valid expected issuer URL');
  }
  const http = require('node:http');
  const installed = Symbol.for('oan.partner-session-cookie-guard');
  if (http.Server.prototype[installed]) return;
  const emit = http.Server.prototype.emit;
  http.Server.prototype.emit = function (event, ...args) {
    if (event === 'request' && args[0]?.headers?.cookie) {
      const request = args[0];
      request.headers.cookie = filterAuthCookies(request.headers.cookie, issuer);
      // Keep the raw header consistent for frameworks that inspect it directly.
      for (let i = 0; i < request.rawHeaders.length; i += 2) {
        if (request.rawHeaders[i].toLowerCase() === 'cookie') request.rawHeaders[i + 1] = request.headers.cookie;
      }
    }
    return emit.call(this, event, ...args);
  };
  http.Server.prototype[installed] = true;
}

module.exports = { filterAuthCookies, tokenIssuer, install };
if (process.env.OAN_SESSION_COOKIE_GUARD === '1') {
  if (!process.env.OAN_SESSION_EXPECTED_ISSUER) throw new Error('Expected session issuer is required');
  install(process.env.OAN_SESSION_EXPECTED_ISSUER);
}
