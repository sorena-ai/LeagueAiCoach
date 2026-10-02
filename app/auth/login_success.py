from __future__ import annotations

import hashlib
import re
from typing import Optional

from app.config import settings

_TRANSACTION_ID_RE = re.compile(r"^[a-f0-9]{16}$")

_CONVERSION_SNIPPET = (
    "  gtag('event', 'conversion', {{send_to: '{send_to}', transaction_id: '{transaction_id}'}});"
)


def activation_transaction_id(user_id: str) -> str:
    """Stable, per-account id for deduplicating the activation conversion."""
    digest = hashlib.sha256(f"{user_id}:activation".encode("utf-8")).hexdigest()
    return digest[:16]


def valid_transaction_id(value: Optional[str]) -> Optional[str]:
    """Return the id only if it is a safe 16-char hex string, else None."""
    if value is None:
        return None
    if not _TRANSACTION_ID_RE.match(value):
        return None
    return value


def _conversion_snippet(transaction_id: Optional[str], gads_id: str, label: str) -> str:
    if not transaction_id or not gads_id or not label:
        return ""
    return _CONVERSION_SNIPPET.format(send_to=f"{gads_id}/{label}", transaction_id=transaction_id)


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex, nofollow" />
<title>You're signed in — Sensii</title>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  (function () {
    var consent = null;
    (document.cookie || '').split('; ').forEach(function (c) {
      var i = c.indexOf('=');
      if (i !== -1 && c.slice(0, i) === 'sensii_consent') {
        consent = decodeURIComponent(c.slice(i + 1));
      }
    });
    var value = consent === 'granted' ? 'granted' : 'denied';
    var fields = {ad_storage: value, ad_user_data: value, ad_personalization: value, analytics_storage: value};
    if (value !== 'granted') { fields.wait_for_update = 500; }
    gtag('consent', 'default', fields);
  })();
</script>
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


def render_login_success_page(transaction_id: Optional[str]) -> str:
    gads_id = settings.gads_id
    label = settings.gads_activation_label

    safe_id = valid_transaction_id(transaction_id)
    conversion = _conversion_snippet(safe_id, gads_id, label)

    return _PAGE_TEMPLATE.replace("__GADS_ID__", gads_id).replace("__CONVERSION__", conversion)
