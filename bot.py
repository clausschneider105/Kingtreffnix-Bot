import os
import asyncio
import aiohttp
import discord

from discord.ext import commands, tasks
from discord import app_commands

from dotenv import load_dotenv


# =========================================================
# .ENV LADEN
# =========================================================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not DISCORD_TOKEN:
    raise ValueError(
        "DISCORD_TOKEN wurde nicht gefunden. Überprüfe deine .env-Datei."
    )

if not YOUTUBE_API_KEY:
    raise ValueError(
        "YOUTUBE_API_KEY wurde nicht gefunden. "
        "Füge den API-Key in deine .env-Datei ein."
    )


# =========================================================
# EINSTELLUNGEN
# =========================================================

TICKET_CATEGORY_NAME = "HILFE"
TICKET_PANEL_CHANNEL_NAME = "├🎫tickets"

MOD_ROLE_NAME = "Mod"
ADMIN_ROLE_NAME = "Admin"

BOT_DISPLAY_NAME = "Kingtreffnix"


# =========================================================
# YOUTUBE
# =========================================================

YOUTUBE_CHANNEL_ID = "UCY5LXqf2KMjRxjfrryBSveQ"

YOUTUBE_CHANNEL_NAME = "Kingtreffnix"

YOUTUBE_DISCORD_CHANNEL_NAME = "└🔔content"

YOUTUBE_CHECK_INTERVAL = 120

# Mod-Logs
MOD_LOG_CHANNEL_NAME = "├🤓mod-log"

MOD_LOG_COLORS = {
    "channel_created": discord.Color.green(),
    "channel_deleted": discord.Color.orange(),
    "channel_renamed": discord.Color.blue(),
    "channel_permissions": discord.Color.orange(),
    "role_created": discord.Color.green(),
    "role_deleted": discord.Color.red(),
    "role_updated": discord.Color.orange(),
    "user_banned": discord.Color.red(),
    "user_unbanned": discord.Color.blue(),
    "user_kicked": discord.Color.red(),
    "timeout_given": discord.Color.orange(),
    "timeout_removed": discord.Color.blue(),
    "message_deleted": discord.Color.green(),
    "message_edited": discord.Color.green(),
    "ticket_created": discord.Color.green(),
    "ticket_claimed": discord.Color.green(),
    "ticket_closed": discord.Color.green(),
    "ticket_reopened": discord.Color.green(),
    "ticket_deleted": discord.Color.blue(),
}

# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

# Discord-Nachrichten für detaillierte Lösch-Logs kurz zwischenspeichern.
message_cache = {}
MESSAGE_CACHE_LIMIT = 5000

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# YOUTUBE STATUS
# =========================================================

last_youtube_video_id = None
last_live_video_id = None


# =========================================================
# MOD-LOG HILFSFUNKTIONEN
# =========================================================

def get_mod_log_channel(guild: discord.Guild):
    return discord.utils.get(
        guild.text_channels,
        name=MOD_LOG_CHANNEL_NAME
    )


