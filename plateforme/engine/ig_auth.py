"""Connexion OAuth Instagram pour les stats (module 6), un token par compte, enregistré dans .env.

Deux types d'app Meta :
  instagram (défaut), « Instagram API with Instagram Login » : scopes instagram_business_basic +
                       instagram_business_manage_insights, host graph.instagram.com, token long-lived 60 j (rafraîchi auto)
  facebook, « Instagram API with Facebook Login » (compte IG lié à une Page) : host graph.facebook.com,
                       token de Page (n'expire pas)

.env requis : IG_APP_ID, IG_APP_SECRET, IG_REDIRECT_URI (doit être déclarée telle quelle dans l'app Meta).
  - redirect http://localhost:<port>/… → le code est capturé automatiquement par un mini-serveur local
  - sinon (ex. https://localhost:8765/callback, obligatoire en https côté Instagram Login) → le navigateur affiche
    une erreur de connexion, c'est normal : copie l'URL complète de la barre d'adresse et colle-la dans le terminal.
"""
from __future__ import annotations

import datetime as dt
import http.server
import os
import secrets
import threading
import urllib.parse
import webbrowser

import requests

from . import log
from .config import ROOT, env, settings

logger = log.get("ig_auth")
ENV_PATH = ROOT / ".env"
VERSION = lambda: env("IG_GRAPH_VERSION", "v23.0")  # noqa: E731
IG_SCOPES = "instagram_business_basic,instagram_business_manage_insights"
FB_SCOPES = "instagram_basic,instagram_manage_insights,pages_show_list,pages_read_engagement,business_management"


# ---------------------------------------------------------------- .env
def save_env(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    keys_done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if k in values:
            lines[i] = f"{k}={values[k]}"
            keys_done.add(k)
    lines += [f"{k}={v}" for k, v in values.items() if k not in keys_done]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)
    os.environ.update(values)


def _check(r) -> None:
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} : {r.text[:300]}")


def _mask(t: str) -> str:
    return t[:6] + "…" + t[-4:] if t and len(t) > 12 else "…"


# ---------------------------------------------------------------- liens
def _require() -> tuple[str, str, str]:
    app_id, secret, redirect = env("IG_APP_ID"), env("IG_APP_SECRET"), env("IG_REDIRECT_URI")
    missing = [n for n, v in (("IG_APP_ID", app_id), ("IG_APP_SECRET", secret), ("IG_REDIRECT_URI", redirect)) if not v]
    if missing:
        raise SystemExit(
            f"Manque dans .env : {', '.join(missing)}.\n"
            "  Instagram Login : app Meta → Instagram → « API setup with Instagram login » → Instagram app ID / secret ;\n"
            "                    « Set up Instagram business login » → ajoute l'URL de redirection (ex. https://localhost:8765/callback).\n"
            "  Facebook Login  : App settings → Basic → App ID / secret ; Facebook Login → Settings → Valid OAuth Redirect URIs.")
    return app_id, secret, redirect


def auth_url(flow: str, state: str) -> str:
    app_id, _, redirect = _require()
    if flow == "facebook":
        q = {"client_id": app_id, "redirect_uri": redirect, "state": state, "scope": FB_SCOPES,
             "response_type": "code", "auth_type": "rerequest"}
        return f"https://www.facebook.com/{VERSION()}/dialog/oauth?" + urllib.parse.urlencode(q)
    q = {"client_id": app_id, "redirect_uri": redirect, "response_type": "code", "scope": IG_SCOPES,
         "state": state, "force_reauth": "true", "enable_fb_login": "0"}
    return "https://www.instagram.com/oauth/authorize?" + urllib.parse.urlencode(q)


# ---------------------------------------------------------------- capture du code
def _capture_code(url: str, redirect: str, state: str) -> str:
    parsed = urllib.parse.urlparse(redirect)
    auto = parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
    result: dict = {}
    server = None
    if auto:
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result.update({k: v[0] for k, v in qs.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h2>Connexion reçue ✓, tu peux fermer cet onglet.</h2>".encode())

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer((parsed.hostname, parsed.port or 80), H)
        threading.Thread(target=server.handle_request, daemon=True).start()
    print(f"\n  Lien de connexion :\n  {url}\n")
    webbrowser.open(url)
    if auto:
        print("  → Connecte-toi dans le navigateur (avec le BON compte Instagram). J'attends le retour…")
        deadline = dt.datetime.now() + dt.timedelta(minutes=10)
        while "code" not in result and "error" not in result:
            if dt.datetime.now() > deadline:
                server.server_close()
                raise SystemExit("Pas de retour de Meta après 10 min, relance la commande.")
            threading.Event().wait(0.5)
        server.server_close()
    else:
        print("  → Connecte-toi avec le BON compte Instagram. Le navigateur finira sur une page d'erreur : c'est normal.\n"
              "    Copie l'URL complète de la barre d'adresse et colle-la ici :")
        pasted = input("  URL > ").strip()
        result = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query).items()}
    if "error" in result:
        raise SystemExit(f"Refusé par Meta : {result.get('error_description') or result['error']}")
    if result.get("state") and result["state"] != state:
        raise SystemExit("state OAuth inattendu, relance la commande.")
    return result["code"].split("#")[0]


