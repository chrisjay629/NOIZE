import os
import re
import json
import base64
import requests
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from database import get_latest_hashtags, get_hashtag_velocity
from scraper import scrape_hashtags

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- TOOL FUNCTIONS ----------
# These are the actual Python functions the agent can call.

def tool_get_trending_hashtags():
    """Returns the latest scraped hashtags from the database."""
    hashtags = get_latest_hashtags()
    if not hashtags:
        # If db is empty, scrape fresh
        scrape_hashtags()
        hashtags = get_latest_hashtags()
    return hashtags

def tool_filter_by_niche(niche):
    """Uses GPT to intelligently match hashtags to a user's niche based on context, not just keywords."""
    hashtags = get_latest_hashtags()
    if not hashtags:
        return []

    # Build a compact list for GPT to evaluate
    hashtag_summary = "\n".join([
        f"- #{h['name']} (category: {h.get('category') or 'uncategorized'})"
        for h in hashtags
    ])

    prompt = f"""You are matching trending TikTok hashtags to a creator's niche.

Creator's niche: "{niche}"

Here are the currently trending hashtags:
{hashtag_summary}

Return ONLY the hashtag names (without the # symbol) that are genuinely relevant to this niche. Consider related topics, synonyms, and context — not just exact keyword matches. Return them as a comma-separated list, no other text. If none are relevant, return the word: NONE"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    result = response.choices[0].message.content.strip()

    if result.upper() == "NONE" or not result:
        return []

    # Parse the comma-separated list
    matched_names = [name.strip().lstrip("#").lower() for name in result.split(",")]

    # Return full hashtag objects for matched names
    matches = [h for h in hashtags if h["name"].lower() in matched_names]
    return matches

def tool_generate_content_ideas(hashtag, niche):
    """Generates 3 content ideas for a hashtag in a given niche."""
    prompt = f"Give me 3 short, punchy TikTok content ideas for the hashtag #{hashtag} targeted at a {niche} creator. Format: numbered list, one sentence each."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def research_niche_hashtags(topic):
    """Uses GPT to suggest relevant TikTok hashtags for any topic with context."""
    prompt = (
        f'You are a TikTok hashtag research expert. A creator wants to make content about: "{topic}"\n\n'
        "Suggest 15 relevant TikTok hashtags they should consider. For each provide:\n"
        "- name: the hashtag without the # symbol\n"
        "- description: one sentence on who uses it and what content performs well\n"
        "- competition: Low, Medium, or High (based on how saturated it is)\n"
        "- content_type: the format that works best (Tutorial, Storytime, Trend, Educational, Entertainment, etc.)\n\n"
        "Return ONLY a valid JSON array, no other text:\n"
        '[{"name":"...","description":"...","competition":"...","content_type":"..."}]'
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        return _parse_json_safe(response.choices[0].message.content)
    except Exception:
        return []


def generate_blueprint(hashtag_names, niche="content creator"):
    """Generates a full production blueprint for a list of hashtags."""
    hashtag_list = ", ".join([f"#{n}" for n in hashtag_names])

    prompt = (
        f"You are an expert TikTok content strategist. A {niche} creator wants to post today "
        f"using these trending hashtags: {hashtag_list}\n\n"
        "For EACH hashtag, write a complete production blueprint using exactly this format:\n\n"
        "---\n"
        "## #[hashtag name]\n\n"
        "**Hook (first 3 seconds)**\n"
        "[What to say or show in the opening 3 seconds to stop the scroll — be specific]\n\n"
        "**Script Outline**\n"
        "[4-5 bullet points of what to cover in order — keep it under 60 seconds total]\n\n"
        "**Visual Style**\n"
        "[Describe the setting, camera angle, text overlays, pacing, and vibe]\n\n"
        "**Caption + Hashtags**\n"
        "[A ready-to-paste caption with the trending hashtag plus 4-5 supporting hashtags]\n\n"
        "**Best Time to Post**\n"
        "[Specific recommendation based on when this trend is peaking]\n\n"
        "**Recommended Tool**\n"
        "[Pick one: Phone camera / CapCut / HeyGen (AI avatar) / Runway (AI video) — and explain in one sentence why this format fits the trend]\n"
        "---\n\n"
        "Write a blueprint for every hashtag listed. Be specific, actionable, and punchy — this creator is ready to make content today."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are a TikTok content strategist creating production blueprints for a {niche} creator. Be specific and actionable."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=2000
    )
    return response.choices[0].message.content

def generate_topic_blueprint(topic, dossier=None):
    """A content blueprint for ONE investigated topic, grounded in the live
    cross-platform headlines we already pulled — so it reflects what's actually
    trending on that topic right now (no extra scraping; reuses the dossier)."""
    ctx_lines = []
    if dossier:
        for sec in dossier.get("sections", []):
            plat = sec.get("platform", "")
            for s in sec.get("stories", []):
                h = (s.get("headline") or "").strip()
                src = (s.get("source") or "").strip()
                if h:
                    ctx_lines.append(f"- [{plat}] {h} ({src})")
    ctx = "\n".join(ctx_lines[:15])
    ctx_block = (
        "\n\nWHAT'S CURRENTLY TRENDING on this topic across platforms (use this to make "
        f"the blueprint timely and specific — reference these real angles):\n{ctx}\n"
        if ctx else ""
    )
    prompt = (
        f'You are an expert short-form content strategist. A creator wants to make content '
        f'about "{topic}" right now.{ctx_block}\n'
        "Produce ONE focused, ready-to-shoot content blueprint for this topic, in exactly "
        "this markdown format:\n\n"
        f"## 📐 Blueprint: {topic}\n\n"
        "**Why now** — 1-2 sentences on the current angle / why this is hot (lean on the trending items above).\n\n"
        "**3 Content Angles** — three punchy video ideas, one line each.\n\n"
        "**Top Pick — Full Breakdown**\n"
        "- **Hook (first 3s):** what stops the scroll\n"
        "- **Script outline:** 4-5 bullets, under 60s total\n"
        "- **Visual style:** setting, camera, text overlays, pacing\n"
        "- **Caption + hashtags:** ready to paste\n\n"
        "**Best platform & format** — TikTok / YouTube Shorts / Reels, why, and best time to post.\n\n"
        "**Recommended tool** — one of: Phone camera / CapCut / HeyGen / Runway — one sentence why.\n\n"
        "Be specific, current, and actionable."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a sharp short-form content strategist. Be specific, timely, and actionable."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1400,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[TOPIC BLUEPRINT] failed: {e}", flush=True)
        return f"Couldn't generate a blueprint for **{topic}** right now — try again."


def tool_get_velocity():
    """Returns hashtags sorted by rank movement — biggest climbers first."""
    velocity = get_hashtag_velocity()
    if not velocity:
        return "No velocity data available yet — need at least 2 scrapes."
    # Return only the top 10 most useful for the agent
    return velocity[:10]

# ---------- TOOL SCHEMA ----------
# This tells the agent what tools exist and how to call them.

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_trending_hashtags",
            "description": "Get the latest trending hashtags from TikTok Creative Center.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filter_by_niche",
            "description": "Filter trending hashtags by a creator's niche (e.g. 'fitness', 'fashion', 'sports').",
            "parameters": {
                "type": "object",
                "properties": {
                    "niche": {"type": "string", "description": "The creator's niche or content category."}
                },
                "required": ["niche"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_content_ideas",
            "description": "Generate 3 content ideas for a specific hashtag and niche.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hashtag": {"type": "string", "description": "The trending hashtag without the # symbol."},
                    "niche": {"type": "string", "description": "The creator's niche."}
                },
                "required": ["hashtag", "niche"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_velocity",
            "description": "Get hashtags sorted by rank movement over time. Use this to find which hashtags are climbing fast (negative rank_change) versus fading. Best for 'what should I post about right now?' questions.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_topic_hashtags",
            "description": "Research TikTok hashtags that are genuinely relevant to a SPECIFIC topic, theme, or subject the user names (e.g. 'aliens', 'baking', 'true crime', 'skincare'). Use this whenever the user asks about a particular topic rather than 'what's trending in general'. Returns ~15 relevant hashtags, each with a description, competition level, and best content type. Do NOT fall back to unrelated general trending hashtags when the user asked about a specific topic — use this instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic, theme, or subject the creator wants to make content about."}
                },
                "required": ["topic"]
            }
        }
    }
]

# ---------- AGENT LOOP ----------

def run_agent(user_message):
    messages = [
        {"role": "system", "content": (
            "You are a TikTok trend strategist. Help creators find hashtags and content ideas they can act on quickly. "
            "Pick the right tool for the question:\n"
            "- If the user asks about a SPECIFIC topic, theme, or subject (e.g. 'aliens', 'cooking', 'true crime'), call research_topic_hashtags with that topic to get hashtags genuinely relevant to it. "
            "NEVER substitute unrelated general trending hashtags when the user named a specific topic — if nothing is trending for it, research relevant hashtags for that topic instead.\n"
            "- Use get_trending_hashtags or get_velocity only when the user asks what's trending in general or 'what should I post right now'. When velocity data is available, prioritize hashtags climbing fast over static ones.\n"
            "- Use filter_by_niche to find which of TODAY'S trending hashtags fit a creator's stated niche.\n"
            "Be concise and actionable."
        )},
        {"role": "user", "content": user_message}
    ]

    # Loop until the agent stops calling tools
    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools
        )
        msg = response.choices[0].message
        messages.append(msg)

        # If no tool call, we're done
        if not msg.tool_calls:
            return msg.content

        # Execute each tool call
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"  [agent calling: {name}({args})]")

            if name == "get_trending_hashtags":
                result = tool_get_trending_hashtags()
            elif name == "filter_by_niche":
                result = tool_filter_by_niche(args["niche"])
            elif name == "generate_content_ideas":
                result = tool_generate_content_ideas(args["hashtag"], args["niche"])
            elif name == "get_velocity":
                result = tool_get_velocity()
            elif name == "research_topic_hashtags":
                result = research_niche_hashtags(args["topic"])
            else:
                result = "Unknown tool"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result) if not isinstance(result, str) else result
            })

# ── NICHE PULSE ─────────────────────────────────────────────────

def _parse_json_safe(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _filter_top3_for_niche(platform_data, niche, platform_key):
    """Use GPT to pick the live trends GENUINELY relevant to a niche/topic.
    Returns 0-3 real trend dicts — NOT padded with unrelated items. If nothing
    on the platform genuinely relates to the topic, returns an empty list so the
    caller can top up with topic-relevant AI results instead."""
    names = [h["name"] for h in platform_data[:20]]
    prompt = (
        f"From these {platform_key} trending topics: {json.dumps(names)}\n"
        f'Return ONLY the ones GENUINELY relevant to a creator making "{niche}" content. '
        f"Related sub-topics, synonyms, and clear thematic connections count, but do NOT "
        f"stretch for loose or unrelated picks. Pick at most 3.\n"
        f"Return ONLY a JSON array of the relevant names exactly as they appear (it may be empty):\n"
        f'["name1", "name2"]  // or []'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        selected_names = _parse_json_safe(resp.choices[0].message.content)
        name_map = {h["name"]: h for h in platform_data}
        selected = [name_map[n] for n in selected_names if n in name_map]
        return selected[:3]
    except Exception as e:
        print(f"[NICHE PULSE] {platform_key} filter failed: {e}", flush=True)
        return []


def _gpt_niche_fallback(niche, platform):
    """Generate 3 niche-relevant trends for a platform when no live data exists."""
    today = datetime.now().strftime("%B %d, %Y")
    platform_contexts = {
        "tiktok":  ("TikTok hashtags",         '{"rank":"1","name":"...","posts":"2.4M","category":"Entertainment"}'),
        "google":  ("Google Search trends",     '{"rank":"1","name":"...","posts":"500K+ searches","category":"News"}'),
        "youtube": ("YouTube trending videos",  '{"rank":"1","name":"...","posts":"4.2M views","category":"Gaming"}'),
        "reddit":  ("Reddit hot posts",         '{"rank":"1","name":"...","posts":"89K upvotes","category":"r/all"}'),
    }
    url_builders = {
        "tiktok":  lambda n: f"https://www.tiktok.com/tag/{n.replace(' ','')}",
        "google":  lambda n: f"https://www.google.com/search?q={n.replace(' ','+')}",
        "youtube": lambda n: f"https://www.youtube.com/results?search_query={n.replace(' ','+')}",
        "reddit":  lambda n: f"https://www.reddit.com/search/?q={n.replace(' ','+')}&sort=hot",
    }
    ctx, example = platform_contexts.get(platform, ("trends", '{"rank":"1","name":"...","posts":"—","category":"—"}'))
    prompt = (
        f"Today is {today}. A content creator makes '{niche}' content.\n"
        f"Generate 3 currently trending {ctx} that would be relevant or interesting for them.\n"
        f"Return ONLY a JSON array of exactly 3 items:\n"
        f"[{example}]"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        data = _parse_json_safe(resp.choices[0].message.content)
        now = datetime.now().isoformat()
        builder = url_builders.get(platform, lambda n: f"https://www.google.com/search?q={n}")
        return [{
            "rank": str(h.get("rank", i + 1)),
            "name": h.get("name", ""),
            "posts": h.get("posts", ""),
            "category": h.get("category", ""),
            "url": builder(h.get("name", "")),
            "scraped_at": now,
            "platform": platform,
            "source": "gpt_fallback",
        } for i, h in enumerate(data[:3])]
    except Exception as e:
        print(f"[NICHE PULSE] GPT fallback for {platform} failed: {e}", flush=True)
        return []


def transform_niche_query(niche: str) -> list:
    """Rephrase a raw topic into 2-3 search angles so live retrieval casts a
    richer, more relevant net. e.g. 'aliens' -> ['aliens','UFO disclosure',
    'UAP sighting']. Always includes the original; falls back to [niche] on any
    error. Kept lean (<=3) to hold latency and API cost down."""
    niche = (niche or "").strip()
    if not niche:
        return []
    prompt = (
        f'A content creator is investigating the topic: "{niche}".\n'
        "Give 2 ADDITIONAL closely-related search angles (synonyms, the trending "
        "sub-topic, or the specific event driving interest) that would surface the "
        "best current cross-platform content. Keep them tight and on-topic — no "
        "loose stretches.\n"
        'Return ONLY a JSON array of 2 short strings, e.g. ["angle one","angle two"].'
    )
    angles = [niche]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        extra = _parse_json_safe(resp.choices[0].message.content) or []
        for a in extra:
            if isinstance(a, str) and a.strip() and a.strip().lower() != niche.lower():
                angles.append(a.strip())
    except Exception as e:
        print(f"[NICHE PULSE] query transform failed: {e}", flush=True)
    return angles[:3]


def _search_platform_live(platform_key, angles, want=8):
    """Run the real per-query search for a platform across all query angles,
    dedup by name, and return the combined live rows (capped at `want`)."""
    from platforms import search_google_news, search_youtube, search_reddit
    fetchers = {
        "google":  search_google_news,
        "youtube": search_youtube,
        "reddit":  search_reddit,
    }
    fetch = fetchers.get(platform_key)
    if not fetch:
        return []
    rows, seen = [], set()
    for angle in angles:
        for row in fetch(angle, limit=4):
            name = (row.get("name") or "").strip().lower()
            if name and name not in seen:
                rows.append(row)
                seen.add(name)
            if len(rows) >= want:
                return rows
    return rows


def _gather_live_rows(niche, angles):
    """Fetch live rows once per platform so cards AND the dossier can share them
    (avoids paying for the same retrieval twice). Returns {platform: [rows]}.
    TikTok has no free search API, so it uses DB trends."""
    raw = {"tiktok": get_latest_hashtags(platform="tiktok") or []}
    for key in ["google", "youtube", "reddit"]:
        raw[key] = _search_platform_live(key, angles)
    return raw


def _cards_from_rows(niche, raw):
    """Turn gathered rows into the {platform: [up to 3]} card shape: keep only
    genuinely relevant live rows, top up with AI only when a platform is short."""
    results = {}
    for key in ["tiktok", "google", "youtube", "reddit"]:
        platform_data = raw.get(key) or []
        relevant = _filter_top3_for_niche(platform_data, niche, key) if platform_data else []
        if len(relevant) < 3:
            seen = {(h.get("name") or "").strip().lower() for h in relevant}
            for g in _gpt_niche_fallback(niche, key):
                gname = (g.get("name") or "").strip().lower()
                if gname and gname not in seen:
                    relevant.append(g)
                    seen.add(gname)
                if len(relevant) >= 3:
                    break
        results[key] = relevant[:3]
    return results


def niche_pulse(niche: str) -> dict:
    """Cross-platform niche search. Returns {platform_key: [up to 3 trend dicts]}.
    Grounded cascade: transform query -> live retrieval -> relevance filter ->
    AI top-up only when short. (Kept for callers that just want the cards.)"""
    angles = transform_niche_query(niche) or [niche]
    return _cards_from_rows(niche, _gather_live_rows(niche, angles))


def _build_sites_panel(raw, limit=6):
    """The desktop thumbnail rail: only rows with a REAL image (YouTube/Reddit) —
    news favicons are excluded so the rail stays clean photo thumbnails."""
    panel, seen = [], set()
    ordered = (raw.get("youtube") or []) + (raw.get("reddit") or [])
    for r in ordered:
        url, thumb = r.get("url"), r.get("thumbnail")
        if not url or url in seen or not thumb or r.get("thumb_kind") != "image":
            continue
        panel.append({
            "title": r.get("name", "")[:90],
            "source": r.get("source_name") or r.get("category") or r.get("platform", ""),
            "thumb": thumb,
            "url": url,
            "platform": r.get("platform", ""),
        })
        seen.add(url)
        if len(panel) >= limit:
            return panel
    return panel


def _synthesize_dossier_sections(niche, raw):
    """Feed the REAL gathered rows to GPT and have it organize them into per-
    platform sections (themed heading + 2-3 stories). GPT only organizes — every
    story references a provided row by number, so URLs/sources stay real and
    nothing is invented. Returns a list of section dicts."""
    # Number every real row globally so GPT can only cite what we gave it.
    indexed, lines = {}, []
    n = 0
    label = {"google": "Google News", "youtube": "YouTube", "reddit": "Reddit", "tiktok": "TikTok"}
    for key in ["google", "youtube", "reddit"]:           # tiktok rows are hashtags, not stories
        for r in (raw.get(key) or []):
            if not r.get("name"):
                continue
            n += 1
            indexed[n] = r
            blurb = (r.get("blurb") or "")[:160]
            lines.append(f'{n}. [{label.get(key, key)}] {r.get("name","")[:120]} — {r.get("source_name","")} :: {blurb}')
    if not lines:
        return []
    prompt = (
        f'You are Pugson, an investigator briefing a content creator on "{niche}". '
        "Below are REAL items pulled live from each platform, each with a number.\n\n"
        + "\n".join(lines)
        + "\n\nGroup them into per-platform sections. For each platform that has items, "
        "write a short themed heading (max 8 words) and 2-3 story bullets. Each bullet "
        "must reference ONE item by its number and give a punchy 1-sentence take in a "
        "sharp, slightly noir tone. Use ONLY the items above — do NOT invent stories, "
        "numbers, or platforms. If a platform has no items, omit it.\n"
        'Return ONLY JSON (no markdown):\n'
        '{"sections":[{"platform":"google|youtube|reddit","heading":"...",'
        '"stories":[{"ref":<item number>,"take":"one sentence"}]}]}'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},   # guarantees valid JSON
        )
        data = _parse_json_safe(resp.choices[0].message.content) or {}
    except Exception as e:
        print(f"[DOSSIER] synthesis failed: {e}", flush=True)
        data = {}

    sections = []
    for sec in data.get("sections", []):
        stories, plats = [], []
        for s in sec.get("stories", []):
            row = indexed.get(s.get("ref"))
            if not row:
                continue                                   # drop any hallucinated ref
            plats.append(row.get("platform", ""))
            stories.append({
                "headline": row.get("name", ""),
                "take": (s.get("take") or "").strip(),
                "source": row.get("source_name") or row.get("category", ""),
                "url": row.get("url", ""),
                "thumbnail": row.get("thumbnail", ""),
                "thumb_fallback": row.get("thumb_fallback", ""),
                "thumb_kind": row.get("thumb_kind", "image"),
            })
        if stories:
            # Trust the rows, not GPT's label, for the platform (styling/icon).
            platform = max(set(plats), key=plats.count) if plats else sec.get("platform", "")
            sections.append({
                "platform": platform,
                "heading": (sec.get("heading") or "").strip(),
                "stories": stories[:3],
            })
    return sections


def build_dossier(niche: str) -> dict:
    """The INVESTIGATE dossier: one live gather powers everything.
    Returns {query, cards, sections, sites_panel}.
    - cards:       {platform: [up to 3]} for the existing pulse renderer
    - sections:    per-platform themed digest, grounded in real rows
    - sites_panel: thumbnail rail (mostly YouTube)"""
    angles = transform_niche_query(niche) or [niche]
    raw = _gather_live_rows(niche, angles)
    return {
        "query": niche,
        "angles": angles,
        "cards": _cards_from_rows(niche, raw),
        "sections": _synthesize_dossier_sections(niche, raw),
        "sites_panel": _build_sites_panel(raw),
    }


# ── AUTO TREND ARTICLES ─────────────────────────────────────────

def generate_trend_articles() -> list:
    """Generates 3 mini trending news blurbs (News, Music & Film, Gaming).
    Uses live trending data from the DB as context when available."""
    today = datetime.now().strftime("%B %d, %Y")

    # Pull live context from DB
    google_trends = get_latest_hashtags(platform="google")[:8]
    tiktok_trends = get_latest_hashtags(platform="tiktok")[:8]
    combined = google_trends or tiktok_trends
    trend_ctx = ""
    if combined:
        names = [h["name"] for h in combined]
        trend_ctx = f"Currently trending topics include: {', '.join(names)}. Use these as inspiration where relevant."

    prompt = (
        f"Today is {today}. {trend_ctx}\n\n"
        "Write 3 short trending news blurbs for a real-time trend app called Noize. "
        "One for each category: News, Music & Film, Gaming. "
        "Each should feel like a punchy breaking news headline + 2-sentence summary — "
        "specific, current, and engaging. Do NOT make things up that are factually wrong; "
        "lean on plausible current events.\n\n"
        "Return ONLY a valid JSON array (no markdown):\n"
        '[\n'
        '  {"category":"News","headline":"...","summary":"...","tag":"Breaking","search_query":"..."},\n'
        '  {"category":"Music & Film","headline":"...","summary":"...","tag":"Trending","search_query":"..."},\n'
        '  {"category":"Gaming","headline":"...","summary":"...","tag":"Hot","search_query":"..."}\n'
        ']'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        articles = _parse_json_safe(resp.choices[0].message.content)
        # Attach search URLs
        cat_colors = {
            "News":         "#4285f4",
            "Music & Film": "#fe2c55",
            "Gaming":       "#AAFF00",
        }
        for a in articles:
            q = a.get("search_query", a.get("headline", ""))
            a["url"]   = f"https://www.google.com/search?q={q.replace(' ', '+')}"
            a["color"] = cat_colors.get(a.get("category", ""), "#AAFF00")
        return articles[:3]
    except Exception as e:
        print(f"[TREND ARTICLES] Failed: {e}", flush=True)
        return []


# ── STRANGE SIGNALS ─────────────────────────────────────────────

def _gpt_strange_signals_fallback(limit=5):
    """Last resort: when both Reddit and Google come up empty (e.g. blocked on
    Railway), have GPT invent original strange-signal case files so the radar
    is never blank. Each gets a summary here; images are generated lazily when
    a case is opened (image_url left empty)."""
    print("[STRANGE] Using GPT fallback to generate signals", flush=True)
    types = ["UFO", "Paranormal", "Strange", "Unsolved", "Cryptid", "Glitch"]
    prompt = (
        "You are Pugson, a noir detective who catalogues strange, unexplained "
        f"signals from the internet's weirdest corners. Invent {limit} ORIGINAL, "
        "fictional-but-plausible strange reports (UFO sightings, hauntings, "
        "cryptids, unsolved mysteries, reality glitches). Each should feel like "
        "a real anonymous internet account. Vary the 'type' across: "
        + ", ".join(types) + ".\n\n"
        "Return ONLY a JSON array (no markdown) of exactly "
        f"{limit} objects:\n"
        '[{"title":"short eerie headline (max 14 words)",'
        '"type":"one of ' + "/".join(types) + '",'
        '"body":"2-3 sentence first-person account of the strange event",'
        '"summary":"ONE ominous detective sentence framing the mystery (max 24 words)"}]'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        data = _parse_json_safe(resp.choices[0].message.content) or []
    except Exception as e:
        print(f"[STRANGE] GPT fallback failed: {e}", flush=True)
        return []

    signals = []
    for i, d in enumerate(data[:limit]):
        title = (d.get("title") or "").strip()
        if not title:
            continue
        sig_type = d.get("type", "Strange")
        if sig_type not in types:
            sig_type = "Strange"
        signals.append({
            "title": title[:160],
            "subreddit": "Anonymous wire",
            "type": sig_type,
            "rank": i + 1,
            "permalink": f"https://www.google.com/search?q={title.replace(' ', '+')}",
            "selftext": (d.get("body") or "")[:400],
            "summary": (d.get("summary") or title).strip(),
            "image_url": "",
            "platform": "gpt",
            "source": "gpt_fallback",
        })
    print(f"[STRANGE] GPT fallback produced {len(signals)} signals", flush=True)
    return signals


def generate_strange_signals(limit=5):
    """Layered sourcing so the radar is never empty:
    1) real weird/unexplained Reddit posts,
    2) strange news from Google News (works where Reddit is IP-blocked),
    3) GPT-generated original case files as a last resort.
    Returns up to `limit` signals (hottest first), each with a noir summary."""
    from platforms import scrape_strange_signals, scrape_strange_signals_google
    signals = scrape_strange_signals(limit=limit)
    if not signals:
        print("[STRANGE] Reddit empty — trying Google News", flush=True)
        signals = scrape_strange_signals_google(limit=limit)
    if not signals:
        print("[STRANGE] Google empty — falling back to GPT", flush=True)
        return _gpt_strange_signals_fallback(limit=limit)

    # One batched GPT call to write a punchy detective-style line per post.
    numbered = []
    for i, s in enumerate(signals):
        body = s.get("selftext", "")[:300].replace("\n", " ")
        numbered.append(f'{i + 1}. [{s["subreddit"]}] {s["title"]} :: {body}')
    prompt = (
        "You are Pugson, a noir detective cataloguing strange signals from the "
        "internet's weirdest corners. For each Reddit post below, write ONE "
        "intriguing sentence (max 24 words) that captures the mystery in a "
        "slightly ominous detective tone. Do NOT invent facts beyond the "
        "title/body — just frame what's there.\n\n"
        + "\n".join(numbered)
        + f"\n\nReturn ONLY a JSON array of exactly {len(signals)} strings, in order."
    )
    summaries = []
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        summaries = _parse_json_safe(resp.choices[0].message.content) or []
    except Exception as e:
        print(f"[STRANGE] Summary GPT failed: {e}", flush=True)

    for i, s in enumerate(signals):
        if i < len(summaries) and isinstance(summaries[i], str) and summaries[i].strip():
            s["summary"] = summaries[i].strip()
        elif s.get("selftext"):
            s["summary"] = s["selftext"][:160] + ("…" if len(s["selftext"]) > 160 else "")
        else:
            s["summary"] = s["title"]
    return signals


def _generate_case_image(signal):
    """Generate an atmospheric noir image for a story when the post has none.
    Returns a data-URI string (persists past OpenAI's 1h URL expiry) or ''."""
    style = {
        "UFO":       "unidentified lights in a night sky, grainy, eerie",
        "Paranormal":"a haunted, shadowy interior, cold and unsettling",
        "Unsolved":  "a cold-case evidence board, dim and mysterious",
        "Glitch":    "reality glitching, surreal doubled imagery",
        "Cryptid":   "a dark forest with something half-seen in the trees",
        "Strange":   "an uncanny, dreamlike scene that feels deeply off",
    }.get(signal.get("type", "Strange"), "an uncanny, unsettling scene")
    prompt = (
        f"A moody, cinematic noir illustration: {style}. "
        f"Inspired by this strange report: \"{signal.get('title','')[:160]}\". "
        "Dark teal-and-amber detective palette, film-grain, atmospheric fog, "
        "no text, no words, no watermark."
    )
    try:
        resp = client.images.generate(
            model="gpt-image-1-mini", prompt=prompt, size="1024x1024",
            quality="low", n=1,
        )
        d = resp.data[0]
        # gpt-image returns inline b64; older models may return a hosted url.
        b64 = getattr(d, "b64_json", None)
        if not b64:
            img = requests.get(d.url, timeout=20)
            img.raise_for_status()
            b64 = base64.b64encode(img.content).decode("ascii")
        print("[STRANGE] Generated a case image via gpt-image", flush=True)
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[STRANGE] Image generation failed: {e}", flush=True)
        return ""


def generate_case_file(signal):
    """On demand: turn ONE real strange post into Pugson's original noir
    case-file write-up (his retelling, not a copy), and make sure it has an
    image (real post image preferred, DALL-E fallback). Mutates + returns the
    signal with 'case_headline', 'case_body' (list of paragraphs) and
    'image_url'. Cached by the caller, so this runs once per story."""
    if signal.get("case_body"):
        return signal

    body = (signal.get("selftext") or "")[:700].replace("\n", " ")
    prompt = (
        "You are Pugson, a hard-boiled noir detective who writes up strange "
        "cases from the internet's weirdest corners for an outlet called Noize. "
        "Below is a REAL Reddit post. Rewrite it as YOUR OWN original short case "
        "file in an atmospheric noir-detective voice — your framing, your words, "
        "not a copy. Stay faithful to the actual facts in the post; do NOT invent "
        "concrete details (names, dates, numbers) that aren't there. If facts are "
        "thin, lean into the mood and the open questions instead of fabricating.\n\n"
        f"SUBREDDIT: {signal.get('subreddit','')}\n"
        f"TITLE: {signal.get('title','')}\n"
        f"BODY: {body or '(no body text — work from the title)'}\n\n"
        "Return ONLY JSON (no markdown):\n"
        '{"headline":"a punchy original headline (max 12 words)",'
        '"body":["paragraph 1","paragraph 2","paragraph 3"]}'
        "\nEach paragraph 2-4 sentences. Exactly 3 paragraphs."
    )
    headline, paragraphs = signal.get("title", ""), []
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        data = _parse_json_safe(resp.choices[0].message.content) or {}
        headline = (data.get("headline") or signal.get("title", "")).strip()
        paragraphs = [p.strip() for p in (data.get("body") or []) if isinstance(p, str) and p.strip()]
    except Exception as e:
        print(f"[STRANGE] Case-file GPT failed: {e}", flush=True)
    if not paragraphs:
        paragraphs = [signal.get("summary") or signal.get("selftext") or signal.get("title", "")]

    signal["case_headline"] = headline
    signal["case_body"] = paragraphs

    # Image: prefer the real post image; otherwise generate one (once).
    if not signal.get("image_url"):
        signal["image_url"] = _generate_case_image(signal)
    return signal


# ---------- CLI ----------

if __name__ == "__main__":
    print("TikTok Trends Agent — type your niche or question. (Ctrl+C to quit)\n")
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        print("\nAgent: ", end="", flush=True)
        answer = run_agent(user_input)
        print(answer + "\n")