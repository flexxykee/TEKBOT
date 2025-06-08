import discord
from discord import app_commands
from discord.ext import commands
import os
import sys
import time
from dotenv import load_dotenv

# .env betöltése
load_dotenv()

# Token betöltése
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# Discord bot beállításai
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Adatok tárolása
szolgalatok = {}
szolgalati_idok = {}
aktiv_szolgalat_kezdete = {}

# Tulajdonos ID
bot_owner_id = 1125866681860894780

@bot.event
async def on_ready():
    GUILD_ID = 1379472816008593650
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f'✅ Bejelentkezve mint {bot.user}, slash parancsok szinkronizálva.')

@bot.tree.command(name="szolgálat", description="Szolgálat felvétel vagy leadás")
@app_commands.describe(művelet="felvétel vagy leadás")
async def szolgálat(interaction: discord.Interaction, művelet: str):
    user_id = interaction.user.id
    now = time.time()

    if művelet.lower() == "felvétel":
        if user_id in aktiv_szolgalat_kezdete:
            await interaction.response.send_message("❗ Már szolgálatban vagy!", ephemeral=True)
            return
        aktiv_szolgalat_kezdete[user_id] = now
        await interaction.response.send_message(f"✅ {interaction.user.mention} szolgálatba lépett.")
    elif művelet.lower() == "leadás":
        if user_id not in aktiv_szolgalat_kezdete:
            await interaction.response.send_message("❗ Nem vagy szolgálatban!", ephemeral=True)
            return
        kezdes = aktiv_szolgalat_kezdete.pop(user_id)
        eltelt = now - kezdes
        szolgalati_idok[user_id] = szolgalati_idok.get(user_id, 0) + eltelt
        await interaction.response.send_message(f"✅ {interaction.user.mention} szolgálatot leadta. Eltöltött idő: {int(eltelt)} másodperc.")
    else:
        await interaction.response.send_message("⚠️ Érvénytelen művelet. Használat: felvétel vagy leadás.", ephemeral=True)

@szolgálat.autocomplete("művelet")
async def autocomplete_művelet(interaction: discord.Interaction, current: str):
    choices = [
        app_commands.Choice(name="felvétel", value="felvétel"),
        app_commands.Choice(name="leadás", value="leadás")
    ]
    return [choice for choice in choices if choice.name.startswith(current.lower())]

@bot.tree.command(name="szolgálat_leaderboard", description="Leaderboard megtekintése")
async def szolgálat_leaderboard(interaction: discord.Interaction):
    if not szolgalati_idok:
        await interaction.response.send_message("📭 Még senki nem volt szolgálatban.")
        return

    sorted_users = sorted(szolgalati_idok.items(), key=lambda x: x[1], reverse=True)
    leaderboard = []
    for i, (user_id, seconds) in enumerate(sorted_users, start=1):
        perc = int(seconds // 60)
        mp = int(seconds % 60)
        leaderboard.append(f"{i}. <@{user_id}> - {perc} perc {mp} mp")

    await interaction.response.send_message("🏆 Szolgálati leaderboard:\n" + "\n".join(leaderboard))

@bot.tree.command(name="újraindít", description="Bot újraindítása (csak tulajnak)")
async def ujraindit(interaction: discord.Interaction):
    if interaction.user.id != bot_owner_id:
        await interaction.response.send_message("🚫 Nincs jogosultságod újraindítani a botot.", ephemeral=True)
        return

    await interaction.response.send_message("🔁 Újraindítás...", ephemeral=True)
    await bot.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Bot indítása
bot.run(BOT_TOKEN)
