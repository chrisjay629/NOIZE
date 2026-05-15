import os
import json
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


def generate_blueprint(hashtag_names, niche="content creator"):
    """Generates a full production blueprint for a list of hashtags."""
    sections = []
    for name in hashtag_names:
        sections.append(f"#{name}")
    hashtag_list = ", ".join(sections)

    prompt = f"""You are an expert TikTok content strategist. A {niche} creator wants to post today using these trending hashtags: {hashtag_list}

For EACH hashtag, write a complete production blueprint using exactly this format:

---
## #{name_placeholder}

**Hook (first 3 seconds)**
[What to say or show in the opening 3 seconds to stop the scroll — be specific]

**Script Outline**
[4-5 bullet points of what to cover in order — keep it under 60 seconds total]

**Visual Style**
[Describe the setting, camera angle, text overlays, pacing, and vibe]

**Caption + Hashtags**
[A ready-to-paste caption with the trending hashtag plus 4-5 supporting hashtags]

**Best Time to Post**
[Specific recommendation based on when this trend is peaking]

**Recommended Tool**
[Pick one: Phone camera / CapCut / HeyGen (AI avatar) / Runway (AI video) — and explain in one sentence why this format fits the trend]
---

Replace #{name_placeholder} with the actual hashtag name. Write a blueprint for every hashtag listed. Be specific, actionable, and punchy — this creator is ready to make content today."""

    # Replace placeholder with actual first hashtag name for the format example
    prompt = prompt.replace("#{name_placeholder}", "#{hashtag_name}")

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