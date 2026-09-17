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

# Social-Media / Twitch (optional – YouTube bleibt unverändert)
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_CHANNEL_NAME = os.getenv("TWITCH_CHANNEL_NAME", "kingtreffnix20")

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


# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# YOUTUBE STATUS
# =========================================================

last_youtube_video_id = None
last_live_video_id = None

# Twitch status
twitch_user_id = None
twitch_access_token = None
twitch_was_live = None


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

        await interaction.channel.delete(
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
            "description": snippet.get(
                "description",
                ""
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
    description_text="",
    is_live=False,
    is_scheduled=False
):
    # ---------------------------------------------------------
    # Beschreibung: Nur der erste Absatz wird angezeigt.
    # Sobald eine freie Zeile kommt, wird der Rest abgeschnitten.
    # ---------------------------------------------------------
    short_description = (description_text or "").strip()

    if "\n\n" in short_description:
        short_description = short_description.split("\n\n", 1)[0].strip()

    if len(short_description) > 1000:
        short_description = short_description[:1000].rstrip() + "..."

    if is_scheduled:
        status_text = "📅 **Stream geplant**"
    elif is_live:
        status_text = "🔴 **LIVE auf YouTube**"
    else:
        status_text = "🎬 **Neues Video auf YouTube**"

    if short_description:
        embed_description = f"{status_text}\n\n{short_description}"
    else:
        embed_description = status_text

    embed = discord.Embed(
        title=title,
        url=f"https://www.youtube.com/watch?v={video_id}",
        description=embed_description,
        color=discord.Color.red()
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
            videos = await get_latest_youtube_videos(session)

            if not videos:
                return

            # -------------------------------------------------
            # ERSTER START
            # -------------------------------------------------
            # Bereits vorhandene Videos/Streams werden beim
            # ersten Start nicht nachträglich angekündigt.
            # Ein bereits laufender Stream wird nur gemerkt.
            # -------------------------------------------------
            if last_youtube_video_id is None:
                last_youtube_video_id = videos[0]["id"]

                video_details = await get_video_details(
                    session,
                    [video["id"] for video in videos]
                )

                for video in video_details:
                    live_details = video.get("liveStreamingDetails")

                    if not live_details:
                        continue

                    actual_start = live_details.get("actualStartTime")
                    actual_end = live_details.get("actualEndTime")

                    if actual_start and not actual_end:
                        last_live_video_id = video["id"]

                print("YouTube-Checker gestartet.")
                return

            # -------------------------------------------------
            # NUR DER NEUESTE YOUTUBE-UPLOAD
            # -------------------------------------------------
            # Absichtlich nur videos[0] verarbeiten. Dadurch werden
            # ältere Uploads/Streams niemals als "neu" nachgeschickt.
            # -------------------------------------------------
            newest_video = videos[0]

            if newest_video["id"] != last_youtube_video_id:
                video_details = await get_video_details(
                    session,
                    [newest_video["id"]]
                )

                details = video_details[0] if video_details else {}
                live_details = details.get("liveStreamingDetails") or {}

                actual_start = live_details.get("actualStartTime")
                actual_end = live_details.get("actualEndTime")
                scheduled_start = live_details.get("scheduledStartTime")

                if scheduled_start and not actual_start:
                    embed = create_youtube_embed(
                        title=newest_video["title"],
                        video_id=newest_video["id"],
                        thumbnail=newest_video["thumbnail"],
                        description_text=newest_video.get("description", ""),
                        is_scheduled=True
                    )

                    await discord_channel.send(
                        content=(
                            f"@everyone {YOUTUBE_CHANNEL_NAME} "
                            f"hat einen **Stream geplant**. 📅"
                        ),
                        embed=embed
                    )

                elif actual_start and actual_end:
                    # Beendete Streams nicht als normales Video posten.
                    pass

                else:
                    # Normaler Upload oder Short: genau EIN neuer Eintrag.
                    embed = create_youtube_embed(
                        title=newest_video["title"],
                        video_id=newest_video["id"],
                        thumbnail=newest_video["thumbnail"],
                        description_text=newest_video.get("description", ""),
                        is_live=False
                    )

                    await discord_channel.send(
                        content=(
                            f"@everyone {YOUTUBE_CHANNEL_NAME} "
                            f"hat ein neues Video hochgeladen!"
                        ),
                        embed=embed
                    )

                # Sofort als gesehen markieren: ältere Feed-Einträge
                # werden dadurch niemals nachträglich verschickt.
                last_youtube_video_id = newest_video["id"]

            # LIVESTREAM STARTEN, DER SCHON VORHER GEPLANT WAR
            # -------------------------------------------------
            # Dieser zweite Check erkennt den Moment, in dem ein
            # bereits angekündigter Stream tatsächlich LIVE geht.
            # -------------------------------------------------
            video_details = await get_video_details(
                session,
                [video["id"] for video in videos]
            )

            for details in video_details:
                video_id = details["id"]
                live_details = details.get("liveStreamingDetails")

                if not live_details:
                    continue

                actual_start = live_details.get("actualStartTime")
                actual_end = live_details.get("actualEndTime")

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
                        description_text=matching_video.get("description", ""),
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
# TWITCH
# =========================================================

async def twitch_get_access_token(session):
    global twitch_access_token
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None
    try:
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials"
            },
            timeout=20
        ) as response:
            data = await response.json()
            if response.status != 200:
                print(f"Twitch OAuth Fehler {response.status}: {data}")
                return None
            twitch_access_token = data.get("access_token")
            return twitch_access_token
    except Exception as error:
        print(f"Fehler beim Twitch OAuth: {error}")
        return None