async def send_mod_log(
    guild: discord.Guild,
    action: str,
    color: discord.Color,
    target: str,
    actor: str,
    reason: str,
    extra_fields=None
):
    channel = get_mod_log_channel(guild)

    if channel is None:
        print(
            f"Mod-Log-Kanal {MOD_LOG_CHANNEL_NAME} wurde nicht gefunden."
        )
        return

    embed = discord.Embed(
        title=f"🛡️ {action}",
        color=color,
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(name="Kanal / Ziel", value=target, inline=False)
    embed.add_field(name="Responsible Moderator", value=actor, inline=False)
    embed.add_field(
        name="Reason",
        value=reason or "Kein Grund angegeben",
        inline=False
    )

    if extra_fields:
        for field_name, field_value, inline in extra_fields:
            embed.add_field(
                name=field_name,
                value=str(field_value)[:1024] or "-",
                inline=inline
            )

    embed.set_footer(text=BOT_DISPLAY_NAME)

    try:
        await channel.send(embed=embed)
    except discord.HTTPException as error:
        print(f"Fehler beim Senden des Mod-Logs: {error}")


async def get_audit_actor(
    guild: discord.Guild,
    action,
    target_id=None,
    delay=1.0
):
    if delay:
        await asyncio.sleep(delay)

    try:
        async for entry in guild.audit_logs(limit=10, action=action):
            if target_id is not None:
                if getattr(entry.target, "id", None) != target_id:
                    continue

            if (discord.utils.utcnow() - entry.created_at).total_seconds() > 15:
                continue

            return entry.user, entry.reason

    except discord.Forbidden:
        print(f"Keine Berechtigung für Audit-Logs auf {guild.name}.")
    except discord.HTTPException as error:
        print(f"Fehler beim Lesen der Audit-Logs: {error}")

    return None, None


def format_actor(actor) -> str:
    if actor is None:
        return "Unbekannt"
    return f"{actor.mention} ({actor})"


def shorten_text(text, limit=1000):
    text = text if text is not None else "[Kein Text / nur Anhang oder Einbettung]"
    text = str(text)
    if not text:
        text = "[Kein Text / nur Anhang oder Einbettung]"
    if len(text) > limit:
        return text[:limit - 3] + "..."
    return text


def format_role_list(roles):
    if not roles:
        return "Keine"
    return ", ".join(role.mention for role in roles)


def format_permission_value(value):
    if value is None:
        return "Unverändert"
    if value is True:
        return "Erlaubt"
    if value is False:
        return "Verweigert"
    return str(value)


def describe_audit_changes(entry):
    changes = []
    for change in getattr(entry, "changes", []):
        key = getattr(change, "key", "unbekannt")
        before = getattr(change, "before", None)
        after = getattr(change, "after", None)
        changes.append(
            f"**{key}:** `{shorten_text(before, 300)}` → `{shorten_text(after, 300)}`"
        )
    return "\n".join(changes) if changes else "Keine Detailänderungen von Discord geliefert."


def describe_role_permission_changes(before: discord.Role, after: discord.Role):
    changes = []
    for permission_name in discord.Permissions.VALID_FLAGS:
        old_value = getattr(before.permissions, permission_name)
        new_value = getattr(after.permissions, permission_name)
        if old_value != new_value:
            changes.append(
                f"**{permission_name}:** "
                f"{'Erlaubt' if old_value else 'Verweigert'} → "
                f"{'Erlaubt' if new_value else 'Verweigert'}"
            )
    return "\n".join(changes) if changes else "Keine einzelnen Rollenrechte geändert."


def describe_channel_permission_changes(before, after):
    changes = []
    before_overwrites = getattr(before, "overwrites", {}) or {}
    after_overwrites = getattr(after, "overwrites", {}) or {}
    targets = set(before_overwrites.keys()) | set(after_overwrites.keys())

    for target in targets:
        old = before_overwrites.get(target)
        new = after_overwrites.get(target)
        target_name = getattr(target, "mention", None) or str(target)

        for permission_name in discord.Permissions.VALID_FLAGS:
            old_value = getattr(old, permission_name, None) if old else None
            new_value = getattr(new, permission_name, None) if new else None
            if old_value != new_value:
                def state(value):
                    if value is True:
                        return "Erlaubt"
                    if value is False:
                        return "Verweigert"
                    return "Neutral"

                changes.append(
                    f"**{target_name} – {permission_name}:** "
                    f"{state(old_value)} → {state(new_value)}"
                )

    return "\n".join(changes) if changes else "Keine einzelnen Kanalrechte erkannt."


# =========================================================
# TICKET HILFSFUNKTIONEN
# =========================================================

def can_manage_ticket(member: discord.Member) -> bool:

    if member.guild_permissions.administrator:
        return True

    return any(
        role.name in [MOD_ROLE_NAME, ADMIN_ROLE_NAME]
        for role in member.roles
    )


def get_ticket_category(guild: discord.Guild):

    return discord.utils.get(
        guild.categories,
        name=TICKET_CATEGORY_NAME
    )


def is_ticket_channel(channel) -> bool:

    category = getattr(channel, "category", None)

    return (
        category is not None
        and category.name == TICKET_CATEGORY_NAME
        and channel.name.startswith("ticket-")
    )


def get_ticket_user_id(channel):

    topic = channel.topic or ""

    if "User-ID:" not in topic:
        return None

    try:

        return int(
            topic.split("User-ID:")[1].split("|")[0].strip()
        )

    except ValueError:

        return None


# =========================================================
# TICKET KATEGORIEN
# =========================================================

TICKET_OPTIONS = [

    {
        "label": "Support",
        "description": "Du benötigst Hilfe bei einem Problem.",
        "emoji": "🛠️"
    },

    {
        "label": "User melden",
        "description": "Melde einen Nutzer wegen eines Regelverstoßes.",
        "emoji": "🚨"
    },

    {
        "label": "Bug melden",
        "description": "Melde einen Fehler auf dem Server.",
        "emoji": "🐛"
    },

    {
        "label": "Team Report",
        "description": "Melde ein Problem oder Anliegen bezüglich des Teams.",
        "emoji": "⚠️"
    },

    {
        "label": "Mod-Bewerbung",
        "description": "Bewirb dich für das Moderationsteam.",
        "emoji": "📝"
    },

    {
        "label": "Sonstige",
        "description": "Dein Anliegen passt in keine andere Kategorie.",
        "emoji": "❓"
    }
]


# =========================================================
# TICKET BUTTONS
# =========================================================

class TicketButtons(discord.ui.View):

    def __init__(self, closed=False):

        super().__init__(timeout=None)

        # -------------------------------------------------
        # CLAIM
        # -------------------------------------------------

        claim_button = discord.ui.Button(
            label="Ticket claimen",
            emoji="🙋",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_claim",
            disabled=closed
        )

        claim_button.callback = self.claim

        self.add_item(claim_button)

        # -------------------------------------------------
        # SCHLIESSEN
        # -------------------------------------------------

        close_button = discord.ui.Button(
            label="Ticket schließen",
            emoji="🔒",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_close",
            disabled=closed
        )

        close_button.callback = self.close

        self.add_item(close_button)

        # -------------------------------------------------
        # ÖFFNEN
        # -------------------------------------------------

        open_button = discord.ui.Button(
            label="Ticket öffnen",
            emoji="🔓",
            style=discord.ButtonStyle.success,
            custom_id="ticket_reopen",
            disabled=not closed
        )

        open_button.callback = self.reopen

        self.add_item(open_button)

        # -------------------------------------------------
        # LÖSCHEN
        # -------------------------------------------------

        delete_button = discord.ui.Button(
            label="Ticket löschen",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_delete"
        )

        delete_button.callback = self.delete

        self.add_item(delete_button)


    # =====================================================
    # CLAIM
    # =====================================================

    async def claim(self, interaction: discord.Interaction):

        # SOFORT bestätigen
        await interaction.response.defer()

        if not isinstance(interaction.user, discord.Member):

            await interaction.followup.send(
                "❌ Ungültiger Benutzer.",
                ephemeral=True
            )

            return

        if not can_manage_ticket(interaction.user):

            await interaction.followup.send(
                "❌ Nur Mods oder Admins können dieses Ticket claimen.",
                ephemeral=True
            )

            return

        if not is_ticket_channel(interaction.channel):

            await interaction.followup.send(
                "❌ Dieser Button kann nur in einem Ticket benutzt werden.",
                ephemeral=True
            )

            return

        # Neue View
        view = TicketButtons(
            closed=False
        )

        # Claim deaktivieren
        for item in view.children:

            if item.custom_id == "ticket_claim":

                item.disabled = True

                item.label = (
                    f"Geclaimt von "
                    f"{interaction.user.display_name}"
                )

        await interaction.message.edit(
            view=view
        )

        await send_mod_log(
            guild=interaction.guild,
            action="Ticket geclaimt",
            color=MOD_LOG_COLORS["ticket_claimed"],
            target=interaction.channel.mention,
            actor=format_actor(interaction.user),
            reason=f"Ticket geclaimt von {interaction.user}"
        )

        await interaction.followup.send(
            "🙋 Du hast das Ticket übernommen.",
            ephemeral=True
        )


    # =====================================================
    # SCHLIESSEN
    # =====================================================

    async def close(self, interaction: discord.Interaction):

        # SOFORT bestätigen
        await interaction.response.defer()

        if not isinstance(interaction.user, discord.Member):

            await interaction.followup.send(
                "❌ Ungültiger Benutzer.",
                ephemeral=True
            )

            return

        if not can_manage_ticket(interaction.user):

            await interaction.followup.send(
                "❌ Nur Mods oder Admins können Tickets schließen.",
                ephemeral=True
            )

            return

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):

            await interaction.followup.send(
                "❌ Ungültiger Kanal.",
                ephemeral=True
            )

            return

        if not is_ticket_channel(interaction.channel):

            await interaction.followup.send(
                "❌ Dieser Button kann nur in einem Ticket benutzt werden.",
                ephemeral=True
            )

            return

        channel = interaction.channel

        user_id = get_ticket_user_id(channel)

        # Ticket-Ersteller ausblenden
        if user_id:

            member = channel.guild.get_member(user_id)

            if member:

                await channel.set_permissions(
                    member,
                    view_channel=False,
                    send_messages=False
                )

        # Buttons ändern
        view = TicketButtons(
            closed=True
        )

        await interaction.message.edit(
            view=view
        )

        await send_mod_log(
            guild=interaction.guild,
            action="Ticket geschlossen",
            color=MOD_LOG_COLORS["ticket_closed"],
            target=channel.mention,
            actor=format_actor(interaction.user),
            reason=f"Ticket geschlossen von {interaction.user}"
        )

        # NUR der klickende Mod/Admin sieht diese Nachricht
        await interaction.followup.send(
            "🔒 Das Ticket wurde geschlossen.",
            ephemeral=True
        )


    # =====================================================
    # ÖFFNEN
    # =====================================================

    async def reopen(self, interaction: discord.Interaction):

        # SOFORT bestätigen
        await interaction.response.defer()

        if not isinstance(interaction.user, discord.Member):

            await interaction.followup.send(
                "❌ Ungültiger Benutzer.",
                ephemeral=True
            )

            return

        if not can_manage_ticket(interaction.user):

            await interaction.followup.send(
                "❌ Nur Mods oder Admins können Tickets öffnen.",
                ephemeral=True
            )

            return

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):

            await interaction.followup.send(
                "❌ Ungültiger Kanal.",
                ephemeral=True
            )

            return

        if not is_ticket_channel(interaction.channel):

            await interaction.followup.send(
                "❌ Dieser Button kann nur in einem Ticket benutzt werden.",
                ephemeral=True
            )

            return

        channel = interaction.channel

        user_id = get_ticket_user_id(channel)

        # Ticket-Ersteller wieder freischalten
        if user_id:

            member = channel.guild.get_member(user_id)

            if member:

                await channel.set_permissions(
                    member,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )

        # Buttons wieder öffnen
        view = TicketButtons(
            closed=False
        )

        await interaction.message.edit(
            view=view
        )

        await send_mod_log(
            guild=interaction.guild,
            action="Ticket wieder geöffnet",
            color=MOD_LOG_COLORS["ticket_reopened"],
            target=channel.mention,
            actor=format_actor(interaction.user),
            reason=f"Ticket wieder geöffnet von {interaction.user}"
        )

        # NUR der klickende Mod/Admin sieht diese Nachricht
        await interaction.followup.send(
            "🔓 Das Ticket wurde wieder geöffnet.",
            ephemeral=True
        )


    # =====================================================
    # LÖSCHEN
    # =====================================================

    async def delete(self, interaction: discord.Interaction):

        # SOFORT bestätigen
        await interaction.response.defer(
            ephemeral=True
        )

        if not isinstance(interaction.user, discord.Member):

            await interaction.followup.send(
                "❌ Ungültiger Benutzer.",
                ephemeral=True
            )

            return

        if not can_manage_ticket(interaction.user):

            await interaction.followup.send(
                "❌ Nur Mods oder Admins können Tickets löschen.",
                ephemeral=True
            )

            return

        if not isinstance(
            interaction.channel,
            discord.TextChannel
        ):

            await interaction.followup.send(
                "❌ Ungültiger Kanal.",
                ephemeral=True
            )

            return

        if not is_ticket_channel(interaction.channel):

            await interaction.followup.send(
                "❌ Dieser Button kann nur in einem Ticket benutzt werden.",
                ephemeral=True
            )

            return

        await interaction.followup.send(
            "🗑️ Ticket wird gelöscht...",
            ephemeral=True
        )

        channel = interaction.channel

        await send_mod_log(
            guild=channel.guild,
            action="Ticket gelöscht",
            color=MOD_LOG_COLORS["ticket_deleted"],
            target=f"#{channel.name}",
            actor=format_actor(interaction.user),
            reason=f"Ticket gelöscht von {interaction.user}"
        )

        await channel.delete(
            reason=f"Ticket gelöscht von {interaction.user}"
        )


