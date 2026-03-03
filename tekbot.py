import os
import sys
import time

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Lokálisan hasznos (Fly-on nem baj, ha van)
load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("DISCORD_TOKEN nincs beállítva environment variable-ként!")

# Discord bot beállítások
intents = discord.Intents.default()
intents.message_content = True  # nem kötelező a slash-hez, de nem baj ha kell később

# FONTOS: ne legyen '/' a prefix, mert összekever a slash-sel
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Adatok memóriában (újraindításnál nullázódik) ---
szolgalati_idok: dict[int, float] = {}          # user_id -> összes másodperc
aktiv_szolgalat_kezdete: dict[int, float] = {}  # user_id -> start timestamp

# Csak te használhatod ezeket (reset/ujraindit)
bot_owner_id = 1125866681860894780

# A szerver, ahol a slash parancsok megjelenjenek (GUILD COMMAND)
GUILD_ID = 1476755863610986546


def format_ido(seconds: float) -> str:
    seconds = int(seconds)
    ora = seconds // 3600
    perc = (seconds % 3600) // 60
    mp = seconds % 60
    if ora > 0:
        return f"{ora} óra {perc} perc {mp} mp"
    return f"{perc} perc {mp} mp"


@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)

    # Sync csak erre az 1 szerverre (gyors)
    try:
        await bot.tree.sync(guild=guild)
        print(f"✅ Bejelentkezve mint {bot.user}")
        print(f"✅ Slash parancsok szinkronizálva erre a szerverre: {GUILD_ID}")
    except discord.Forbidden:
        print("❌ Missing Access a slash sync-hez.")
        print("   Ellenőrizd: bot bent van-e a szerveren + applications.commands scope-pal lett-e behívva.")


# ---------- SLASH PARANCSOK ----------

@bot.tree.command(name="szolgalat", description="Szolgálat felvétel vagy leadás", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(muvelet="felvetel vagy leadas")
async def szolgalat(interaction: discord.Interaction, muvelet: str):
    user_id = interaction.user.id
    now = time.time()

    m = muvelet.lower().strip()

    if m == "felvetel":
        if user_id in aktiv_szolgalat_kezdete:
            await interaction.response.send_message("❗ Már szolgálatban vagy!", ephemeral=True)
            return
        aktiv_szolgalat_kezdete[user_id] = now
        await interaction.response.send_message(f"✅ {interaction.user.mention} szolgálatba lépett.")

    elif m == "leadas":
        if user_id not in aktiv_szolgalat_kezdete:
            await interaction.response.send_message("❗ Nem vagy szolgálatban!", ephemeral=True)
            return

        kezdes = aktiv_szolgalat_kezdete.pop(user_id)
        eltelt = now - kezdes
        szolgalati_idok[user_id] = szolgalati_idok.get(user_id, 0.0) + eltelt

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} szolgálatot leadta.\n"
            f"⏱️ Eltöltött idő: {format_ido(eltelt)}"
        )

    else:
        await interaction.response.send_message(
            "⚠️ Érvénytelen művelet. Használd: **felvetel** vagy **leadas**.",
            ephemeral=True
        )


@szolgalat.autocomplete("muvelet")
async def autocomplete_muvelet(interaction: discord.Interaction, current: str):
    options = [
        app_commands.Choice(name="felvetel", value="felvetel"),
        app_commands.Choice(name="leadas", value="leadas"),
    ]
    current = (current or "").lower()
    return [o for o in options if o.name.startswith(current)]


@bot.tree.command(name="szolgalat_leaderboard", description="Szolgálati idő ranglista", guild=discord.Object(id=GUILD_ID))
async def szolgalat_leaderboard(interaction: discord.Interaction):
    if not szolgalati_idok:
        await interaction.response.send_message("📭 Még senki nem volt szolgálatban.")
        return

    sorted_users = sorted(szolgalati_idok.items(), key=lambda x: x[1], reverse=True)

    lines = []
    for i, (uid, sec) in enumerate(sorted_users[:20], start=1):
        lines.append(f"**{i}.** <@{uid}> — {format_ido(sec)}")

    await interaction.response.send_message("🏆 **Szolgálati leaderboard:**\n" + "\n".join(lines))


@bot.tree.command(name="reset", description="Minden szolgálati idő törlése (csak tulaj)", guild=discord.Object(id=GUILD_ID))
async def reset(interaction: discord.Interaction):
    if interaction.user.id != bot_owner_id:
        await interaction.response.send_message("🚫 Nincs jogosultságod a resethez.", ephemeral=True)
        return

    szolgalati_idok.clear()
    aktiv_szolgalat_kezdete.clear()
    await interaction.response.send_message("🗑️ Minden szolgálati idő törölve lett.", ephemeral=True)


@bot.tree.command(name="ujraindit", description="Bot újraindítása (csak tulaj)", guild=discord.Object(id=GUILD_ID))
async def ujraindit(interaction: discord.Interaction):
    if interaction.user.id != bot_owner_id:
        await interaction.response.send_message("🚫 Nincs jogosultságod újraindítani a botot.", ephemeral=True)
        return

    await interaction.response.send_message("🔁 Újraindítás...", ephemeral=True)
    await bot.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)


# Ha valaki mégis prefix parancsot ír (pl. /szolgalat üzenetként), ne spameljen hibát
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


bot.run(BOT_TOKEN)
