"""
Leetify helper
"""

import aiohttp
import discord
from utils.database import get_last_match_id, set_last_match_id

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

    # mvps = stats["mvps"]
    total_kills = stats["total_kills"]
    total_deaths = stats["total_deaths"]
    # kd_ratio = stats["kd_ratio"]
    # total_assists = stats["total_assists"]
    # total_damage = stats["total_damage"]

    embed = discord.Embed(
        title="Post-Match Analysis",
        color=discord.Color.green()
    )
    embed.add_field(name="KILLS", value=total_kills)
    embed.add_field(name="DEATHS", value=total_deaths)

    await channel.send(embed=embed)

    await set_last_match_id(latest_match_id)
