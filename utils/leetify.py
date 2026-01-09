"""
Leetify helper
"""

from datetime import datetime
import aiohttp
import discord
from utils.database import get_last_match_id, set_last_match_id
from utils.strings import get_random_string

URL = "https://api-public.cs-prod.leetify.com"

async def fetch_latest_matches(steamid: str, token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = {
        "steam64_id": {steamid},
        # OR could use "id" if we have the Leetify user ID
        # "id": "leetify_user_id_here"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{URL}/v3/profile/matches", params=params) as r:
            r.raise_for_status()
            matches = await r.json()

        if not matches:
            print("No matches found")
            return

    return matches

async def process_matches(matches: list, channel):
    latest_match = matches[0]
    latest_match_id = latest_match["id"]

    last_match_id = await get_last_match_id()
    if latest_match_id == last_match_id:
        return  # already posted

    # headers = {
    #     "Authorization": f"Bearer {token}",
    #     "Accept": "application/json",
    # }
    # async with aiohttp.ClientSession(headers=headers) as session:
    #     async with session.get(
    #         f"{URL}/v2/matches/{latest_match_id}"
    #     ) as resp:
    #         if resp.status != 200:
    #             return
    #         match_data = await resp.json()

    stats = latest_match["stats"]

    rating = stats["leetify_rating"]
    # mvps = stats["mvps"]
    total_kills = stats["total_kills"]
    total_deaths = stats["total_deaths"]
    # kd_ratio = stats["kd_ratio"]
    # total_assists = stats["total_assists"]
    # total_damage = stats["total_damage"]

    if rating < 0.5:
        color = discord.Color.red()
        message = get_random_string("BRUTAL")
    elif 0.5 <= rating < 0.8:
        color = discord.Color.orange()
        message = get_random_string("MEDIUM")
    else:
        color = discord.Color.green()
        message = get_random_string("MILD")

    embed = discord.Embed(
        title=f"📊 Post-Match Analysis - {rating}",
        description=message,
        color=color,
        timestamp=datetime.strptime(latest_match["finished_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
    )
    embed.add_field(name="KILLS", value=total_kills)
    embed.add_field(name="DEATHS", value=total_deaths)
    embed.set_footer(
        text=f"{latest_match["map_name"]} - {latest_match["team_scores"][0]["score"]}:{latest_match["team_scores"][1]["score"]}",
        # icon_url="MAP IMAGE HERE?"
    )

    await channel.send(embed=embed)

    await set_last_match_id(latest_match_id)
