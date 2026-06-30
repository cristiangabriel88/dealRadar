"""Import a logged-in Facebook session from Chrome into the app's profile.

Facebook's new-device 2FA blocks logging into the app's fresh Playwright browser
directly (see ``fb_login``). Chrome, where you're already logged in, is a trusted
device — but Chrome 127+ encrypts its cookies (``v20`` App-Bound Encryption) so
no other program can read them, and the cookies that actually authenticate you
(``c_user``, ``xs``) aren't even written to disk while Chrome is open.

So instead of reading Chrome's cookie store, you copy the two values yourself —
from Chrome's DevTools, where Facebook shows them to you decrypted — and this
script injects them into the app's persistent profile. Facebook then sees the
app as the same logged-in session, no 2FA. Run it once::

    python -m olx_finder.fb_import_cookies

How to find the values (takes ~30 seconds):
  1. In Chrome, open https://www.facebook.com (logged in).
  2. Press F12 -> "Application" tab -> left sidebar "Cookies" ->
     "https://www.facebook.com".
  3. Find the rows named ``c_user`` and ``xs`` and copy each "Value" cell.
     (``datr`` is optional but helps avoid checkpoints — copy it too if shown.)
"""

from __future__ import annotations

import time

import config


def _ask(label: str, required: bool = True) -> str:
    while True:
        value = input(f"Paste the '{label}' cookie value: ").strip().strip('"')
        if value or not required:
            return value
        print(f"  '{label}' is required — see the instructions above.")


def main() -> None:
    from playwright.sync_api import sync_playwright

    print(__doc__)
    c_user = _ask("c_user")
    xs = _ask("xs")
    datr = _ask("datr", required=False)

    cookies = [
        {"name": "c_user", "value": c_user},
        {"name": "xs", "value": xs},
    ]
    if datr:
        cookies.append({"name": "datr", "value": datr})
    # An explicit future expiry is essential: cookies added without one are
    # *session* cookies that Playwright keeps only in memory and discards on
    # context.close(), so they'd never reach the persistent profile on disk and
    # the next run would see a logged-out browser. A one-year expiry persists
    # them (Facebook itself sets c_user/xs for ~1 year).
    expires = int(time.time()) + 365 * 24 * 3600
    # Facebook auth cookies live on the apex domain, are HTTPS-only and secret.
    for ck in cookies:
        ck.update(
            domain=".facebook.com",
            path="/",
            secure=True,
            httpOnly=True,
            sameSite="None",
            expires=expires,
        )

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            config.FB_PROFILE_DIR,
            headless=True,
            user_agent=config.USER_AGENT,
            locale="ro-RO",
        )
        try:
            context.add_cookies(cookies)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                "https://www.facebook.com/marketplace/you/selling",
                wait_until="domcontentloaded",
            )
            ok = "login" not in page.url and not page.query_selector(
                'input[name="email"]'
            )
        finally:
            context.close()

    if ok:
        print("\nSuccess — the app is now logged into Facebook. Run the app and search.")
    else:
        print(
            "\nFacebook still shows a login screen. Double-check you copied the "
            "current 'c_user' and 'xs' values (xs rotates if you log out), then "
            "run this again."
        )


if __name__ == "__main__":
    main()
