import os
import sys
import time
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Lokális futtatásnál segít; Fly.io-n a környezeti változóból jön
load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# ============================================================
# BEÁLLÍTÁSOK
# ============================================================

# IDE ÍRD A SAJÁT DISCORD SZERVERED ID-JÁT
# Példa:
# ALLOWED_GUILD_ID = 123456789012345678

ALLOWED_GUILD_ID = 123456789012345678


# SQLite adatbázis helye
# Fly.io esetén a fly.toml:
# DB_PATH = "/data/duty.db"

DB_PATH = os.getenv("DB_PATH", "duty.db")


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
        DO UPDATE SET total_seconds = total_seconds + excluded.total_seconds
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
    s = int(seconds)

    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60

    if h > 0:
        return f"{h} óra {m} perc {sec} mp"

    if m > 0:
        return f"{m} perc {sec} mp"

    return f"{sec} mp"


def is_allowed_guild(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and interaction.guild.id == ALLOWED_GUILD_ID
    )


def is_server_owner(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False

    return interaction.user.id == interaction.guild.owner_id


# ============================================================
# DISCORD BOT
# ============================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# BOT INDULÁS
# ============================================================

@bot.event
async def on_ready():

    init_database()

    await bot.tree.sync()

    print(
        f"✅ Bejelentkezve mint {bot.user} | "
        f"Slash parancsok szinkronizálva (globál)."
    )

    print(f"💾 SQLite adatbázis: {DB_PATH}")
    print(f"🔒 Engedélyezett szerver ID: {ALLOWED_GUILD_ID}")


# ============================================================
# /szolgalat
# ============================================================

szolgalat_group = app_commands.Group(
    name="szolgalat",
    description="Szolgálati rendszer"
)


# ============================================================
# /szolgalat felvetel
# ============================================================

@szolgalat_group.command(
    name="felvetel",
    description="Szolgálat felvétele"
)
async def szolgalat_felvetel(interaction: discord.Interaction):

    if not is_allowed_guild(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    user_id = interaction.user.id
    now = time.time()

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


# ============================================================
# /szolgalat leadas
# ============================================================

@szolgalat_group.command(
    name="leadas",
    description="Szolgálat leadása"
)
async def szolgalat_leadas(interaction: discord.Interaction):

    if not is_allowed_guild(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    user_id = interaction.user.id
    now = time.time()

    start = get_active_start(user_id)

    if start is None:
        await interaction.response.send_message(
            "❗ Nem vagy szolgálatban.",
            ephemeral=True
        )
        return

    eltelt = now - start

    add_total_time(user_id, eltelt)
    stop_duty(user_id)

    total_time = get_total_time(user_id)

    await interaction.response.send_message(
        f"✅ {interaction.user.mention} szolgálatot leadta.\n"
        f"⏱️ Eltöltött idő: **{format_ido(eltelt)}**\n"
        f"📊 Összes szolgálati idő: **{format_ido(total_time)}**"
    )


# ============================================================
# /szolgalat info
# ============================================================

@szolgalat_group.command(
    name="info",
    description="Megmutatja, kik vannak jelenleg szolgálatban"
)
async def szolgalat_info(interaction: discord.Interaction):

    if not is_allowed_guild(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    rows = get_active_users()

    if not rows:
        await interaction.response.send_message(
            "📭 Jelenleg senki nincs szolgálatban."
        )
        return

    now = time.time()

    lines = []

    for row in rows:
        user_id = row["user_id"]
        start_time = float(row["start_time"])

        elapsed = now - start_time

        member = interaction.guild.get_member(user_id)

        if member is not None:
            name = member.mention
        else:
            name = f"<@{user_id}>"

        lines.append(
            f"👮 {name} — **{format_ido(elapsed)}**"
        )

    embed = discord.Embed(
        title="👮 Jelenleg szolgálatban",
        description="\n".join(lines),
        color=discord.Color.blue()
    )

    embed.set_footer(
        text=f"Összes szolgálatban lévő személy: {len(rows)}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /szolgalat CSOPORT REGISZTRÁLÁSA
# ============================================================

bot.tree.add_command(szolgalat_group)


# ============================================================
# /leaderboard
# ============================================================

@bot.tree.command(
    name="leaderboard",
    description="Szolgálati idő ranglista"
)
async def leaderboard(interaction: discord.Interaction):

    if not is_allowed_guild(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
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
# /reset
# ============================================================

@bot.tree.command(
    name="reset",
    description="Minden szolgálati idő törlése (csak szerver tulaj)"
)
async def reset(interaction: discord.Interaction):

    if not is_allowed_guild(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    if not is_server_owner(interaction):
        await interaction.response.send_message(
            "🚫 Csak a szerver tulajdonosa használhatja.",
            ephemeral=True
        )
        return

    reset_database()

    await interaction.response.send_message(
        "🗑️ Minden szolgálati idő és aktív szolgálat törölve.",
        ephemeral=True
    )


# ============================================================
# /ujraindit
# ============================================================

@bot.tree.command(
    name="ujraindit",
    description="Bot újraindítása (csak szerver tulaj)"
)
async def ujraindit(interaction: discord.Interaction):

    if not is_allowed_guild(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    if not is_server_owner(interaction):
        await interaction.response.send_message(
            "🚫 Csak a szerver tulajdonosa használhatja.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🔁 Újraindítás...",
        ephemeral=True
    )

    await bot.close()

    os.execv(
        sys.executable,
        [sys.executable] + sys.argv
    )


# ============================================================
# INDÍTÁS
# ============================================================

if not BOT_TOKEN or not BOT_TOKEN.strip():
    raise RuntimeError(
        "❌ DISCORD_TOKEN nincs beállítva "
        "(Secrets / Environment Variables)."
    )

init_database()

bot.run(BOT_TOKEN.strip())
