import os
import re
import json
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
        return json.loads(response.choices[0].message.content)
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
    }
]

# ---------- AGENT LOOP ----------

def run_agent(user_message):
    messages = [
        {"role": "system", "content": "You are a TikTok trend strategist. Help creators identify trending hashtags relevant to their niche and suggest content ideas they can act on quickly. When velocity data is available, prioritize hashtags that are climbing fast over ones that are static. Be concise and actionable."},
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
    """Use GPT to pick the 3 most relevant trends from a platform for a given niche."""
    names = [h["name"] for h in platform_data[:20]]
    prompt = (
        f"From these {platform_key} trending topics: {json.dumps(names)}\n"
        f"Pick the 3 most interesting or relevant ones for a creator who makes '{niche}' content.\n"
        f"If none are directly related, pick the 3 most creatively connectable.\n"
        f"Return ONLY a JSON array of exactly 3 names exactly as they appear:\n"
        f'["name1", "name2", "name3"]'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        selected_names = _parse_json_safe(resp.choices[0].message.content)
        name_map = {h["name"]: h for h in platform_data}
        selected = [name_map[n] for n in selected_names if n in name_map]
        # Pad to 3 if GPT names didn't match exactly
        if len(selected) < 3:
            for h in platform_data:
                if h not in selected:
                    selected.append(h)
                if len(selected) >= 3:
                    break
        return selected[:3]
    except Exception as e:
        print(f"[NICHE PULSE] {platform_key} filter failed: {e}", flush=True)
        return platform_data[:3]


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


def niche_pulse(niche: str) -> dict:
    """Cross-platform niche search. Returns {platform_key: [3 trend dicts]}."""
    platforms = ["tiktok", "google", "youtube", "reddit"]
    results = {}
    for key in platforms:
        platform_data = get_latest_hashtags(platform=key)
        if not platform_data:
            print(f"[NICHE PULSE] No data for {key} — using GPT fallback", flush=True)
            results[key] = _gpt_niche_fallback(niche, key)
        else:
            results[key] = _filter_top3_for_niche(platform_data, niche, key)
    return results


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