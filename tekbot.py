import os
import sys
import time
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


# ============================================================
# BEÁLLÍTÁSOK
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# SQLite adatbázis
# Fly.io-n a fly.toml-ban:
# DB_PATH = "/data/duty.db"
DB_PATH = os.getenv("DB_PATH", "duty.db")


# ============================================================
# ENGEDÉLYEZETT SZERVEREK
# ============================================================

ALLOWED_GUILDS = {
    1542483166932246620,  # TESZT SZERVER
    1535743519220830361,  # ÉLES SZERVER
}


# ============================================================
# JOGOSULTSÁGOK
# ============================================================

# /reset használhatja:
RESET_ALLOWED_USERS = {
    1125866681860894780,
    747749105346019338,
}

# /ujraindit használhatja:
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

    h = seconds // 3600
    m = (seconds % 3600) // 60
    sec = seconds % 60

    if h > 0:
        return f"{h} óra {m} perc {sec} mp"

    if m > 0:
        return f"{m} perc {sec} mp"

    return f"{sec} mp"


def guild_allowed(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False

    return interaction.guild.id in ALLOWED_GUILDS


# ============================================================
# /SZOLGALAT
# ============================================================

@app_commands.guilds(
    discord.Object(id=1542483166932246620),
    discord.Object(id=1535743519220830361)
)
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

    # Extra védelem
    if not guild_allowed(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
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

        # Szolgálati idő hozzáadása
        add_total_time(user_id, elapsed)

        # Aktív szolgálat törlése
        stop_duty(user_id)

        total_time = get_total_time(user_id)

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} leadta a szolgálatot.\n"
            f"⏱️ Eltöltött idő: **{format_ido(elapsed)}**\n"
            f"📊 Összes szolgálati idő: **{format_ido(total_time)}**"
        )


# ============================================================
# /SZOLGALAT INFO
# ============================================================

@app_commands.guilds(
    discord.Object(id=1542483166932246620),
    discord.Object(id=1535743519220830361)
)
@app_commands.command(
    name="szolgalat_info",
    description="Megmutatja, kik vannak jelenleg szolgálatban"
)
async def szolgalat_info(
    interaction: discord.Interaction
):

    # Extra védelem
    if not guild_allowed(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    active_users = get_active_users()

    if not active_users:
        await interaction.response.send_message(
            "📭 Jelenleg senki nincs szolgálatban."
        )
        return

    lines = []

    now = time.time()

    for row in active_users:

        user_id = row["user_id"]
        start_time = float(row["start_time"])

        elapsed = now - start_time

        member = interaction.guild.get_member(user_id)

        if member:
            name = member.mention
        else:
            name = f"<@{user_id}>"

        lines.append(
            f"🟢 {name} — **{format_ido(elapsed)}**"
        )

    await interaction.response.send_message(
        "👮 **Jelenleg szolgálatban:**\n\n" +
        "\n".join(lines)
    )


# ============================================================
# /LEADERBOARD
# ============================================================

@app_commands.guilds(
    discord.Object(id=1542483166932246620),
    discord.Object(id=1535743519220830361)
)
@app_commands.command(
    name="leaderboard",
    description="Szolgálati idő ranglista"
)
async def leaderboard(
    interaction: discord.Interaction
):

    # Extra védelem
    if not guild_allowed(interaction):
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
# /RESET
# ============================================================

@app_commands.guilds(
    discord.Object(id=1542483166932246620),
    discord.Object(id=1535743519220830361)
)
@app_commands.command(
    name="reset",
    description="Minden szolgálati idő törlése"
)
async def reset(
    interaction: discord.Interaction
):

    # Szerver ellenőrzés
    if not guild_allowed(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    # Felhasználó ellenőrzés
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


# ============================================================
# /UJRAINDIT
# ============================================================

@app_commands.guilds(
    discord.Object(id=1542483166932246620),
    discord.Object(id=1535743519220830361)
)
@app_commands.command(
    name="ujraindit",
    description="Bot újraindítása"
)
async def ujraindit(
    interaction: discord.Interaction
):

    # Szerver ellenőrzés
    if not guild_allowed(interaction):
        await interaction.response.send_message(
            "🚫 Ez a bot ezen a szerveren nem használható.",
            ephemeral=True
        )
        return

    # Csak te használhatod
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
# PARANCSOK REGISZTRÁLÁSA
# ============================================================

bot.tree.add_command(szolgalat)
bot.tree.add_command(szolgalat_info)
bot.tree.add_command(leaderboard)
bot.tree.add_command(reset)
bot.tree.add_command(ujraindit)


# ============================================================
# BOT INDULÁS
# ============================================================

@bot.event
async def on_ready():

    init_database()

    guilds = [
        discord.Object(id=1542483166932246620),
        discord.Object(id=1535743519220830361),
    ]

    # A korábban globálisan regisztrált parancsok eltávolítása.
    # Ez fontos, mert korábban globálisan voltak szinkronizálva.
    bot.tree.clear_commands(guild=None)

    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"⚠️ Globális parancsok törlése sikertelen: {e}")

    # A parancsok regisztrálása kizárólag a két engedélyezett szerverre.
    for guild in guilds:
        try:
            await bot.tree.sync(guild=guild)

            print(
                f"✅ Parancsok szinkronizálva: {guild.id}"
            )

        except Exception as e:
            print(
                f"❌ Parancs szinkronizálási hiba "
                f"({guild.id}): {e}"
            )

    print(
        f"✅ Bejelentkezve mint {bot.user}"
    )

    print(
        f"💾 SQLite adatbázis: {DB_PATH}"
    )

    print(
        "🔒 Engedélyezett szerverek:"
    )

    for guild_id in ALLOWED_GUILDS:
        print(f"   - {guild_id}")


# ============================================================
# INDÍTÁS
# ============================================================

if not BOT_TOKEN or not BOT_TOKEN.strip():
    raise RuntimeError(
        "❌ DISCORD_TOKEN nincs beállítva "
        "(Secrets / Environment Variables)."
    )


# Adatbázis létrehozása még indulás előtt
init_database()

bot.run(BOT_TOKEN.strip())