# ---------------------------------------------------------------- échanges
def _instagram_tokens(code: str) -> dict:
    app_id, secret, redirect = _require()
    r = requests.post("https://api.instagram.com/oauth/access_token", timeout=60, data={
        "client_id": app_id, "client_secret": secret, "grant_type": "authorization_code", "redirect_uri": redirect, "code": code})
    _check(r)
    d = r.json()
    d = (d.get("data") or [d])[0]
    short = d["access_token"]
    r = requests.get("https://graph.instagram.com/access_token", timeout=60,
                     params={"grant_type": "ig_exchange_token", "client_secret": secret, "access_token": short})
    _check(r)
    ll = r.json()
    me = requests.get(f"https://graph.instagram.com/{VERSION()}/me", timeout=60,
                      params={"fields": "user_id,username", "access_token": ll["access_token"]}).json()
    expires = dt.date.today() + dt.timedelta(seconds=int(ll.get("expires_in", 5_184_000)))
    return {"token": ll["access_token"], "user_id": str(me.get("user_id") or d.get("user_id")),
            "username": me.get("username"), "expires": expires.isoformat()}


def _facebook_accounts(code: str) -> list[dict]:
    app_id, secret, redirect = _require()
    base = f"https://graph.facebook.com/{VERSION()}"
    r = requests.get(f"{base}/oauth/access_token", timeout=60,
                     params={"client_id": app_id, "client_secret": secret, "redirect_uri": redirect, "code": code})
    _check(r)
    short = r.json()["access_token"]
    r = requests.get(f"{base}/oauth/access_token", timeout=60, params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret, "fb_exchange_token": short})
    _check(r)
    user_ll = r.json()["access_token"]
    pages = requests.get(f"{base}/me/accounts", timeout=60, params={
        "fields": "name,access_token,instagram_business_account{id,username}", "access_token": user_ll}).json()
    out = []
    for p in pages.get("data", []):
        ig = p.get("instagram_business_account")
        if ig:  # token de Page dérivé d'un token long-lived : n'expire pas
            out.append({"token": p["access_token"], "user_id": ig["id"], "username": ig.get("username"),
                        "page": p.get("name"), "expires": ""})
    return out


