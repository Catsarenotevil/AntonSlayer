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
from utils.strings import load_strings

# Init
load_dotenv()
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
discord.Intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@tasks.loop(minutes=15)
async def check_leetify():
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel is None:
        print("Channel not found!")
        return

    try:
        matches = await fetch_latest_matches(TARGET_STEAM64, LEETIFY_TOKEN)
        await process_matches(matches, channel, TARGET_STEAM64, LEETIFY_TOKEN)
    except Exception as e:
        print(f"Error fetching matches: {e}")

# ====== READY ======
@bot.event
async def on_ready():
    """
    Docstring for on_ready
    """
    print(f"Logged in as {bot.user}")

    await init_db()
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

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("_"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

# Run bot
async def main():
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)

import asyncio
asyncio.run(main())