# =========================================================
# TICKET DROPDOWN
# =========================================================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = []

        for ticket in TICKET_OPTIONS:

            options.append(
                discord.SelectOption(
                    label=ticket["label"],
                    description=ticket["description"],
                    emoji=ticket["emoji"]
                )
            )

        super().__init__(
            placeholder="Select a category",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )


    async def callback(
        self,
        interaction: discord.Interaction
    ):

        # WICHTIG:
        # Sofort bestätigen, damit Discord nicht
        # "Bot hat nicht rechtzeitig reagiert" anzeigt.
        await interaction.response.defer(
            ephemeral=True
        )

        selected_category = self.values[0]

        guild = interaction.guild

        if guild is None:

            await interaction.followup.send(
                "❌ Dieser Vorgang funktioniert nur auf einem Server.",
                ephemeral=True
            )

            return

        ticket_category = get_ticket_category(guild)

        if ticket_category is None:

            await interaction.followup.send(
                f"❌ Die Kategorie **{TICKET_CATEGORY_NAME}** wurde nicht gefunden.",
                ephemeral=True
            )

            return


        # -------------------------------------------------
        # Prüfen, ob bereits ein Ticket existiert
        # -------------------------------------------------

        existing_ticket = None

        username = interaction.user.name.lower()

        for channel in ticket_category.channels:

            if channel.name.startswith(
                f"ticket-{username}"
            ):

                existing_ticket = channel
                break


        if existing_ticket:

            await interaction.followup.send(
                f"❌ Du hast bereits ein Ticket: "
                f"{existing_ticket.mention}",
                ephemeral=True
            )

            return


        # -------------------------------------------------
        # Rollen
        # -------------------------------------------------

        mod_role = discord.utils.get(
            guild.roles,
            name=MOD_ROLE_NAME
        )

        admin_role = discord.utils.get(
            guild.roles,
            name=ADMIN_ROLE_NAME
        )


        # -------------------------------------------------
        # Berechtigungen
        # -------------------------------------------------

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
        }


        # Mod
        if mod_role:

            overwrites[mod_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )


        # Admin
        if admin_role:

            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )


        # -------------------------------------------------
        # Ticket erstellen
        # -------------------------------------------------

        ticket_channel = await guild.create_text_channel(

            name=f"ticket-{username}",

            category=ticket_category,

            overwrites=overwrites,

            topic=(
                f"User-ID: {interaction.user.id} | "
                f"Kategorie: {selected_category}"
            )
        )


        # -------------------------------------------------
        # Ticket-Embed
        # -------------------------------------------------

        embed = discord.Embed(

            title="🎫 Ticket erstellt",

            description=(
                f"Hallo {interaction.user.mention}!\n\n"
                f"**Kategorie:** {selected_category}\n\n"
                "Beschreibe hier bitte dein Anliegen "
                "möglichst genau."
            )
        )

        embed.set_footer(
            text=f"{BOT_DISPLAY_NAME} • Ticket-System"
        )


        # -------------------------------------------------
        # Ticket-Nachricht
        # -------------------------------------------------

        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=TicketButtons()
        )

        await send_mod_log(
            guild=guild,
            action="Ticket erstellt",
            color=MOD_LOG_COLORS["ticket_created"],
            target=ticket_channel.mention,
            actor=format_actor(interaction.user),
            reason=(
                f"{selected_category}-Ticket erstellt von "
                f"{interaction.user}"
            )
        )

        # -------------------------------------------------
        # Erfolgreiche Antwort
        # -------------------------------------------------

        await interaction.followup.send(
            f"✅ Dein Ticket wurde erstellt: "
            f"{ticket_channel.mention}",
            ephemeral=True
        )


        # -------------------------------------------------
        # Dropdown zurücksetzen
        # -------------------------------------------------

        try:

            await interaction.message.edit(
                view=TicketView()
            )

        except discord.HTTPException:

            pass


