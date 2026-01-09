"""
Leetify helper
"""

import aiohttp
import discord
from utils.database import get_last_match_id, set_last_match_id

URL = "https://api-public.cs-prod.leetify.com"

async def fetch_latest_matches(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{URL}/v3/profile/matches") as r:
            r.raise_for_status()
            matches = await r.json()

        if not matches:
            print("No matches found")
            return

    return matches

async def process_matches(matches: list, channel, token: str):
    latest_match = matches[0]
    latest_match_id = latest_match["id"]

    last_match_id = await get_last_match_id()
    if latest_match_id == last_match_id:
        return  # already posted

    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(
            f"{URL}/v2/matches/{latest_match_id}"
        ) as resp:
            if resp.status != 200:
                return
            match_data = await resp.json()

    stats = match_data["playerStats"]
    kd = stats["killDeathRatio"]
    adr = stats["adr"]

    embed = discord.Embed(
        title="New Match",
        color=discord.Color.green()
    )
    embed.add_field(name="K/D", value=kd)
    embed.add_field(name="ADR", value=adr)

    await channel.send(embed=embed)

    await set_last_match_id(latest_match_id)