async def twitch_api_request(session, endpoint, params=None):
    global twitch_access_token
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None
    if not twitch_access_token:
        twitch_access_token = await twitch_get_access_token(session)
    if not twitch_access_token:
        return None

    url = f"https://api.twitch.tv/helix/{endpoint}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {twitch_access_token}"
    }

    try:
        async with session.get(
            url, headers=headers, params=params or {}, timeout=20
        ) as response:
            if response.status == 401:
                twitch_access_token = None
                twitch_access_token = await twitch_get_access_token(session)
                if not twitch_access_token:
                    return None
                headers["Authorization"] = f"Bearer {twitch_access_token}"
                async with session.get(
                    url, headers=headers, params=params or {}, timeout=20
                ) as retry_response:
                    if retry_response.status != 200:
                        text = await retry_response.text()
                        print(f"Twitch API Fehler {retry_response.status}: {text}")
                        return None
                    return await retry_response.json()

            if response.status != 200:
                text = await response.text()
                print(f"Twitch API Fehler {response.status}: {text}")
                return None
            return await response.json()
    except Exception as error:
        print(f"Fehler bei der Twitch API: {error}")
        return None


async def get_twitch_user_id(session):
    global twitch_user_id
    if twitch_user_id:
        return twitch_user_id

    data = await twitch_api_request(
        session, "users", {"login": TWITCH_CHANNEL_NAME}
    )
    if not data:
        return None

    users = data.get("data", [])
    if not users:
        print(f"Twitch-Kanal @{TWITCH_CHANNEL_NAME} wurde nicht gefunden.")
        return None

    twitch_user_id = users[0].get("id")
    return twitch_user_id


async def get_twitch_stream(session):
    user_id = await get_twitch_user_id(session)
    if not user_id:
        return None

    data = await twitch_api_request(
        session, "streams", {"user_id": user_id}
    )
    if not data:
        return None

    streams = data.get("data", [])
    return streams[0] if streams else None


def create_twitch_embed(stream):
    title = stream.get("title") or "Twitch-Livestream"
    game_name = stream.get("game_name") or ""
    thumbnail = stream.get("thumbnail_url")

    if thumbnail:
        thumbnail = thumbnail.replace("{width}", "1280")
        thumbnail = thumbnail.replace("{height}", "720")

    embed = discord.Embed(
        title=title,
        url=f"https://www.twitch.tv/{TWITCH_CHANNEL_NAME}",
        description="🔴 **LIVE auf Twitch**",
        color=discord.Color.red()
    )

    if game_name:
        embed.add_field(name="Spiel", value=game_name, inline=True)

    if thumbnail:
        embed.set_image(url=thumbnail)

    embed.set_footer(text="Kingtreffnix • Twitch")
    return embed


@tasks.loop(seconds=120)
async def twitch_checker():
    global twitch_was_live

    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return

    try:
        discord_channel = get_youtube_discord_channel()
        if discord_channel is None:
            print(
                f"Discord-Kanal {YOUTUBE_DISCORD_CHANNEL_NAME} "
                f"wurde für Twitch nicht gefunden."
            )
            return

        async with aiohttp.ClientSession() as session:
            stream = await get_twitch_stream(session)
            is_live = stream is not None

            if twitch_was_live is None:
                twitch_was_live = is_live
                print("Twitch-Checker gestartet.")
                return

            if is_live and not twitch_was_live:
                embed = create_twitch_embed(stream)
                await discord_channel.send(
                    content=(
                        f"@everyone {BOT_DISPLAY_NAME} ist gerade "
                        f"auf Twitch **LIVE**! 🔴\n"
                        f"https://www.twitch.tv/{TWITCH_CHANNEL_NAME}"
                    ),
                    embed=embed
                )

            twitch_was_live = is_live

    except asyncio.CancelledError:
        raise
    except Exception as error:
        print(f"Fehler im Twitch-Checker: {error}")


@twitch_checker.before_loop
async def before_twitch_checker():
    await bot.wait_until_ready()


# =========================================================
# /socialtest
# =========================================================

@bot.tree.command(
    name="socialtest",
    description="Testet die Social-Media-Benachrichtigung."
)
@app_commands.checks.has_permissions(administrator=True)
async def socialtest(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    discord_channel = get_youtube_discord_channel()
    if discord_channel is None:
        await interaction.followup.send(
            f"❌ Der Kanal **{YOUTUBE_DISCORD_CHANNEL_NAME}** wurde nicht gefunden.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Social-Media-Test",
        description=(
            f"🟣 **Twitch:** @{TWITCH_CHANNEL_NAME}\n\n"
            "TikTok und Instagram werden über ihre jeweiligen "
            "offiziellen Schnittstellen angebunden."
        ),
        color=discord.Color.red()
    )
    embed.set_footer(text=f"{BOT_DISPLAY_NAME} • Social Notifications")

    await discord_channel.send(
        content="🧪 **Social-Benachrichtigungstest**",
        embed=embed
    )

    await interaction.followup.send(
        f"✅ Test wurde in {discord_channel.mention} gesendet.",
        ephemeral=True
    )


# =========================================================
# YOUTUBE CHECKER START
# =========================================================

@youtube_checker.before_loop
async def before_youtube_checker():

    await bot.wait_until_ready()


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

    # Twitch-Checker starten (nur wenn Zugangsdaten vorhanden sind)
    if (
        TWITCH_CLIENT_ID
        and TWITCH_CLIENT_SECRET
        and not twitch_checker.is_running()
    ):
        twitch_checker.start()


# =========================================================
# BOT STARTEN
# =========================================================

bot.run(DISCORD_TOKEN)
