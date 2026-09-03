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
            # NEUE YOUTUBE-UPLOADS
            # -------------------------------------------------
            newest_video = videos[0]

            if newest_video["id"] != last_youtube_video_id:
                new_videos = []

                for video in videos:
                    if video["id"] == last_youtube_video_id:
                        break
                    new_videos.append(video)

                # Älteste zuerst ankündigen
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
                    details = details_by_id.get(video["id"])

                    if not details:
                        continue

                    live_details = details.get("liveStreamingDetails")

                    # -------------------------------------------------
                    # LIVESTREAM / GEPLANTER STREAM
                    # -------------------------------------------------
                    if live_details:
                        actual_start = live_details.get("actualStartTime")
                        actual_end = live_details.get("actualEndTime")

                        # Geplanter Stream: noch nicht gestartet.
                        # NIEMALS als normales Video behandeln.
                        if not actual_start:
                            embed = create_youtube_embed(
                                title=video["title"],
                                video_id=video["id"],
                                thumbnail=video["thumbnail"],
                                description_text=video.get("description", ""),
                                is_scheduled=True
                            )

                            await discord_channel.send(
                                content=(
                                    f"@everyone "
                                    f"{YOUTUBE_CHANNEL_NAME} "
                                    f"hat einen **Stream geplant**. 📅"
                                ),
                                embed=embed
                            )

                            continue

                        # Tatsächlich LIVE
                        if actual_start and not actual_end:
                            if video["id"] != last_live_video_id:
                                embed = create_youtube_embed(
                                    title=video["title"],
                                    video_id=video["id"],
                                    thumbnail=video["thumbnail"],
                                    description_text=video.get("description", ""),
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

                        # Beendete Streams nicht als normales Video posten.
                        continue

                    # -------------------------------------------------
                    # NORMALES VIDEO / SHORT
                    # -------------------------------------------------
                    embed = create_youtube_embed(
                        title=video["title"],
                        video_id=video["id"],
                        thumbnail=video["thumbnail"],
                        description_text=video.get("description", ""),
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


# =========================================================
# BOT STARTEN
# =========================================================

bot.run(DISCORD_TOKEN)