def _pick(accounts: list[dict], account: str) -> dict | None:
    handle = ((settings().accounts.get(account, {}).get("my_handles") or {}).get("instagram") or "").lower().lstrip("@")
    for a in accounts:
        if handle and (a.get("username") or "").lower() == handle:
            return a
    if len(accounts) == 1:
        return accounts[0]
    print(f"\n  Comptes Instagram trouvés pour « {account} » :")
    for i, a in enumerate(accounts, 1):
        print(f"   {i}. @{a.get('username')} (Page : {a.get('page')})")
    choice = input("  Numéro du compte à utiliser (vide = aucun) > ").strip()
    return accounts[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(accounts) else None


# ---------------------------------------------------------------- commandes
def connect(account: str, flow: str = "instagram") -> bool:
    _, _, redirect = _require()
    state = f"{account}-{secrets.token_urlsafe(8)}"
    print(f"\n=== Compte « {account} » ({flow}) ===")
    code = _capture_code(auth_url(flow, state), redirect, state)
    if flow == "facebook":
        acc = _pick(_facebook_accounts(code), account)
    else:
        acc = _instagram_tokens(code)
    if not acc:
        print("  ✗ Aucun compte Instagram professionnel récupéré.")
        return False
    k = account.upper()
    save_env({f"IG_{k}_USER_ID": acc["user_id"], f"IG_{k}_TOKEN": acc["token"], f"IG_{k}_TOKEN_EXPIRES": acc["expires"],
              "IG_GRAPH_HOST": "graph.facebook.com" if flow == "facebook" else "graph.instagram.com",
              "IG_AUTH_FLOW": flow})
    print(f"  ✓ @{acc.get('username')} connecté (id {acc['user_id']}, token {_mask(acc['token'])}"
          + (f", expire le {acc['expires']}" if acc["expires"] else ", sans expiration") + ") → enregistré dans .env")
    return True


def refresh_if_needed(account: str, days_before: int = 10, force: bool = False) -> bool:
    """Tokens Instagram Login (60 j) : rafraîchis automatiquement quand ils approchent de l'expiration."""
    k = account.upper()
    token, exp = env(f"IG_{k}_TOKEN"), env(f"IG_{k}_TOKEN_EXPIRES")
    if not token or env("IG_AUTH_FLOW", "instagram") != "instagram" or not exp:
        return False
    if not force and dt.date.fromisoformat(exp) - dt.date.today() > dt.timedelta(days=days_before):
        return False
    r = requests.get("https://graph.instagram.com/refresh_access_token", timeout=60,
                     params={"grant_type": "ig_refresh_token", "access_token": token})
    if r.status_code != 200:
        logger.warning("refresh token %s KO : %s, relance `engine ig-auth %s`", account, r.text[:200], account)
        return False
    d = r.json()
    new_exp = (dt.date.today() + dt.timedelta(seconds=int(d.get("expires_in", 5_184_000)))).isoformat()
    save_env({f"IG_{k}_TOKEN": d["access_token"], f"IG_{k}_TOKEN_EXPIRES": new_exp})
    logger.info("token Instagram %s rafraîchi (expire le %s)", account, new_exp)
    return True


# ---------------------------------------------------------------- version dashboard (sans terminal)
_PENDING: dict[str, dict] = {}   # state → {account, flow, choices}


def begin(account: str, flow: str = "instagram") -> dict:
    state = f"{account}-{secrets.token_urlsafe(8)}"
    _PENDING[state] = {"account": account, "flow": flow}
    return {"url": auth_url(flow, state), "state": state, "redirect": env("IG_REDIRECT_URI")}


def _code_from(pasted: str) -> tuple[str | None, str | None]:
    pasted = pasted.strip()
    if "code=" not in pasted:
        return pasted.split("#")[0] or None, None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
    return (qs.get("code", [None])[0] or "").split("#")[0] or None, qs.get("state", [None])[0]


def _store(account: str, flow: str, acc: dict) -> dict:
    k = account.upper()
    save_env({f"IG_{k}_USER_ID": acc["user_id"], f"IG_{k}_TOKEN": acc["token"], f"IG_{k}_TOKEN_EXPIRES": acc["expires"],
              "IG_GRAPH_HOST": "graph.facebook.com" if flow == "facebook" else "graph.instagram.com", "IG_AUTH_FLOW": flow})
    return {"ok": True, "username": acc.get("username"), "user_id": acc["user_id"], "expires": acc["expires"]}


def complete(pasted: str, state: str | None = None, choice: str | None = None) -> dict:
    """pasted = URL de retour (ou code). choice = @username à retenir (Facebook Login, plusieurs comptes)."""
    code, url_state = _code_from(pasted) if pasted else (None, None)
    state = url_state or state
    pend = _PENDING.get(state or "")
    if not pend:
        raise ValueError("Session de connexion inconnue ou expirée, reclique sur « Connecter ».")
    account, flow = pend["account"], pend["flow"]
    if pend.get("choices"):
        acc = next((a for a in pend["choices"] if a.get("username") == choice), None)
        if not acc:
            raise ValueError("Choisis un compte dans la liste.")
        _PENDING.pop(state, None)
        return _store(account, flow, acc)
    if not code:
        raise ValueError("Pas de « code= » dans l'URL collée.")
    if flow == "facebook":
        accounts = _facebook_accounts(code)
        handle = ((settings().accounts.get(account, {}).get("my_handles") or {}).get("instagram") or "").lower().lstrip("@")
        match = [a for a in accounts if (a.get("username") or "").lower() == handle] or (accounts if len(accounts) == 1 else [])
        if not match:
            if not accounts:
                raise ValueError("Aucun compte Instagram professionnel lié à tes Pages.")
            pend["choices"] = accounts
            return {"ok": False, "choose": [a.get("username") for a in accounts], "state": state}
        _PENDING.pop(state, None)
        return _store(account, flow, match[0])
    _PENDING.pop(state, None)
    return _store(account, flow, _instagram_tokens(code))


def config_status() -> dict:
    return {"app_id": bool(env("IG_APP_ID")), "secret": bool(env("IG_APP_SECRET")), "redirect": env("IG_REDIRECT_URI"),
            "flow": env("IG_AUTH_FLOW", "instagram"),
            "accounts": {a: {"connected": bool(env(f"IG_{a.upper()}_TOKEN")), "expires": env(f"IG_{a.upper()}_TOKEN_EXPIRES")}
                         for a in settings().accounts}}
