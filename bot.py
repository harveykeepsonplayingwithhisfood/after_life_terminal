"""
Afterlife colour bot.

- Posts a panel with a button.
- On click: makes a one-time token, DMs the member a private link to the
  website (falls back to an ephemeral reply if their DMs are closed).
- Polls the shared database for colours submitted on the website and
  applies them as a role, live, with no manual step.
"""

import os
import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks

import db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("afterlife-colour-bot")

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
BASE_URL = os.environ["WEBSITE_BASE_URL"].rstrip("/")   # e.g. https://afterlife-colour.up.railway.app
LINK_TTL_SECONDS = int(os.environ.get("LINK_TTL_SECONDS", "600"))  # 10 minutes

PANEL_TEXT = (
    "click the button to get a link and a temporary password to a website "
    "to choose your unique colour, only accessible to you\n"
    "`#finderskeepersloserssweepers`"
)

BUTTON_CUSTOM_ID = "afterlife:get_colour_link"

intents = discord.Intents.default()
intents.members = True  # needed to fetch/assign roles reliably

bot = commands.Bot(command_prefix="!", intents=intents)


class ColourPanelView(discord.ui.View):
    """timeout=None + a fixed custom_id makes this survive bot restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Get my colour link",
        style=discord.ButtonStyle.danger,
        emoji="🎨",
        custom_id=BUTTON_CUSTOM_ID,
    )
    async def get_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        token = db.create_token(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            username=str(interaction.user),
            ttl_seconds=LINK_TTL_SECONDS,
        )
        link = f"{BASE_URL}/colour/{token}"
        minutes = LINK_TTL_SECONDS // 60

        dm_text = (
            f"**AFTERLIFE — private colour terminal**\n\n"
            f"Your link (treat it like a password — works once, expires in {minutes} minutes):\n"
            f"{link}"
        )

        try:
            await interaction.user.send(dm_text)
            await interaction.response.send_message(
                "Sent you a DM with your private link. 🎨", ephemeral=True
            )
        except discord.Forbidden:
            # DMs closed — fall back to an ephemeral message, still only visible to them
            await interaction.response.send_message(
                f"Your DMs are closed, so here it is privately instead "
                f"(only you can see this message):\n{link}\n\n"
                f"Expires in {minutes} minutes, works once.",
                ephemeral=True,
            )


@bot.event
async def on_ready():
    db.init_db()
    bot.add_view(ColourPanelView())  # re-register persistent view after restarts
    if not apply_pending_colours.is_running():
        apply_pending_colours.start()
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash commands", len(synced))
    except discord.HTTPException:
        log.exception("Slash command sync failed")
    log.info("Logged in as %s", bot.user)


@bot.tree.command(name="setup-colour-panel", description="Post the colour picker panel in this channel (admin only).")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_colour_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎨 AFTERLIFE — Colour Terminal",
        description=PANEL_TEXT,
        colour=discord.Colour.from_str("#B026FF"),
    )
    await interaction.channel.send(embed=embed, view=ColourPanelView())
    await interaction.response.send_message("Panel posted.", ephemeral=True)


@tasks.loop(seconds=3)
async def apply_pending_colours():
    for submission in db.get_pending_submissions():
        token = submission["token"]
        try:
            guild = bot.get_guild(submission["guild_id"])
            if guild is None:
                db.mark_failed(token)
                continue

            member = guild.get_member(submission["user_id"]) or await guild.fetch_member(submission["user_id"])
            hex_colour = submission["hex_colour"]
            colour = discord.Colour(int(hex_colour.lstrip("#"), 16))

            existing_role_id = db.get_user_role(member.id, guild.id)
            role = guild.get_role(existing_role_id) if existing_role_id else None

            if role is None:
                role = await guild.create_role(
                    name=f"⚡ {hex_colour.upper()}",
                    colour=colour,
                    reason=f"Afterlife colour pick for {member}",
                )
                db.set_user_role(member.id, guild.id, role.id)
                # try to slot it just under the bot's own top role so it actually shows
                try:
                    bot_top = guild.me.top_role
                    await role.edit(position=max(bot_top.position - 1, 1))
                except discord.HTTPException:
                    pass  # not fatal — admin can reorder manually if needed
            else:
                await role.edit(colour=colour, name=f"⚡ {hex_colour.upper()}")

            if role not in member.roles:
                await member.add_roles(role, reason="Afterlife colour pick")

            db.mark_applied(token)
            log.info("Applied %s to %s in %s", hex_colour, member, guild.name)

            try:
                await member.send(f"Your colour is live: **{hex_colour.upper()}** ⚡")
            except discord.Forbidden:
                pass

        except Exception:
            log.exception("Failed to apply submission for token %s", token)
            db.mark_failed(token)


if __name__ == "__main__":
    bot.run(TOKEN)
