"""
Anton bot bot
"""

import os
# from typing import Optional
# import random
# import logging

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from utils.database import init_db
from utils.leetify import fetch_latest_matches, process_matches
from utils.strings import load_strings, get_string

# Init
load_dotenv()
init_db()
load_strings()

# ====== ENV ======
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LEETIFY_TOKEN = os.getenv("LEETIFY_TOKEN")

GUILD_ID = os.getenv("GUILD_ID") or None
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))

TARGET_STEAM64 = os.getenv("TARGET_STEAM64") # Anton Steam64
KILLS_MAX = int(os.getenv("KILLS_MAX"))

# ====== DISCORD BOT ======
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# ====== FUNCTIONS ======
# def _pick_roast(kills: int) -> str:
#     if kills <= 3:
#         return random.choice(ROASTS_BRUTAL)
#     elif kills <= 8:
#         return random.choice(ROASTS_MEDIUM)
#     else:
#         return random.choice(ROASTS_MILD)

# async def _post_to_channel(text: Optional[str] = None, embed: Optional[discord.Embed] = None):
#     try:
#         ch = await bot.fetch_channel(TARGET_CHANNEL_ID)
#         if embed is not None:
#             # send embed (with optional content)
#             await ch.send(content=text if text else None, embed=embed)
#         else:
#             if text is None:
#                 text = ""
#             await ch.send(text)
#     except Exception:
#         logging.exception("Error")

# ====== SLASH COMMANDS ======
# @bot.tree.command(name="status", description="Visar botstatus, gräns och senaste kända info")
# async def status(interaction: discord.Interaction):
#     msg = (
#         f"✅ **Status**\n"
#         f"• Channel: `{TARGET_CHANNEL_ID}`\n"
#         f"• Anton Steam64: `{TARGET_STEAM64 or 'NOT SET'}`\n"
#         f"• Roast if Anton kills ≤ **{KILLS_MAX}**\n"
#         f"• Last map: `{last_map or 'unknown'}`\n"
#         f"• Last phase: `{last_phase or 'unknown'}`\n"
#         f"• Last Anton kills: `{last_anton_kills if last_anton_kills is not None else 'unknown'}`"
#     )
#     await interaction.response.send_message(msg, ephemeral=True)

@tasks.loop(minutes=15)
async def check_leetify():
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel is None:
        print("Channel not found!")
        return

    try:
        matches = fetch_latest_matches(TARGET_STEAM64, LEETIFY_TOKEN)
        await process_matches(matches, channel)
    except Exception as e:
        print(f"Error fetching matches: {e}")

# ====== READY ======
@bot.event
async def on_ready():
    """
    Docstring for on_ready
    """
    print(f"Logged in as {bot.user}")

    check_leetify.start()

    try:
        if GUILD_ID:
            try:
                await bot.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
                print(f"Slash commands synced to guild {GUILD_ID}.")
            except Exception as e:
                print("Guild sync error, falling back to global sync:", repr(e))
                await bot.tree.sync()
                print("Slash commands synced globally.")
        else:
            await bot.tree.sync()
            print("Slash commands synced globally.")
    except Exception as e:
        print("Slash sync error:", repr(e))

bot.run(DISCORD_TOKEN)
