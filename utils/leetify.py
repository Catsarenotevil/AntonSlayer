"""
Leetify helper
"""

from datetime import datetime
from pathlib import Path
import aiohttp
import discord
from utils.database import get_last_match_id, set_last_match_id, insert_match
from utils.strings import get_random_string

URL = "https://api-public.cs-prod.leetify.com"

async def fetch_latest_matches(steamid: str, token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = { "steam64_id": steamid }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{URL}/v3/profile/matches", params=params) as r:
            r.raise_for_status()
            matches = await r.json()

        if not matches:
            print("No matches found")
            return

    return matches

async def process_matches(matches: dict, channel, steamid: str, token: str):
    for match in matches:
        await insert_match(match)

    latest_match = matches[0]
    latest_match_id = latest_match["id"]

    last_match_id = await get_last_match_id()
    if latest_match_id == last_match_id:
        return  # already posted

    # This should probably be made its own function.
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = { "steam64_id": steamid }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{URL}/v3/profile", params=params) as resp:
            if resp.status != 200:
                return
            profile_data = await resp.json()

    # Profile stats
    winrate = profile_data["winrate"]
    premier_rank = profile_data["ranks"]["premier"]
    faceit_rank = profile_data["ranks"]["faceit"]
    leetify_rank = profile_data["ranks"]["leetify"]

    # Match stats
    stats = latest_match["stats"][0]
    rating: float = stats["leetify_rating"]
    total_kills = stats["total_kills"]
    total_deaths = stats["total_deaths"]
    kd_ratio = stats["kd_ratio"]
    mvps = stats["mvps"]
    total_assists = stats["total_assists"]
    total_damage = stats["total_damage"]

    if rating > 1.5:
        color = discord.Color.green()
        message = get_random_string("MILD")
    elif 1.5 >= rating > -3.0:
        color = discord.Color.yellow()
        message = get_random_string("MEDIUM")
    else:
        color = discord.Color.red()
        message = get_random_string("BRUTAL")

    embed = discord.Embed(
        title="📊 Post-Anton-Match Analysis",
        description=message,
        color=color,
        timestamp=datetime.strptime(latest_match["finished_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
    )

    embed.add_field(name="\u200B", value="**Match Stats:**", inline=False)
    embed.add_field(name="💀 Kills", value=f"┗ ` {total_kills} `", inline=True)
    embed.add_field(name="🪦 Deaths", value=f"┗ ` {total_deaths} `", inline=True)
    embed.add_field(name="🎯 K/D", value=f"┗ ` {kd_ratio} `", inline=True)
    embed.add_field(name="🏆 MVPs", value=f"┗ ` {mvps} `", inline=True)
    embed.add_field(name="🤝 Assists", value=f"┗ ` {total_assists} `", inline=True)
    embed.add_field(name="🥊 Damage", value=f"┗ ` {total_damage} `", inline=True)

    embed.add_field(name="\u200B", value="**Post-Match Stats:**", inline=False)
    embed.add_field(name=f"Win Rate - {winrate*100}%", value=f"{progress_bar(winrate)}", inline=False)
    embed.add_field(name="Premier Rank", value=f"┗ ` {premier_rank} `", inline=True)
    embed.add_field(name="Faceit Rank", value=f"┗ ` {faceit_rank} `", inline=True)
    embed.add_field(name="Leetify Rating", value=f"┗ ` {leetify_rank} `", inline=True)

    team_scores = latest_match["team_scores"]
    initial_team = stats["initial_team_number"]
    scores = {team["team_number"]: team["score"] for team in team_scores}

    score = scores[initial_team]
    opponent_scores = [score for team, score in scores.items() if team != initial_team]
    opponent_score = max(opponent_scores)

    if score > opponent_score:
        result = "win"
    elif score < opponent_score:
        result = "loss"
    else:
        result = "tie"

    result_image = Path("assets/match") / f"{result}.png"
    result_file = discord.File(result_image, filename="result_image.png")
    embed.set_image(url="attachment://result_image.png")

    map_image = get_map_image(latest_match["map_name"])
    map_file = discord.File(map_image, filename="map_image.png")
    embed.set_footer(
        text=f"{latest_match["map_name"]} - {latest_match["team_scores"][0]["score"]}:{latest_match["team_scores"][1]["score"]}",
        icon_url="attachment://map_image.png"
    )

    await channel.send(files=[result_file, map_file], embed=embed)

    await set_last_match_id(latest_match_id)

IMAGE_DIR = Path("assets/maps")
FALLBACK_IMAGE = IMAGE_DIR / "misc.png"

def get_map_image(map_name: str) -> Path:
    image_path = IMAGE_DIR / f"{map_name}.png"
    return image_path if image_path.exists() else FALLBACK_IMAGE

def progress_bar(winrate, width=45):
    winrate = max(0, min(winrate, 1))
    filled = int(winrate * width)

    GREEN = "\u001b[32;1m"
    RED = "\u001b[31;1m"
    RESET = "\u001b[0;0m"

    bar = (
        GREEN + "■" * filled +
        RED + "■" * (width - filled) +
        RESET
    )

    return f"```ansi\n{bar}\n```"
