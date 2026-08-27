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

# SQLite adatbázis helye
# Fly.io volume esetén ezt a fly.toml-ban fogjuk beállítani.
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


async def is_server_owner(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False

    return interaction.user.id == interaction.guild.owner_id


# ============================================================
# DISCORD BOT
# ============================================================

# Slash parancsokhoz nem kell message_content intent
intents = discord.Intents.default()

# Prefixet ne "/"-ra tedd, mert összekeveri a slash-sel
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


# ============================================================
# /szolgalat
# ============================================================

@bot.tree.command(
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

        eltelt = now - start

        # Szolgálati idő hozzáadása
        add_total_time(user_id, eltelt)

        # Aktív szolgálat törlése
        stop_duty(user_id)

        total_time = get_total_time(user_id)

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} szolgálatot leadta.\n"
            f"⏱️ Eltöltött idő: **{format_ido(eltelt)}**\n"
            f"📊 Összes szolgálati idő: **{format_ido(total_time)}**"
        )


# ============================================================
# /leaderboard
# ============================================================

@bot.tree.command(
    name="leaderboard",
    description="Szolgálati idő ranglista"
)
async def leaderboard(interaction: discord.Interaction):

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

    if not await is_server_owner(interaction):
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

    if not await is_server_owner(interaction):
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

# Adatbázis létrehozása még a bot indítása előtt
init_database()

bot.run(BOT_TOKEN.strip())
