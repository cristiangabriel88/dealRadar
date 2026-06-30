"""One-time Facebook login for the Marketplace source.

Marketplace is login-gated, so the :class:`~olx_finder.sources.facebook.FacebookSource`
drives a headless browser that reuses a saved, logged-in session. This helper
creates that session: it opens a *visible* Chromium with the same persistent
profile dir the source uses, you log into Facebook by hand, and pressing Enter
closes the window — the cookies persist on disk for every later search.

Run once (and again only if the session ever expires)::

    python -m olx_finder.fb_login
"""

from __future__ import annotations

import config


def main() -> None:
    from playwright.sync_api import sync_playwright

    print(f"Opening a browser with profile: {config.FB_PROFILE_DIR}")
    print(
        "Log into Facebook in the window that appears, make sure you can open\n"
        "Marketplace, then come back here and press Enter to save the session."
    )
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            config.FB_PROFILE_DIR, headless=False
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        try:
            input("\nPress Enter once you are logged in... ")
        finally:
            context.close()
    print("Session saved. You can now search Facebook Marketplace from the app.")


if __name__ == "__main__":
    main()