# =========================================================
# TICKET VIEW
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            TicketSelect()
        )


# =========================================================
# /ticket
# =========================================================

@bot.tree.command(
    name="ticket",
    description="Erstellt das Ticket-System."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def ticket(
    interaction: discord.Interaction
):

    # Sofort bestätigen
    await interaction.response.defer(
        ephemeral=True
    )

    guild = interaction.guild

    if guild is None:

        await interaction.followup.send(
            "❌ Dieser Befehl kann nur auf einem Server verwendet werden.",
            ephemeral=True
        )

        return


    ticket_panel_channel = discord.utils.get(
        guild.text_channels,
        name=TICKET_PANEL_CHANNEL_NAME
    )


    if ticket_panel_channel is None:

        await interaction.followup.send(
            f"❌ Der Kanal "
            f"**{TICKET_PANEL_CHANNEL_NAME}** wurde nicht gefunden.",
            ephemeral=True
        )

        return


    # -------------------------------------------------
    # Ticket-Panel
    # -------------------------------------------------

    embed = discord.Embed(

        title="🎫 Ticket-System",

        description=(
            "Benötigst du Hilfe oder möchtest du etwas melden?\n\n"
            "Wähle unten die passende Kategorie aus, "
            "um ein Ticket zu erstellen."
        )
    )

    embed.set_footer(
        text=f"{BOT_DISPLAY_NAME} • Ticket-System"
    )


    await ticket_panel_channel.send(
        embed=embed,
        view=TicketView()
    )


    await interaction.followup.send(
        f"✅ Das Ticket-System wurde in "
        f"{ticket_panel_channel.mention} erstellt.",
        ephemeral=True
    )


# =========================================================
# YOUTUBE: DISCORD-KANAL SUCHEN
# =========================================================

def get_youtube_discord_channel():

    for guild in bot.guilds:

        channel = discord.utils.get(
            guild.text_channels,
            name=YOUTUBE_DISCORD_CHANNEL_NAME
        )

        if channel:
            return channel

    return None


# =========================================================
# YOUTUBE API
# =========================================================

async def youtube_api_request(
    session,
    endpoint,
    params
):

    url = (
        "https://www.googleapis.com/youtube/v3/"
        + endpoint
    )

    params["key"] = YOUTUBE_API_KEY

    async with session.get(
        url,
        params=params,
        timeout=20
    ) as response:

        if response.status != 200:

            text = await response.text()

            print(
                f"YouTube API Fehler {response.status}: "
                f"{text}"
            )

            return None

        return await response.json()


# =========================================================
# YOUTUBE: NEUE VIDEOS
# =========================================================

async def get_latest_youtube_videos(session):

    # Upload-Playlist des Kanals holen
    channel_data = await youtube_api_request(
        session,
        "channels",
        {
            "part": "contentDetails",
            "id": YOUTUBE_CHANNEL_ID
        }
    )

    if not channel_data:
        return []

    items = channel_data.get(
        "items",
        []
    )

    if not items:
        return []

    uploads_playlist_id = (
        items[0]
        ["contentDetails"]
        ["relatedPlaylists"]
        ["uploads"]
    )


    # Neueste Uploads holen
    playlist_data = await youtube_api_request(
        session,
        "playlistItems",
        {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": 10
        }
    )

    if not playlist_data:
        return []

    videos = []

    for item in playlist_data.get(
        "items",
        []
    ):

        video_id = item["contentDetails"]["videoId"]

        snippet = item["snippet"]

        videos.append({
            "id": video_id,
            "title": snippet.get(
                "title",
                "Neues Video"
            ),
            "published_at": snippet.get(
                "publishedAt"
            ),
            "thumbnail": (
                snippet
                .get("thumbnails", {})
                .get("maxres", {})
                .get("url")
            ) or (
                snippet
                .get("thumbnails", {})
                .get("high", {})
                .get("url")
            ) or (
                snippet
                .get("thumbnails", {})
                .get("default", {})
                .get("url")
            )
        })

    return videos


# =========================================================
# YOUTUBE: VIDEO-INFOS
# =========================================================

async def get_video_details(
    session,
    video_ids
):

    if not video_ids:
        return []

    data = await youtube_api_request(
        session,
        "videos",
        {
            "part": "snippet,liveStreamingDetails,status",
            "id": ",".join(video_ids)
        }
    )

    if not data:
        return []

    return data.get(
        "items",
        []
    )


# =========================================================
# YOUTUBE EMBED
# =========================================================

def create_youtube_embed(
    title,
    video_id,
    thumbnail,
    is_live=False
):

    if is_live:

        embed = discord.Embed(
            title=title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            description="🔴 **LIVE auf YouTube**"
        )

    else:

        embed = discord.Embed(
            title=title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            description="🎬 Neues Video auf YouTube"
        )

    if thumbnail:

        embed.set_image(
            url=thumbnail
        )

    embed.set_footer(
        text="Kingtreffnix • YouTube"
    )

    return embed


# =========================================================
# YOUTUBE-CHECKER
# =========================================================

@tasks.loop(seconds=YOUTUBE_CHECK_INTERVAL)
async def youtube_checker():

    global last_youtube_video_id
    global last_live_video_id

    try:

        discord_channel = get_youtube_discord_channel()

        if discord_channel is None:

            print(
                f"YouTube-Kanal "
                f"{YOUTUBE_DISCORD_CHANNEL_NAME} "
                f"wurde nicht gefunden."
            )

            return


        async with aiohttp.ClientSession() as session:

            videos = await get_latest_youtube_videos(
                session
            )

            if not videos:
                return


            # -------------------------------------------------
            # ERSTER START
            # -------------------------------------------------
            #
            # Beim ersten Check werden bereits vorhandene
            # Videos NICHT nachträglich gespammt.
            #

            if last_youtube_video_id is None:

                last_youtube_video_id = videos[0]["id"]

                video_details = await get_video_details(
                    session,
                    [video["id"] for video in videos]
                )

                # Bereits laufenden Stream beim Start
                # ebenfalls merken, damit er nicht mehrfach
                # gepostet wird.

                for video in video_details:

                    live_details = video.get(
                        "liveStreamingDetails"
                    )

                    if not live_details:
                        continue

                    actual_start = live_details.get(
                        "actualStartTime"
                    )

                    actual_end = live_details.get(
                        "actualEndTime"
                    )

                    if actual_start and not actual_end:

                        last_live_video_id = video["id"]

                print(
                    "YouTube-Checker gestartet."
                )

                return


            # -------------------------------------------------
            # NEUE VIDEOS
            # -------------------------------------------------

            newest_video = videos[0]

            if newest_video["id"] != last_youtube_video_id:

                # Neue Videos seit dem letzten Check
                new_videos = []

                for video in videos:

                    if video["id"] == last_youtube_video_id:
                        break

                    new_videos.append(video)


                # Älteste zuerst
                new_videos.reverse()


                video_details = await get_video_details(
                    session,
                    [video["id"] for video in new_videos]
                )


                details_by_id = {
                    video["id"]: video
                    for video in video_details
                }


                for video in new_videos:

                    details = details_by_id.get(
                        video["id"]
                    )

                    if not details:
                        continue


                    live_details = details.get(
                        "liveStreamingDetails"
                    )


                    # -------------------------------------------------
                    # LIVE-STREAM
                    # -------------------------------------------------

                    if live_details:

                        actual_start = live_details.get(
                            "actualStartTime"
                        )

                        actual_end = live_details.get(
                            "actualEndTime"
                        )

                        # Nur wenn tatsächlich LIVE
                        if actual_start and not actual_end:

                            if video["id"] != last_live_video_id:

                                embed = create_youtube_embed(
                                    title=video["title"],
                                    video_id=video["id"],
                                    thumbnail=video["thumbnail"],
                                    is_live=True
                                )

                                await discord_channel.send(

                                    content=(
                                        f"@everyone "
                                        f"{YOUTUBE_CHANNEL_NAME} "
                                        f"ist gerade **LIVE**! 🔴"
                                    ),

                                    embed=embed
                                )

                                last_live_video_id = video["id"]

                            continue


                    # -------------------------------------------------
                    # NORMALER UPLOAD
                    # -------------------------------------------------

                    # Auch Shorts landen hier als normaler Upload.
                    embed = create_youtube_embed(
                        title=video["title"],
                        video_id=video["id"],
                        thumbnail=video["thumbnail"],
                        is_live=False
                    )

                    await discord_channel.send(

                        content=(
                            f"@everyone "
                            f"{YOUTUBE_CHANNEL_NAME} "
                            f"hat ein neues Video hochgeladen!"
                        ),

                        embed=embed
                    )


                last_youtube_video_id = newest_video["id"]


            # -------------------------------------------------
            # LIVESTREAM STARTEN, DER SCHON VORHER ANGELEGT WAR
            # -------------------------------------------------
            #
            # Ein Stream kann bereits als Video existieren,
            # ohne dass er schon LIVE ist.
            # Deshalb prüfen wir zusätzlich die neuesten
            # Videos auf einen neu gestarteten Stream.
            #

            video_details = await get_video_details(
                session,
                [video["id"] for video in videos]
            )


            for details in video_details:

                video_id = details["id"]

                live_details = details.get(
                    "liveStreamingDetails"
                )

                if not live_details:
                    continue

                actual_start = live_details.get(
                    "actualStartTime"
                )

                actual_end = live_details.get(
                    "actualEndTime"
                )

                # Jetzt tatsächlich LIVE
                if actual_start and not actual_end:

                    if video_id == last_live_video_id:
                        continue


                    matching_video = next(
                        (
                            video
                            for video in videos
                            if video["id"] == video_id
                        ),
                        None
                    )

                    if not matching_video:
                        continue


                    embed = create_youtube_embed(
                        title=matching_video["title"],
                        video_id=video_id,
                        thumbnail=matching_video["thumbnail"],
                        is_live=True
                    )


                    await discord_channel.send(

                        content=(
                            f"@everyone "
                            f"{YOUTUBE_CHANNEL_NAME} "
                            f"ist gerade **LIVE**! 🔴"
                        ),

                        embed=embed
                    )


                    last_live_video_id = video_id


    except asyncio.CancelledError:

        raise

    except Exception as error:

        print(
            f"Fehler im YouTube-Checker: {error}"
        )


# =========================================================
# YOUTUBE CHECKER START
# =========================================================

@youtube_checker.before_loop
async def before_youtube_checker():

    await bot.wait_until_ready()


# =========================================================
# MOD-LOG EVENTS
# =========================================================

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    # Ticket-Kanäle werden separat als "Ticket erstellt" geloggt.
    if is_ticket_channel(channel):
        return

    actor, audit_reason = await get_audit_actor(
        channel.guild,
        discord.AuditLogAction.channel_create,
        channel.id
    )

    await send_mod_log(
        guild=channel.guild,
        action="Channel erstellt",
        color=MOD_LOG_COLORS["channel_created"],
        target=f"#{channel.name}",
        actor=format_actor(actor),
        reason=audit_reason or f"Channel erstellt von {actor or 'Unbekannt'}"
    )


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    # Ticket-Kanäle werden separat als "Ticket gelöscht" geloggt.
    if is_ticket_channel(channel):
        return

    actor, audit_reason = await get_audit_actor(
        channel.guild,
        discord.AuditLogAction.channel_delete,
        channel.id
    )

    await send_mod_log(
        guild=channel.guild,
        action="Channel gelöscht",
        color=MOD_LOG_COLORS["channel_deleted"],
        target=f"#{channel.name}",
        actor=format_actor(actor),
        reason=audit_reason or f"Channel gelöscht von {actor or 'Unbekannt'}"
    )


@bot.event
async def on_guild_channel_update(
    before: discord.abc.GuildChannel,
    after: discord.abc.GuildChannel
):
    if is_ticket_channel(before) or is_ticket_channel(after):
        return

    if before.name != after.name:
        actor, audit_reason = await get_audit_actor(
            after.guild,
            discord.AuditLogAction.channel_update,
            after.id
        )

        await send_mod_log(
            guild=after.guild,
            action="Channel umbenannt",
            color=MOD_LOG_COLORS["channel_renamed"],
            target=f"#{after.name}",
            actor=format_actor(actor),
            reason=audit_reason or f"Name geändert: {before.name} → {after.name}",
            extra_fields=[("Vorheriger Name", f"#{before.name}", False), ("Neuer Name", f"#{after.name}", False)]
        )

    if getattr(before, "overwrites", None) != getattr(after, "overwrites", None):
        actor, audit_reason = await get_audit_actor(
            after.guild,
            discord.AuditLogAction.channel_update,
            after.id
        )

        detail = describe_channel_permission_changes(before, after)

        await send_mod_log(
            guild=after.guild,
            action="Channel-Berechtigung geändert",
            color=MOD_LOG_COLORS["channel_permissions"],
            target=f"#{after.name}",
            actor=format_actor(actor),
            reason=audit_reason or "Berechtigungen des Channels geändert",
            extra_fields=[("Berechtigungsänderungen", detail, False)]
        )

@bot.event
async def on_guild_role_create(role: discord.Role):
    actor, audit_reason = await get_audit_actor(
        role.guild,
        discord.AuditLogAction.role_create,
        role.id
    )

    await send_mod_log(
        guild=role.guild,
        action="Rolle erstellt",
        color=MOD_LOG_COLORS["role_created"],
        target=f"@{role.name}",
        actor=format_actor(actor),
        reason=audit_reason or f"Rolle erstellt von {actor or 'Unbekannt'}"
    )


@bot.event
async def on_guild_role_delete(role: discord.Role):
    actor, audit_reason = await get_audit_actor(
        role.guild,
        discord.AuditLogAction.role_delete,
        role.id
    )

    await send_mod_log(
        guild=role.guild,
        action="Rolle gelöscht",
        color=MOD_LOG_COLORS["role_deleted"],
        target=f"@{role.name}",
        actor=format_actor(actor),
        reason=audit_reason or f"Rolle gelöscht von {actor or 'Unbekannt'}"
    )


@bot.event
async def on_guild_role_update(
    before: discord.Role,
    after: discord.Role
):
    if before == after:
        return

    actor, audit_reason = await get_audit_actor(
        after.guild,
        discord.AuditLogAction.role_update,
        after.id
    )

    detail = describe_role_permission_changes(before, after)
    audit_detail = "Keine zusätzlichen Audit-Log-Details."
    try:
        async for entry in after.guild.audit_logs(limit=10, action=discord.AuditLogAction.role_update):
            if getattr(entry.target, "id", None) == after.id and (discord.utils.utcnow() - entry.created_at).total_seconds() <= 15:
                audit_detail = describe_audit_changes(entry)
                break
    except (discord.Forbidden, discord.HTTPException):
        pass

    await send_mod_log(
        guild=after.guild,
        action="Rolle geändert",
        color=MOD_LOG_COLORS["role_updated"],
        target=f"@{after.name}",
        actor=format_actor(actor),
        reason=audit_reason or "Einstellungen der Rolle geändert",
        extra_fields=[
            ("Rollenname vorher", before.name, True),
            ("Rollenname nachher", after.name, True),
            ("Rechte der Rolle", detail, False),
            ("Weitere Änderungen", audit_detail, False),
        ]
    )


@bot.event
async def on_member_update(
    before: discord.Member,
    after: discord.Member
):
    # Rollen hinzugefügt / entfernt
    before_roles = {role.id: role for role in before.roles if role.is_default() is False}
    after_roles = {role.id: role for role in after.roles if role.is_default() is False}

    added_roles = [after_roles[rid] for rid in after_roles.keys() - before_roles.keys()]
    removed_roles = [before_roles[rid] for rid in before_roles.keys() - after_roles.keys()]

    if added_roles or removed_roles:
        actor, audit_reason = await get_audit_actor(
            after.guild,
            discord.AuditLogAction.member_role_update,
            after.id
        )

        await send_mod_log(
            guild=after.guild,
            action="Rollen vergeben / entfernt",
            color=MOD_LOG_COLORS["role_updated"],
            target=f"{after.mention} ({after})",
            actor=format_actor(actor),
            reason=audit_reason or "Rollen eines Users geändert",
            extra_fields=[
                ("Rollen vergeben", format_role_list(added_roles), False),
                ("Rollen entfernt", format_role_list(removed_roles), False),
            ]
        )

    # Timeout
    before_timeout = before.communication_disabled_until
    after_timeout = after.communication_disabled_until

    if before_timeout == after_timeout:
        return

    actor, audit_reason = await get_audit_actor(
        after.guild,
        discord.AuditLogAction.member_update,
        after.id
    )

    if after_timeout is not None:
        await send_mod_log(
            guild=after.guild,
            action="Timeout vergeben",
            color=MOD_LOG_COLORS["timeout_given"],
            target=f"{after.mention} ({after})",
            actor=format_actor(actor),
            reason=audit_reason or "Timeout vergeben",
            extra_fields=[("Timeout bis", f"{after_timeout:%d.%m.%Y %H:%M:%S UTC}", False)]
        )
    else:
        await send_mod_log(
            guild=after.guild,
            action="Timeout entfernt",
            color=MOD_LOG_COLORS["timeout_removed"],
            target=f"{after.mention} ({after})",
            actor=format_actor(actor),
            reason=audit_reason or "Timeout entfernt"
        )

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    actor, audit_reason = await get_audit_actor(
        guild,
        discord.AuditLogAction.member_ban_add,
        user.id
    )

    await send_mod_log(
        guild=guild,
        action="User gebannt",
        color=MOD_LOG_COLORS["user_banned"],
        target=f"{user.mention} ({user})",
        actor=format_actor(actor),
        reason=audit_reason or "Kein Ban-Grund angegeben",
        extra_fields=[("Gebannt wurde", f"{user.mention} ({user})", False)]
    )


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    actor, audit_reason = await get_audit_actor(
        guild,
        discord.AuditLogAction.member_ban_remove,
        user.id
    )

    await send_mod_log(
        guild=guild,
        action="User entbannt",
        color=MOD_LOG_COLORS["user_unbanned"],
        target=f"{user.mention} ({user})",
        actor=format_actor(actor),
        reason=audit_reason or "Kein Entbannungs-Grund angegeben",
        extra_fields=[("Entbannt wurde", f"{user.mention} ({user})", False)]
    )


@bot.event
async def on_member_remove(member: discord.Member):
    actor, audit_reason = await get_audit_actor(
        member.guild,
        discord.AuditLogAction.member_kick,
        member.id
    )

    if actor is None:
        return

    await send_mod_log(
        guild=member.guild,
        action="User gekickt",
        color=MOD_LOG_COLORS["user_kicked"],
        target=f"{member.mention} ({member})",
        actor=format_actor(actor),
        reason=audit_reason or "Kein Kick-Grund angegeben",
        extra_fields=[("Gekickt wurde", f"{member.mention} ({member})", False)]
    )


@bot.event
async def on_member_update(
    before: discord.Member,
    after: discord.Member
):
    before_timeout = before.communication_disabled_until
    after_timeout = after.communication_disabled_until

    if before_timeout == after_timeout:
        return

    actor, audit_reason = await get_audit_actor(
        after.guild,
        discord.AuditLogAction.member_update,
        after.id
    )

    if after_timeout is not None:
        await send_mod_log(
            guild=after.guild,
            action="Timeout vergeben",
            color=MOD_LOG_COLORS["timeout_given"],
            target=f"{after.mention} ({after})",
            actor=format_actor(actor),
            reason=(
                audit_reason
                or f"Timeout vergeben bis {after_timeout:%d.%m.%Y %H:%M} UTC"
            )
        )
    else:
        await send_mod_log(
            guild=after.guild,
            action="Timeout entfernt",
            color=MOD_LOG_COLORS["timeout_removed"],
            target=f"{after.mention} ({after})",
            actor=format_actor(actor),
            reason=audit_reason or f"Timeout entfernt von {actor or 'Unbekannt'}"
        )


@bot.event
async def on_message(message: discord.Message):
    # Message Content Intent ist erforderlich, damit Inhalte gespeichert
    # und !-Commands verarbeitet werden können.
    if message.guild is not None and not message.author.bot:
        message_cache[message.id] = {
            "guild_id": message.guild.id,
            "channel_id": message.channel.id,
            "author": message.author,
            "content": message.content,
        }

        if len(message_cache) > MESSAGE_CACHE_LIMIT:
            oldest_ids = list(message_cache.keys())[:500]
            for message_id in oldest_ids:
                message_cache.pop(message_id, None)

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message: discord.Message):
    if message.guild is None:
        return

    if message.author and message.author.bot:
        message_cache.pop(message.id, None)
        return

    cached = message_cache.pop(message.id, {})
    author = cached.get("author") or message.author
    content = cached.get("content", message.content)

    actor, audit_reason = await get_audit_actor(
        message.guild,
        discord.AuditLogAction.message_delete,
        getattr(message.channel, "id", None)
    )

    # Falls Discord den Kanal nicht als Target liefert, noch einmal ohne Target suchen.
    if actor is None:
        actor, audit_reason = await get_audit_actor(
            message.guild,
            discord.AuditLogAction.message_delete,
            delay=0
        )

    await send_mod_log(
        guild=message.guild,
        action="Nachricht gelöscht",
        color=MOD_LOG_COLORS["message_deleted"],
        target=(
            f"{message.channel.mention}\n"
            f"Nachricht-ID: `{message.id}`"
        ),
        actor=format_actor(actor),
        reason=audit_reason or "Nachricht wurde gelöscht",
        extra_fields=[
            ("Nachrichten-Autor", format_actor(author), False),
            ("Gelöscht von", format_actor(actor), False),
            ("Nachricht", f"```\n{shorten_text(content)}\n```", False),
        ]
    )


