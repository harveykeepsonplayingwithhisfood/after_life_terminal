"""
Afterlife colour and path bot.

One button, one link, one password. The website walks the member through
colour first, then path, on the same page. The background loop watches
the shared database for completed submissions (both parts filled in) and
applies both roles.
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
BASE_URL = os.environ["WEBSITE_BASE_URL"].rstrip("/")
LINK_TTL_SECONDS = int(os.environ.get("LINK_TTL_SECONDS", "600"))  # 10 minutes

if not BASE_URL.startswith(("http://", "https://")):
    raise RuntimeError(
        f"WEBSITE_BASE_URL must start with http:// or https:// (got: {BASE_URL!r}). "
        f"Without a scheme, Discord will not turn the link into a clickable URL."
    )

PANEL_TEXT = (
    "click the button to get a private link and a temporary password to a website "
    "to choose your unique colour and your path, only accessible to you\n"
    "`#finderskeepersloserssweepers`"
)

BUTTON_CUSTOM_ID = "afterlife:get_link"
PATH_ROLE_NAMES = {"nomad": "Nomad", "streetkid": "Streetkid", "corpo": "Corpo"}
PATH_ROLE_COLOUR = discord.Colour(0xFFFFFF)

intents = discord.Intents.default()
intents.members = True  # needed to fetch/assign roles reliably

bot = commands.Bot(command_prefix="!", intents=intents)


class LinkPanelView(discord.ui.View):
    """timeout=None + a fixed custom_id makes this survive bot restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Get my link",
        style=discord.ButtonStyle.danger,
        custom_id=BUTTON_CUSTOM_ID,
    )
    async def get_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        if db.has_completed(interaction.user.id, interaction.guild_id):
            await interaction.response.send_message(
                "You already used this. Your colour and your path are already set.",
                ephemeral=True,
            )
            return

        token, password = db.create_token(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            username=str(interaction.user),
            ttl_seconds=LINK_TTL_SECONDS,
        )
        link = f"{BASE_URL}/select/{token}"
        minutes = LINK_TTL_SECONDS // 60

        dm_text = (
            f"AFTERLIFE PRIVATE ACCESS\n\n"
            f"Link: {link}\n"
            f"Password: {password}\n\n"
            f"This walks you through your colour and then your path on the same page. "
            f"It works once, expires in {minutes} minutes, and you only get one shot "
            f"at each part so pick carefully."
        )

        try:
            await interaction.user.send(dm_text)
            await interaction.response.send_message(
                "Sent you a DM with your private link and password.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"Your DMs are closed so here it is instead. Only you can see this message.\n\n{dm_text}",
                ephemeral=True,
            )


@bot.event
async def on_ready():
    db.init_db()
    bot.add_view(LinkPanelView())  # re-register persistent view after restarts
    if not apply_pending_submissions.is_running():
        apply_pending_submissions.start()
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash commands", len(synced))
    except discord.HTTPException:
        log.exception("Slash command sync failed")
    log.info("Logged in as %s", bot.user)


@bot.tree.command(name="setup-panel", description="Post the colour and path panel in this channel (admin only).")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="AFTERLIFE TERMINAL ACCESS",
        description=PANEL_TEXT,
        colour=discord.Colour.from_str("#B026FF"),
    )
    await interaction.channel.send(embed=embed, view=LinkPanelView())
    await interaction.response.send_message("Panel posted.", ephemeral=True)


async def _apply_colour(guild: discord.Guild, member: discord.Member, hex_colour: str):
    colour = discord.Colour(int(hex_colour.lstrip("#"), 16))
    existing_role_id = db.get_user_role(member.id, guild.id, "colour")
    role = guild.get_role(existing_role_id) if existing_role_id else None

    if role is None:
        role = await guild.create_role(
            name=hex_colour.upper(), colour=colour, reason=f"Afterlife colour pick for {member}",
        )
        db.set_user_role(member.id, guild.id, "colour", role.id)
        try:
            bot_top = guild.me.top_role
            await role.edit(position=max(bot_top.position - 1, 1))
        except discord.HTTPException:
            pass
    else:
        await role.edit(colour=colour, name=hex_colour.upper())

    if role not in member.roles:
        await member.add_roles(role, reason="Afterlife colour pick")


async def _apply_path(guild: discord.Guild, member: discord.Member, path_choice: str):
    role_name = PATH_ROLE_NAMES[path_choice]
    existing_role_id = db.get_user_role(member.id, guild.id, "path")
    role = guild.get_role(existing_role_id) if existing_role_id else None

    if role is None:
        # reuse a shared role per path if one already exists in the server, instead of
        # making a new one per member
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            role = await guild.create_role(
                name=role_name, colour=PATH_ROLE_COLOUR, reason="Afterlife path role",
            )
            try:
                bot_top = guild.me.top_role
                await role.edit(position=max(bot_top.position - 1, 1))
            except discord.HTTPException:
                pass
        db.set_user_role(member.id, guild.id, "path", role.id)

    if role not in member.roles:
        await member.add_roles(role, reason="Afterlife path pick")


@tasks.loop(seconds=3)
async def apply_pending_submissions():
    for submission in db.get_pending_submissions():
        token = submission["token"]
        try:
            guild = bot.get_guild(submission["guild_id"])
            if guild is None:
                db.mark_failed(token)
                continue

            member = guild.get_member(submission["user_id"]) or await guild.fetch_member(submission["user_id"])

            await _apply_colour(guild, member, submission["colour_payload"])
            await _apply_path(guild, member, submission["path_payload"])

            db.mark_applied(token)
            log.info(
                "Applied colour %s and path %s to %s in %s",
                submission["colour_payload"], submission["path_payload"], member, guild.name,
            )

            try:
                await member.send(
                    f"Complete. Your colour {submission['colour_payload'].upper()} and your path "
                    f"{PATH_ROLE_NAMES[submission['path_payload']]} are now live in Afterlife."
                )
            except discord.Forbidden:
                pass

        except Exception:
            log.exception("Failed to apply submission for token %s", token)
            db.mark_failed(token)


if __name__ == "__main__":
    bot.run(TOKEN)
