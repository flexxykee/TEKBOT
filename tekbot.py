import os
import sys
import time

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Lokális futtatásnál segít; hoston a környezeti változókból jön
load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# Slash parancsokhoz nem kell message_content intent
intents = discord.Intents.default()

# Prefixet ne "/"-ra tedd, mert összekeveri a slash-sel
bot = commands.Bot(command_prefix="!", intents=intents)

# Memóriában tárol (újraindításnál nullázódik)
szolgalati_idok: dict[int, float] = {}
aktiv_szolgalat_kezdete: dict[int, float] = {}


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
    # Ha DM-ben próbálja -> tiltjuk
    if interaction.guild is None:
        return False
    return interaction.user.id == interaction.guild.owner_id


@bot.event
async def on_ready():
    # Globál sync (minden szerveren működik, ahol bent van)
    await bot.tree.sync()
    print(f"✅ Bejelentkezve mint {bot.user} | Slash parancsok szinkronizálva (globál).")


# /szolgalat felvetel|leadas
@bot.tree.command(name="szolgalat", description="Szolgálat felvétele vagy leadása")
@app_commands.choices(muvelet=[
    app_commands.Choice(name="felvetel", value="felvetel"),
    app_commands.Choice(name="leadas", value="leadas"),
])
async def szolgalat(interaction: discord.Interaction, muvelet: app_commands.Choice[str]):
    user_id = interaction.user.id
    now = time.time()

    if muvelet.value == "felvetel":
        if user_id in aktiv_szolgalat_kezdete:
            await interaction.response.send_message("❗ Már szolgálatban vagy.", ephemeral=True)
            return
        aktiv_szolgalat_kezdete[user_id] = now
        await interaction.response.send_message(f"✅ {interaction.user.mention} szolgálatba lépett.")

    elif muvelet.value == "leadas":
        if user_id not in aktiv_szolgalat_kezdete:
            await interaction.response.send_message("❗ Nem vagy szolgálatban.", ephemeral=True)
            return

        start = aktiv_szolgalat_kezdete.pop(user_id)
        eltelt = now - start
        szolgalati_idok[user_id] = szolgalati_idok.get(user_id, 0.0) + eltelt

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} szolgálatot leadta. Eltöltött idő: **{format_ido(eltelt)}**."
        )


# /leaderboard
@bot.tree.command(name="leaderboard", description="Szolgálati idő ranglista")
async def leaderboard(interaction: discord.Interaction):
    if not szolgalati_idok:
        await interaction.response.send_message("📭 Még nincs szolgálati adat.")
        return

    sorted_users = sorted(szolgalati_idok.items(), key=lambda x: x[1], reverse=True)

    lines = []
    for i, (uid, seconds) in enumerate(sorted_users[:20], start=1):
        lines.append(f"**{i}.** <@{uid}> — {format_ido(seconds)}")

    await interaction.response.send_message("🏆 **Szolgálati leaderboard**\n" + "\n".join(lines))


# /reset (csak a szerver tulajdonosa)
@bot.tree.command(name="reset", description="Minden szolgálati idő törlése (csak szerver tulaj)")
async def reset(interaction: discord.Interaction):
    if not await is_server_owner(interaction):
        await interaction.response.send_message("🚫 Csak a szerver tulajdonosa használhatja.", ephemeral=True)
        return

    szolgalati_idok.clear()
    aktiv_szolgalat_kezdete.clear()
    await interaction.response.send_message("🗑️ Minden szolgálati idő törölve.", ephemeral=True)


# /ujraindit (csak a szerver tulajdonosa)
@bot.tree.command(name="ujraindit", description="Bot újraindítása (csak szerver tulaj)")
async def ujraindit(interaction: discord.Interaction):
    if not await is_server_owner(interaction):
        await interaction.response.send_message("🚫 Csak a szerver tulajdonosa használhatja.", ephemeral=True)
        return

    await interaction.response.send_message("🔁 Újraindítás...", ephemeral=True)

    await bot.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)


# Indítás
if not BOT_TOKEN or not BOT_TOKEN.strip():
    raise RuntimeError("❌ DISCORD_TOKEN nincs beállítva (Secrets / Environment Variables).")

bot.run(BOT_TOKEN.strip())
