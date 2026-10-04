from __future__ import annotations

import hashlib
import re
from typing import Optional

from app.config import settings

_TRANSACTION_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_EMAIL_HASH_RE = re.compile(r"^[a-f0-9]{64}$")

# Domains where Google ignores dots in the local part when matching enhanced conversions.
_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}

_CONVERSION_SNIPPET = (
    "  gtag('event', 'conversion', {{send_to: '{send_to}', transaction_id: '{transaction_id}'}});"
)
_USER_DATA_SNIPPET = "  gtag('set', 'user_data', {{sha256_email_address: '{email_hash}'}});\n"


def signup_transaction_id(user_id: str) -> str:
    """Stable, per-account id so Google Ads dedupes the sign-up conversion.

    The hash input keeps the historical ":activation" suffix on purpose: changing it would
    change the ids of conversions already recorded and break deduplication for them.
    """
    digest = hashlib.sha256(f"{user_id}:activation".encode("utf-8")).hexdigest()
    return digest[:16]


def valid_transaction_id(value: Optional[str]) -> Optional[str]:
    """Return the id only if it is a safe 16-char hex string, else None."""
    if value is None:
        return None
    if not _TRANSACTION_ID_RE.match(value):
        return None
    return value


def hash_email_for_gads(email: Optional[str]) -> Optional[str]:
    """SHA-256 of the normalized email, as Google Ads enhanced conversions expect.

    Normalization: trim, lowercase, and drop dots in the local part for gmail/googlemail.
    """
    if not email:
        return None
    normalized = email.strip().lower()
    local, sep, domain = normalized.partition("@")
    if not sep or not local or not domain:
        return None
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
    return hashlib.sha256(f"{local}@{domain}".encode("utf-8")).hexdigest()


def valid_email_hash(value: Optional[str]) -> Optional[str]:
    """Return the hash only if it is a 64-char lowercase hex string, else None."""
    if value is None:
        return None
    if not _EMAIL_HASH_RE.match(value):
        return None
    return value


def build_signup_cookie_value(transaction_id: str, email_hash: Optional[str] = None) -> str:
    """Cookie value carried from the Auth0 callback to the login-success page."""
    if email_hash:
        return f"{transaction_id}.{email_hash}"
    return transaction_id


def parse_signup_cookie(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split the sign-up cookie into (transaction_id, email_hash), validating both."""
    if not raw:
        return None, None
    transaction_part, _, hash_part = raw.partition(".")
    transaction_id = valid_transaction_id(transaction_part)
    if transaction_id is None:
        return None, None
    return transaction_id, valid_email_hash(hash_part or None)


def _conversion_snippet(
    transaction_id: Optional[str],
    gads_id: str,
    label: str,
    email_hash: Optional[str] = None,
) -> str:
    if not transaction_id or not gads_id or not label:
        return ""
    snippet = ""
    if email_hash:
        snippet += _USER_DATA_SNIPPET.format(email_hash=email_hash)
    snippet += _CONVERSION_SNIPPET.format(
        send_to=f"{gads_id}/{label}",
        transaction_id=transaction_id,
    )
    return snippet


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex, nofollow" />
<title>You're signed in — Sensii</title>
<script async src="https://www.googletagmanager.com/gtag/js?id=__GADS_ID__"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', '__GADS_ID__');
__CONVERSION__
</script>
<style>
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(to bottom, #000, #111827, #000); color: #fff; font-family: system-ui, -apple-system, sans-serif; text-align: center; }
  .card { max-width: 36rem; background: rgba(0,0,0,0.7); border-radius: 1rem; padding: 2.5rem; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }
  h1 { font-size: 1.875rem; font-weight: 600; margin: 0 0 1rem; }
  p { color: #e5e7eb; line-height: 1.5; margin: 0; }
</style>
</head>
<body>
  <div class="card">
    <h1>You're signed in</h1>
    <p>Auth0 successfully linked your Sensii app. You can safely close this tab and return to the desktop client.</p>
  </div>
</body>
</html>
"""


def render_login_success_page(
    transaction_id: Optional[str],
    email_hash: Optional[str] = None,
) -> str:
    """Render the page shown after Auth0. The sign-up conversion fires only for a new account."""
    gads_id = settings.gads_id
    label = settings.gads_activation_label  # label of the Google Ads "Sign-up" conversion action

    safe_id = valid_transaction_id(transaction_id)
    safe_hash = valid_email_hash(email_hash)
    conversion = _conversion_snippet(safe_id, gads_id, label, safe_hash)

    return (
        _PAGE_TEMPLATE.replace("__GADS_ID__", gads_id)
        .replace("__CONVERSION__", conversion)
    )
