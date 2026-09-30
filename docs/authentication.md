# Authentication & Authorization

NEXORA uses JWT bearer tokens for authentication and a two-level role model for
authorization. This document explains both, in plain terms.

## Passwords

- Passwords are hashed with **Argon2** (`pwdlib`'s recommended settings). The
  plaintext password is never stored.
- Registration requires a password of 8–128 characters.
- A **precomputed dummy hash** is used so that login always performs exactly one
  Argon2 verification, whether or not the submitted email exists. This makes
  login **constant-time** and prevents an attacker from discovering which
  accounts are registered by measuring response time.

## Login flow

`POST /api/v1/auth/login` accepts `{ email, password }`:

1. The login **throttle** is checked first, keyed on the normalized email
   (`email.strip().lower()`). If that email is locked (too many recent
   failures), the request is rejected with **429** and a `Retry-After` header.
   The throttle is in-process and thread-safe, tracks at most 10,000 emails, and
   needs no Redis.
2. Exactly one Argon2 verification runs (real hash, or the dummy hash if the
   user/hash is missing).
3. On failure: the throttle records a failure, an audit event
   `login.failure` is written, and a uniform **401** `InvalidCredentialsError`
   is returned (same message whether the email or the password was wrong).
4. On success: the throttle is reset, an **access token** and a **refresh
   token** are issued, and an audit event `login.success` is written.

## Access tokens (JWT)

- Signed with `JWT_SECRET_KEY` using `HS256`.
- The subject (`sub`) is the user's id as a string.
- Tokens carry an `exp` (expiry) claim. **Decoding requires `exp`** — a token
  without one is rejected. Default lifetime is 30 minutes.
- Protected endpoints expect: `Authorization: Bearer <access_token>`.
- `get_current_user` returns a uniform **401** "Invalid authentication
  credentials" for every failure mode (expired, malformed, missing/non-integer
  subject, unknown user) so errors do not leak which part failed.

## Refresh tokens

- A refresh token is a random `secrets.token_urlsafe(32)` string.
- Only its **SHA-256 hash** is stored in the `refresh_tokens` table — the raw
  token is never persisted.
- Default lifetime is 30 days.
- `POST /api/v1/auth/refresh` **rotates** the token: the presented refresh token
  is revoked and a new access + refresh pair is issued. A token that is missing,
  already revoked, expired, or whose user no longer exists is rejected.
- `POST /api/v1/auth/logout` (**204**) revokes the presented refresh token.

## The two role levels

NEXORA separates **platform** roles from **tenant (organization)** roles. They
are independent.

### Platform role (`UserRole`)

- `admin` — can manage users platform-wide (list users, view a user, change a
  user's platform role). Enforced by the `require_admin` dependency; a
  non-admin gets **403** "Admin access required".
- `member` — a normal user. Can only access organizations they belong to.

### Organization role (`OrganizationRole`)

- `owner` — the creator of an organization. Highest tenant authority.
- `admin` — can manage members and documents, but **cannot** modify or remove
  the owner, and **cannot** modify or remove another admin.
- `member` — can use the organization (query documents) but cannot manage it.

Membership rules enforced in `organization_membership_service.py`:

- Only an acting admin/owner can add members; the `owner` role cannot be
  assigned to anyone else.
- An admin cannot change another admin's role, cannot remove another admin, and
  cannot touch the owner.
- Removing the owner is not allowed.
- Every membership change is audited (`membership.member_added`,
  `membership.role_changed`, `membership.member_removed`) with the target user id
  and role.

## Endpoint-level authorization

| Route group | Requirement |
|-------------|-------------|
| `POST /auth/register`, `POST /auth/login` | Public |
| `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | Valid token |
| `/users/*` | Platform `admin` |
| `POST /organizations` | Any authenticated user (creator becomes owner) |
| Organization member management | Organization admin/owner |
| Document upload/list/get | Organization **member** (`require_organization_member`) |
| Document version-replace / status change / delete | Organization **admin/owner** |
| `POST /organizations/{id}/query` and `/query/stream` | Organization member |
| `GET /organizations/{id}/audit-logs` | Organization **owner/admin** only (a plain member gets 403) |

If a caller has no membership in the organization, `require_organization_member`
returns **403**.

## Brute-force protection summary

- Per-email failed-login throttle → 429 + `Retry-After`.
- Constant-time login (always one Argon2 verify).
- Uniform 401 messages (no account enumeration).
- Refresh-token rotation and revocation.

## What is audited

`AuditAction` values: `login.success`, `login.failure`, `document.uploaded`,
`document.version_replaced`, `document.deleted`, `document.status_changed`,
`membership.member_added`, `membership.role_changed`,
`membership.member_removed`, `user.platform_role_changed`. See
[security.md](security.md) for the audit detail allowlist.
