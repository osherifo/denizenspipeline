"""Hub sources — the registered lab / community git repositories.

Persisted in ``~/.config/fmriflow/settings.json`` under the key
``FMRIFLOW_HUB_SOURCES`` (a JSON array of objects), env-overridable via the
``FMRIFLOW_HUB_SOURCES`` environment variable (JSON). This mirrors the
result-roots precedent (`paths.extra_result_roots` etc.), generalised from
plain paths to richer source objects.

Per-source access tokens are stored separately (secret, never returned in
API payloads) under ``FMRIFLOW_HUB_TOKENS`` keyed by source id.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, asdict

from fmriflow.core import paths

SETTINGS_KEY = "FMRIFLOW_HUB_SOURCES"
TOKENS_KEY = "FMRIFLOW_HUB_TOKENS"
ENV_SOURCES = "FMRIFLOW_HUB_SOURCES"

VALID_TIERS = ("lab", "community")
VALID_BACKENDS = ("git",)


@dataclass(frozen=True)
class HubSource:
    id: str
    name: str
    tier: str            # "lab" | "community"
    url: str
    backend: str = "git"
    branch: str = "main"
    enabled: bool = True

    def to_public(self) -> dict:
        """Serialisable view (no secrets — tokens live elsewhere)."""
        return asdict(self)


def source_id(url: str) -> str:
    """Stable id: first 8 hex of sha1(url). Reorder-safe, hides nothing
    sensitive (the URL is not secret; the token is stored separately)."""
    return hashlib.sha1(url.strip().encode()).hexdigest()[:8]


def _coerce(d: dict) -> HubSource | None:
    try:
        url = str(d["url"]).strip()
        if not url:
            return None
        tier = str(d.get("tier", "lab"))
        if tier not in VALID_TIERS:
            tier = "lab"
        return HubSource(
            id=str(d.get("id") or source_id(url)),
            name=str(d.get("name") or url),
            tier=tier,
            url=url,
            backend=str(d.get("backend", "git")),
            branch=str(d.get("branch") or "main"),
            enabled=bool(d.get("enabled", True)),
        )
    except Exception:
        return None


class SourceRegistry:
    """Read/write the configured hub sources (env > settings.json)."""

    def list_sources(self) -> list[HubSource]:
        env = os.environ.get(ENV_SOURCES)
        raw: object
        if env:
            try:
                raw = json.loads(env)
            except Exception:
                raw = []
        else:
            raw = paths.load_settings_value(SETTINGS_KEY, [])
        if not isinstance(raw, list):
            return []
        out: list[HubSource] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            src = _coerce(item)
            if src is None or src.id in seen:
                continue
            seen.add(src.id)
            out.append(src)
        return out

    def env_override(self) -> bool:
        return bool(os.environ.get(ENV_SOURCES))

    def get(self, sid: str) -> HubSource | None:
        for s in self.list_sources():
            if s.id == sid:
                return s
        return None

    def add(self, name: str, url: str, tier: str = "lab",
            branch: str = "main", backend: str = "git") -> HubSource:
        if self.env_override():
            raise RuntimeError("FMRIFLOW_HUB_SOURCES is set in the environment; "
                               "unset it to manage sources here.")
        if tier not in VALID_TIERS:
            raise ValueError(f"tier must be one of {VALID_TIERS}")
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}")
        src = HubSource(id=source_id(url), name=name or url, tier=tier,
                        url=url.strip(), backend=backend, branch=branch or "main")
        current = [s for s in self.list_sources() if s.id != src.id]
        current.append(src)
        paths.save_settings_value(SETTINGS_KEY, [s.to_public() for s in current])
        return src

    def remove(self, sid: str) -> None:
        if self.env_override():
            raise RuntimeError("FMRIFLOW_HUB_SOURCES is set in the environment; "
                               "unset it to manage sources here.")
        current = [s for s in self.list_sources() if s.id != sid]
        paths.save_settings_value(SETTINGS_KEY, [s.to_public() for s in current])
        # also drop any stored token
        toks = self._load_tokens()
        if sid in toks:
            toks.pop(sid, None)
            paths.save_settings_value(TOKENS_KEY, toks)

    # ── Tokens (secret) ──
    #
    # Resolution order for reads: env var > OS keyring > settings.json.
    # Writes prefer the OS keyring (the same secure store `gh` uses — GNOME
    # Keyring/libsecret, macOS Keychain, Windows Credential Manager) and, when
    # keyring is available, actively migrate any plaintext token out of
    # settings.json. Only if no keyring backend exists do we fall back to
    # settings.json, which is plaintext — hence the env-var option for the
    # security-conscious.

    def _load_tokens(self) -> dict:
        val = paths.load_settings_value(TOKENS_KEY, {})
        return val if isinstance(val, dict) else {}

    def set_token(self, sid: str, token: str | None) -> None:
        if _keyring_set(sid, token):
            # Keyring holds it now; make sure no plaintext copy lingers.
            toks = self._load_tokens()
            if toks.pop(sid, None) is not None:
                paths.save_settings_value(TOKENS_KEY, toks)
            return
        # Fallback: settings.json (plaintext).
        toks = self._load_tokens()
        if token:
            toks[sid] = token
        else:
            toks.pop(sid, None)
        paths.save_settings_value(TOKENS_KEY, toks)

    def token_for(self, sid: str) -> str | None:
        env = os.environ.get(f"FMRIFLOW_HUB_TOKEN_{sid.upper()}")
        if env:
            return env
        kr = _keyring_get(sid)
        if kr:
            return kr
        return self._load_tokens().get(sid)

    def has_token(self, sid: str) -> bool:
        return bool(self.token_for(sid))

    def token_storage(self, sid: str) -> str:
        """Where the token for *sid* is held: env | keyring | settings | none."""
        if os.environ.get(f"FMRIFLOW_HUB_TOKEN_{sid.upper()}"):
            return "env"
        if _keyring_get(sid):
            return "keyring"
        if self._load_tokens().get(sid):
            return "settings"
        return "none"


# ── OS keyring (optional) ────────────────────────────────────────────

_KEYRING_SERVICE = "fmriflow-hub"


def keyring_available() -> bool:
    try:
        import keyring
        from keyring.backends import fail
        return not isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return False


def _keyring_get(sid: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, sid)
    except Exception:
        return None


def _keyring_set(sid: str, token: str | None) -> bool:
    """Store/delete in the OS keyring. Returns True if keyring handled it."""
    if not keyring_available():
        return False
    try:
        import keyring
        if token:
            keyring.set_password(_KEYRING_SERVICE, sid, token)
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, sid)
            except Exception:
                pass
        return True
    except Exception:
        return False