@bot.event
async def on_message_edit(
    before: discord.Message,
    after: discord.Message
):
    if before.guild is None:
        return

    if before.author and before.author.bot:
        return

    if before.content == after.content:
        return

    await send_mod_log(
        guild=before.guild,
        action="Nachricht bearbeitet",
        color=MOD_LOG_COLORS["message_edited"],
        target=(
            f"{before.channel.mention}\n"
            f"Nachricht-ID: `{before.id}`"
        ),
        actor=format_actor(before.author),
        reason="Nachricht wurde bearbeitet",
        extra_fields=[
            ("Autor", format_actor(before.author), False),
            ("Vorher", f"```\n{shorten_text(before.content)}\n```", False),
            ("Nachher", f"```\n{shorten_text(after.content)}\n```", False),
        ]
    )

# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"Bot ist online als {bot.user}"
    )

    # Persistent Views nur einmal registrieren
    if not getattr(
        bot,
        "_views_registered",
        False
    ):

        bot.add_view(
            TicketView()
        )

        bot.add_view(
            TicketButtons()
        )

        bot._views_registered = True


    # YouTube-Checker starten
    if not youtube_checker.is_running():

        youtube_checker.start()


# =========================================================
# BOT STARTEN
# =========================================================

bot.run(DISCORD_TOKEN)
