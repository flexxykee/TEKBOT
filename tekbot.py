import os
import sys
import time
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv


# ============================================================
# BEÁLLÍTÁSOK
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# Fly.io volume
# Fly-on: /data/duty.db
# Lokálisan: duty.db
DB_PATH = os.getenv("DB_PATH", "duty.db")


# ============================================================
# CSATORNÁK
# ============================================================

# A normál parancsok csak ebben a csatornában használhatók.
COMMAND_CHANNEL_ID = 1543671340769480816

# Ide kerül a folyamatosan frissülő szolgálati lista.
# EZT ÁLLÍTSD ÁT A SZOLGÁLATI SZOBA ID-JÁRA!
INFO_CHANNEL_ID = 1543671340769480816


# ============================================================
# JOGOSULTSÁGOK
# ============================================================

# Ezek a felhasználók minden csatornából használhatják
# a parancsokat, és a speciális adminisztrációs parancsokra
# is jogosultak.
RESET_ALLOWED_USERS = {
    1125866681860894780,
    747749105346019338,
}

# /ujraindit használatára csak ez a felhasználó jogosult.
RESTART_ALLOWED_USERS = {
    1125866681860894780,
}


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# ADATBÁZIS
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            total_seconds REAL NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS active_duty (
            user_id INTEGER PRIMARY KEY,
            start_time REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def get_total_time(user_id: int) -> float:
    conn = get_db()

    row = conn.execute(
        "SELECT total_seconds FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    if row is None:
        return 0.0

    return float(row["total_seconds"])


def add_total_time(user_id: int, seconds: float):
    conn = get_db()

    conn.execute("""
        INSERT INTO users (user_id, total_seconds)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            total_seconds = total_seconds + excluded.total_seconds
    """, (user_id, seconds))

    conn.commit()
    conn.close()


def get_active_start(user_id: int):
    conn = get_db()

    row = conn.execute(
        "SELECT start_time FROM active_duty WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    if row is None:
        return None

    return float(row["start_time"])


def start_duty(user_id: int, start_time: float):
    conn = get_db()

    conn.execute("""
        INSERT OR REPLACE INTO active_duty (user_id, start_time)
        VALUES (?, ?)
    """, (user_id, start_time))

    conn.commit()
    conn.close()


def stop_duty(user_id: int):
    conn = get_db()

    conn.execute(
        "DELETE FROM active_duty WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


def get_active_users():
    conn = get_db()

    rows = conn.execute("""
        SELECT user_id, start_time
        FROM active_duty
        ORDER BY start_time ASC
    """).fetchall()

    conn.close()

    return rows


def get_leaderboard():
    conn = get_db()

    rows = conn.execute("""
        SELECT user_id, total_seconds
        FROM users
        WHERE total_seconds > 0
        ORDER BY total_seconds DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    return rows


def reset_database():
    conn = get_db()

    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM active_duty")

    conn.commit()
    conn.close()


# ============================================================
# SEGÉDFÜGGVÉNYEK
# ============================================================

def format_ido(seconds: float) -> str:
    seconds = max(0, int(seconds))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours} óra {minutes} perc {secs} mp"

    if minutes > 0:
        return f"{minutes} perc {secs} mp"

    return f"{secs} mp"


def channel_allowed(interaction: discord.Interaction) -> bool:
    """
    A két kiemelt felhasználó minden csatornából használhatja
    a parancsokat.

    Mindenki más csak a COMMAND_CHANNEL_ID csatornában.
    """

    if interaction.user.id in RESET_ALLOWED_USERS:
        return True

    return interaction.channel_id == COMMAND_CHANNEL_ID


# ============================================================
# /SZOLGALAT
# ============================================================

@app_commands.command(
    name="szolgalat",
    description="Szolgálat felvétele vagy leadása"
)
@app_commands.choices(muvelet=[
    app_commands.Choice(
        name="felvetel",
        value="felvetel"
    ),
    app_commands.Choice(
        name="leadas",
        value="leadas"
    ),
])
async def szolgalat(
    interaction: discord.Interaction,
    muvelet: app_commands.Choice[str]
):

    # Csatorna ellenőrzés
    if not channel_allowed(interaction):
        await interaction.response.send_message(
            "🚫 A parancsokat csak a kijelölt szolgálati csatornában használhatod.",
            ephemeral=True
        )
        return

    user_id = interaction.user.id
    now = time.time()

    # ========================================================
    # SZOLGÁLAT FELVÉTEL
    # ========================================================

    if muvelet.value == "felvetel":

        active_start = get_active_start(user_id)

        if active_start is not None:
            await interaction.response.send_message(
                "❗ Már szolgálatban vagy.",
                ephemeral=True
            )
            return

        start_duty(user_id, now)

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} szolgálatba lépett."
        )

        await update_info_channel()

    # ========================================================
    # SZOLGÁLAT LEADÁS
    # ========================================================

    elif muvelet.value == "leadas":

        start = get_active_start(user_id)

        if start is None:
            await interaction.response.send_message(
                "❗ Nem vagy szolgálatban.",
                ephemeral=True
            )
            return

        elapsed = now - start

        add_total_time(user_id, elapsed)
        stop_duty(user_id)

        total_time = get_total_time(user_id)

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} leadta a szolgálatot.\n"
            f"⏱️ Eltöltött idő: **{format_ido(elapsed)}**\n"
            f"📊 Összes szolgálati idő: **{format_ido(total_time)}**"
        )

        await update_info_channel()


# ============================================================
# /SZOLGALAT_KIVESZ
# ============================================================

@bot.tree.command(
    name="szolgalat_kivesz",
    description="Egy személy kivétele az aktív szolgálatból"
)
@app_commands.describe(
    felhasznalo="Az a személy, akit ki szeretnél venni szolgálatból"
)
async def szolgalat_kivesz(
    interaction: discord.Interaction,
    felhasznalo: discord.Member
):

    # Csak a két meghatározott felhasználó
    if interaction.user.id not in RESET_ALLOWED_USERS:
        await interaction.response.send_message(
            "🚫 Nincs jogosultságod a /szolgalat_kivesz használatához.",
            ephemeral=True
        )
        return

    user_id = felhasznalo.id
    start = get_active_start(user_id)

    if start is None:
        await interaction.response.send_message(
            f"❗ {felhasznalo.mention} jelenleg nincs szolgálatban.",
            ephemeral=True
        )
        return

    now = time.time()
    elapsed = now - start

    # Aktív idő hozzáadása az összesített időhöz
    add_total_time(user_id, elapsed)

    # Szolgálat lezárása
    stop_duty(user_id)

    total_time = get_total_time(user_id)

    await interaction.response.send_message(
        f"⛔ {felhasznalo.mention} ki lett véve a szolgálatból.\n"
        f"⏱️ Aktív szolgálati idő: **{format_ido(elapsed)}**\n"
        f"📊 Összes szolgálati idő: **{format_ido(total_time)}**"
    )

    await update_info_channel()


# ============================================================
# /SZOLGALAT_HOZZAAD
# ============================================================

@bot.tree.command(
    name="szolgalat_hozzaad",
    description="Szolgálati idő hozzáadása egy személyhez"
)
@app_commands.describe(
    felhasznalo="Az a személy, akinek időt szeretnél hozzáadni",
    perc="Hozzáadandó szolgálati idő percben"
)
async def szolgalat_hozzaad(
    interaction: discord.Interaction,
    felhasznalo: discord.Member,
    perc: int
):

    # Csak a két meghatározott felhasználó
    if interaction.user.id not in RESET_ALLOWED_USERS:
        await interaction.response.send_message(
            "🚫 Nincs jogosultságod a /szolgalat_hozzaad használatához.",
            ephemeral=True
        )
        return

    if perc <= 0:
        await interaction.response.send_message(
            "❗ A hozzáadandó percnek legalább 1-nek kell lennie.",
            ephemeral=True
        )
        return

    seconds = perc * 60

    add_total_time(felhasznalo.id, seconds)

    total_time = get_total_time(felhasznalo.id)

    await interaction.response.send_message(
        f"➕ {felhasznalo.mention} szolgálati idejéhez "
        f"**{perc} perc** hozzáadva.\n"
        f"📊 Összes szolgálati idő: **{format_ido(total_time)}**"
    )


# ============================================================
# /LEADERBOARD
# ============================================================

@bot.tree.command(
    name="leaderboard",
    description="Szolgálati idő ranglista"
)
async def leaderboard(
    interaction: discord.Interaction
):

    # Csatorna ellenőrzés
    if not channel_allowed(interaction):
        await interaction.response.send_message(
            "🚫 A parancsokat csak a kijelölt szolgálati csatornában használhatod.",
            ephemeral=True
        )
        return

    rows = get_leaderboard()

    if not rows:
        await interaction.response.send_message(
            "📭 Még nincs szolgálati adat."
        )
        return

    lines = []

    for i, row in enumerate(rows, start=1):

        uid = row["user_id"]
        seconds = row["total_seconds"]

        if i == 1:
            hely = "🥇"
        elif i == 2:
            hely = "🥈"
        elif i == 3:
            hely = "🥉"
        else:
            hely = f"**{i}.**"

        lines.append(
            f"{hely} <@{uid}> — **{format_ido(seconds)}**"
        )

    await interaction.response.send_message(
        "🏆 **P&M Duty Leaderboard**\n\n" +
        "\n".join(lines)
    )


# ============================================================
# /RESET
# ============================================================

@bot.tree.command(
    name="reset",
    description="Minden szolgálati idő és aktív szolgálat törlése"
)
async def reset(
    interaction: discord.Interaction
):

    # Csak a két meghatározott felhasználó
    if interaction.user.id not in RESET_ALLOWED_USERS:
        await interaction.response.send_message(
            "🚫 Nincs jogosultságod a /reset használatához.",
            ephemeral=True
        )
        return

    reset_database()

    await interaction.response.send_message(
        "🗑️ Minden szolgálati idő és aktív szolgálat törölve.",
        ephemeral=True
    )

    await update_info_channel()


# ============================================================
# /UJRAINDIT
# ============================================================

@bot.tree.command(
    name="ujraindit",
    description="Bot újraindítása"
)
async def ujraindit(
    interaction: discord.Interaction
):

    # Csak ez a felhasználó
    if interaction.user.id not in RESTART_ALLOWED_USERS:
        await interaction.response.send_message(
            "🚫 Nincs jogosultságod a /ujraindit használatához.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🔁 Bot újraindítása...",
        ephemeral=True
    )

    await bot.close()

    os.execv(
        sys.executable,
        [sys.executable] + sys.argv
    )


# ============================================================
# /SZOLGALAT PARANCS HOZZÁADÁSA
# ============================================================

bot.tree.add_command(szolgalat)


# ============================================================
# SZOLGÁLATI INFO CSATORNA
# ============================================================

info_message = None


async def update_info_channel():
    """
    Folyamatosan frissíti a szolgálati információs üzenetet.
    """

    global info_message

    channel = bot.get_channel(INFO_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(INFO_CHANNEL_ID)
        except Exception as e:
            print(
                f"❌ Információs csatorna nem található: {e}"
            )
            return

    if not isinstance(channel, discord.TextChannel):
        print("❌ Az INFO_CHANNEL_ID nem szöveges csatornára mutat.")
        return

    active_users = get_active_users()
    now = time.time()

    lines = []

    for row in active_users:

        uid = row["user_id"]
        start_time = float(row["start_time"])

        elapsed = now - start_time

        member = channel.guild.get_member(uid)

        if member:
            name = member.mention
        else:
            name = f"<@{uid}>"

        lines.append(
            f"🟢 {name} — **{format_ido(elapsed)}**"
        )

    if lines:

        content = (
            "👮 **JELENLEG SZOLGÁLATBAN**\n\n"
            + "\n".join(lines)
            + "\n\n"
            "🔄 Az információ automatikusan frissül."
        )

    else:

        content = (
            "👮 **JELENLEG SZOLGÁLATBAN**\n\n"
            "📭 Jelenleg senki nincs szolgálatban.\n\n"
            "🔄 Az információ automatikusan frissül."
        )

    try:

        if info_message is None:

            # Utolsó bot üzenet keresése
            async for message in channel.history(limit=20):

                if (
                    message.author == bot.user
                    and message.embeds == []
                ):
                    info_message = message
                    break

        if info_message is None:

            info_message = await channel.send(content)

        else:

            await info_message.edit(content=content)

    except discord.NotFound:

        info_message = await channel.send(content)

    except discord.Forbidden:

        print(
            "❌ Nincs jogosultságom az információs csatornához."
        )

    except Exception as e:

        print(
            f"❌ Információs üzenet frissítési hiba: {e}"
        )


# ============================================================
# AUTOMATIKUS INFO FRISSÍTÉS
# ============================================================

@tasks.loop(seconds=30)
async def update_info_loop():
    await update_info_channel()


# ============================================================
# BOT INDULÁS
# ============================================================

@bot.event
async def on_ready():

    init_database()

    print(f"✅ Bejelentkezve mint {bot.user}")
    print(f"💾 SQLite adatbázis: {DB_PATH}")
    print(
        f"📢 Parancs csatorna: {COMMAND_CHANNEL_ID}"
    )
    print(
        f"👮 Info csatorna: {INFO_CHANNEL_ID}"
    )

    # --------------------------------------------------------
    # GLOBÁLIS PARANCSOK SZINKRONIZÁLÁSA
    # --------------------------------------------------------

    try:

        synced = await bot.tree.sync()

        print(
            f"✅ Globálisan szinkronizált parancsok: {len(synced)}"
        )

        for command in synced:
            print(
                f"   /{command.name}"
            )

    except Exception as e:

        print(
            f"❌ Globális parancs szinkronizálási hiba: {e}"
        )

    # --------------------------------------------------------
    # INFO CSATORNA
    # --------------------------------------------------------

    await update_info_channel()

    if not update_info_loop.is_running():
        update_info_loop.start()

    print(
        "🔒 A bot minden szerveren használható."
    )

    print(
        "📢 Normál felhasználók csak a kijelölt csatornában "
        "használhatják a parancsokat."
    )

    print(
        "👑 A jogosult felhasználók minden csatornából "
        "használhatják a parancsokat."
    )


# ============================================================
# INDÍTÁS
# ============================================================

if not BOT_TOKEN or not BOT_TOKEN.strip():
    raise RuntimeError(
        "❌ DISCORD_TOKEN nincs beállítva "
        "(Secrets / Environment Variables)."
    )


# Adatbázis inicializálása
init_database()


# Bot indítása
bot.run(BOT_TOKEN.strip())
