\
\
\
\
\
\
\
\
   

import base64
import hashlib
import http.server
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from savegd_core.config import GOOGLE_SCOPES
from savegd_core.paths import oauth_client_file, token_file


AUTH_URI  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _load_client() -> dict:
    cf = oauth_client_file()
    if not cf.exists():
        raise FileNotFoundError(
            f"OAuth client file not found:\n{cf}\n\n"
            "Copy oauth_client.json from steam_lookup_assets/ into that folder."
        )
    data = json.loads(cf.read_text(encoding="utf-8"))
    return data.get("installed", data)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    auth_code = None
    error     = None
    error_desc = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if "code" in qs:
            _CallbackHandler.auth_code = qs["code"][0]
        elif "error" in qs:
            _CallbackHandler.error      = qs["error"][0]
            _CallbackHandler.error_desc = qs.get("error_description", [""])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if _CallbackHandler.error:
            html = (
                "<html><body style='font-family:sans-serif;padding:40px;"
                "background:#0a0d14;color:#e8eaf6'>"
                "<h2 style='color:#ef5350'>Authorization failed</h2>"
                f"<p>{_CallbackHandler.error}</p>"
                f"<p>{_CallbackHandler.error_desc}</p>"
                "</body></html>"
            )
        else:
            html = (
                "<html><body style='font-family:sans-serif;padding:40px;"
                "background:#0a0d14;color:#e8eaf6'>"
                "<h2 style='color:#4fc3f7'>SteamLookup Save Sync</h2>"
                "<p>Authorization complete. You can close this tab.</p>"
                "</body></html>"
            )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, *a):
        pass


def run_setup_flow() -> bool:
\
\
\
       
    try:
        client = _load_client()
    except FileNotFoundError as e:
        print(e)
        return False

    client_id     = client.get("client_id", "")
    client_secret = client.get("client_secret", "")
    if not client_id:
        print("oauth_client.json is missing client_id")
        return False

                                                                        
                                                                        
                                 
    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]

                                                                        
                                                                        
                                                      
    redirect_uri = f"http://127.0.0.1:{port}/"

    verifier, challenge = _pkce_pair()

    params = {
        "client_id":             client_id,
        "redirect_uri":          redirect_uri,
        "response_type":         "code",
        "scope":                 " ".join(GOOGLE_SCOPES),
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "access_type":           "offline",
        "prompt":                "consent",
    }

    auth_url = AUTH_URI + "?" + urllib.parse.urlencode(params)

                                                                        
    def serve():
        try:
            server.handle_request()
        except Exception:
            pass

    threading.Thread(target=serve, daemon=True).start()

    print()
    print("=" * 66)
    print("  GOOGLE SIGN-IN")
    print("=" * 66)
    print()
    print(f"  Listening on 127.0.0.1:{port}")
    print()
    print("  1. A browser window will open.")
    print("  2. Sign in with your Google account.")
    print("  3. Google will warn that the app is 'unverified'.")
    print("     Click  Advanced  ->  Go to SteamLookup (unsafe).")
    print("  4. Grant access to Google Drive.")
    print()
    print("  The browser will then show 'Authorization complete.'")
    print("  You can close that tab.")
    print()
    print("=" * 66)
    print()

    webbrowser.open(auth_url)

                                                                        
    end = time.time() + 180
    while time.time() < end:
        if _CallbackHandler.auth_code or _CallbackHandler.error:
            break
        time.sleep(0.2)

    server.server_close()

    if _CallbackHandler.error:
        print(f"\n❌ Authorization error: {_CallbackHandler.error}")
        if _CallbackHandler.error_desc:
            print(f"   {_CallbackHandler.error_desc}")
        return False

    if not _CallbackHandler.auth_code:
        print("\n❌ Timed out waiting for authorization (3 minutes).")
        return False

    print("\nExchanging authorization code for tokens...")

                                                                        
    token_body = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,                                          
        "code":          _CallbackHandler.auth_code,
        "code_verifier": verifier,
        "grant_type":    "authorization_code",
        "redirect_uri":  redirect_uri,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URI, data=token_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept":       "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            token_data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print()
        print("=" * 66)
        print(f"  ❌ TOKEN EXCHANGE FAILED (HTTP {e.code})")
        print("=" * 66)
        print()
        try:
            err = json.loads(body)
            print(f"  Error:       {err.get('error', '?')}")
            print(f"  Description: {err.get('error_description', '?')}")
            print(f"  Redirect URI sent: {redirect_uri}")
        except Exception:
            print(body[:600])
        print()
        print("=" * 66)
        return False

    token_data.setdefault("client_id", client_id)
    token_data.setdefault("client_secret", client_secret)

    tf = token_file()
    tf.write_text(json.dumps(token_data, indent=2), encoding="utf-8")

    print()
    print(f"✅ Authorization saved to:")
    print(f"   {tf}")
    print()
    return True