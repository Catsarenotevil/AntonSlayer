"""Command to see various stats history"""

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

class History(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="history", description="Get various Anton history")
    @app_commands.describe(category="Category")
    @app_commands.choices(category=[
        Choice(name='Matches', value="1"),
        Choice(name='Kills', value="2"),
        Choice(name='Rating', value="3"),
    ])
    async def history(self, interaction: discord.Interaction, category: Choice[str]):
        await interaction.response.send_message(content="PONG")

# Required setup function for cogs
async def setup(bot: commands.Bot):
    await bot.add_cog(History(bot))
