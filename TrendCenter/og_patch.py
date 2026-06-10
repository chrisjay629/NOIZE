"""Inject Open Graph / Twitter share-card meta tags into Streamlit's static
index.html so links to Noize render a rich preview (title, description, image)
on iMessage, Discord, Slack, LinkedIn, X, Facebook, etc.

Streamlit's set_page_config only controls the title + favicon and does so via
client-side JS, which most link-preview crawlers don't execute. This patches the
served HTML shell directly. It runs once at container startup (see Procfile),
is idempotent, and fails quietly so it can never block the app from booting.
"""
import os

SITE_URL = "https://noize-production.up.railway.app"
IMAGE_URL = "https://raw.githubusercontent.com/chrisjay629/NOIZE/master/TrendCenter/static/og_card.png"
TITLE = "Noize — Signal in the noise"
DESCRIPTION = (
    "Real-time trend intelligence for content creators. See what's actually "
    "trending across platforms and turn any trend into ready-to-shoot content "
    "— angle, script, timing, tools, and copy-paste AI prompts, all in one window."
)

MARKER = "<!-- noize-og-tags -->"

META_BLOCK = f"""    {MARKER}
    <meta name="description" content="{DESCRIPTION}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Noize" />
    <meta property="og:title" content="{TITLE}" />
    <meta property="og:description" content="{DESCRIPTION}" />
    <meta property="og:url" content="{SITE_URL}" />
    <meta property="og:image" content="{IMAGE_URL}" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:image:alt" content="Noize — Signal in the noise" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{TITLE}" />
    <meta name="twitter:description" content="{DESCRIPTION}" />
    <meta name="twitter:image" content="{IMAGE_URL}" />
"""


def patch():
    try:
        import streamlit
    except Exception as e:
        print(f"[OG] streamlit import failed, skipping: {e}", flush=True)
        return
    index_path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
    if not os.path.exists(index_path):
        print(f"[OG] index.html not found at {index_path}, skipping", flush=True)
        return
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        if MARKER in html:
            print("[OG] meta tags already present, nothing to do", flush=True)
            return
        # Make non-JS crawlers show the right title instead of "Streamlit".
        html = html.replace("<title>Streamlit</title>", f"<title>{TITLE}</title>")
        # Inject the share-card meta block right before </head>.
        if "</head>" in html:
            html = html.replace("</head>", META_BLOCK + "  </head>", 1)
        else:
            print("[OG] no </head> found, skipping", flush=True)
            return
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
        print("[OG] share-card meta tags injected into index.html", flush=True)
    except Exception as e:
        print(f"[OG] patch failed (non-fatal): {e}", flush=True)


if __name__ == "__main__":
    patch()
