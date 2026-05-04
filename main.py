import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
import logging
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("TOKEN")

OWNER_ID = 994603323615350915
LOG_CHANNEL_ID = 1416752491067867166
LEADERBOARD_CHANNEL_ID = 1381604394516353095
PROMO_LOG_CHANNEL = 1401609279051534396
LOA_ROLE_ID = 1496172962246561792

RECRUIT_ROLE_IDS = [1369906712131141722, 1444285199696396403]
RECRUITER_ROLE_ID = 1444285199696396403

UP_EMOJI = "⬆️"
DOWN_EMOJI = "⬇️"

RANKS = [
    (10, 1369906710084587551, "Sword"),
    (25, 1406646864941416489, "Head Sword"),
    (40, 1414471156173635595, "Glaciers"),
    (60, 1414240501187739648, "War Tank"),
    (80, 1369906695303860225, "Captain"),
    (100, 1406906194446258196, "War Carries"),
    (125, 1414650155432677498, "Admin"),
    (150, 1414649982644125728, "Officer"),
    (175, 1444310584475516948, "Commander"),
    (200, 1487489699265253518, "War Specialist")
]

# =========================
# BOT SETUP
# =========================

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# =========================
# KEEP ALIVE (RENDER)
# =========================

app = Flask('')

@app.route('/')
def home():
    return "Bot running"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# =========================
# JSON FILES
# =========================

FILES = {
    "data.json": {"recruiters": {}, "users": {}, "msg_id": None},
    "loa.json": {},
    "whitelist.json": [],
    "points.json": {"points": {}, "history": {}}
}

def load_file(name):
    if not os.path.exists(name):
        with open(name, "w") as f:
            json.dump(FILES[name], f)

    try:
        with open(name) as f:
            return json.load(f)
    except:
        return FILES[name]

data = load_file("data.json")
loa_data = load_file("loa.json")
whitelist = set(load_file("whitelist.json"))
points_data = load_file("points.json")

def save_all():
    with open("data.json", "w") as f:
        json.dump(data, f)

    with open("loa.json", "w") as f:
        json.dump(loa_data, f)

    with open("whitelist.json", "w") as f:
        json.dump(list(whitelist), f)

    with open("points.json", "w") as f:
        json.dump(points_data, f)

# =========================
# HELPERS
# =========================

def is_admin():
    async def pred(ctx):
        return ctx.author.id == OWNER_ID or ctx.author.id in whitelist
    return commands.check(pred)

def embed_success(msg):
    return discord.Embed(description=f"✅ {msg}", color=0x2ecc71)

def embed_error(msg):
    return discord.Embed(description=f"❌ {msg}", color=0xe74c3c)

def embed_info(msg):
    return discord.Embed(description=f"📌 {msg}", color=0x3498db)

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not loa_check.is_running():
        loa_check.start()

# =========================
# RECRUIT
# =========================

@bot.command()
async def recruit(ctx, member: discord.Member):
    if RECRUITER_ROLE_ID not in [r.id for r in ctx.author.roles]:
        return await ctx.send(embed=embed_error("No permission."))

    if str(member.id) in data["users"]:
        return await ctx.send(embed=embed_error("Already recruited."))

    for rid in RECRUIT_ROLE_IDS:
        role = ctx.guild.get_role(rid)
        if role:
            await member.add_roles(role)

    data["users"][str(member.id)] = str(ctx.author.id)
    data["recruiters"][str(ctx.author.id)] = data["recruiters"].get(str(ctx.author.id), 0) + 1
    save_all()

    await ctx.send(embed=embed_success("Recruit successful."))

# =========================
# DMALL
# =========================

@bot.command()
@is_admin()
async def dmall(ctx, role: discord.Role, *, message):
    users = [m for m in role.members if not m.bot]

    if not users:
        return await ctx.send(embed=embed_error("No members found."))

    progress = await ctx.send(embed=embed_info(f"Sending...\n0/{len(users)}"))

    for i, member in enumerate(users, 1):
        try:
            await member.send(message)
        except:
            pass

        await progress.edit(embed=embed_info(f"Sending...\n{i}/{len(users)}"))
        await asyncio.sleep(1.5)

    await progress.edit(embed=embed_success("DMALL completed."))

# =========================
# LOA SYSTEM
# =========================

@bot.command()
@is_admin()
async def loa(ctx, member: discord.Member, duration: str):
    unit = duration[-1]
    val = int(duration[:-1])

    delta = {
        "m": timedelta(minutes=val),
        "h": timedelta(hours=val),
        "d": timedelta(days=val),
        "w": timedelta(weeks=val)
    }.get(unit)

    if not delta:
        return await ctx.send(embed=embed_error("Use m/h/d/w"))

    loa_data[str(member.id)] = (datetime.utcnow() + delta).isoformat()

    role = ctx.guild.get_role(LOA_ROLE_ID)
    if role:
        await member.add_roles(role)

    save_all()
    await ctx.send(embed=embed_success("LOA set."))

@tasks.loop(minutes=1)
async def loa_check():
    now = datetime.utcnow()
    remove = []

    for uid, t in list(loa_data.items()):
        if datetime.fromisoformat(t) <= now:
            remove.append(uid)

    for uid in remove:
        for guild in bot.guilds:
            member = guild.get_member(int(uid))
            role = guild.get_role(LOA_ROLE_ID)

            if member and role:
                try:
                    await member.remove_roles(role)
                except:
                    pass

        loa_data.pop(uid, None)

    if remove:
        save_all()

# =========================
# POINTS SYSTEM
# =========================

async def update_rank(member):
    uid = str(member.id)
    pts = points_data["points"].get(uid, 0)

    selected = None
    for req, rid, name in RANKS:
        if pts >= req:
            selected = (rid, name)

    for _, rid, _ in RANKS:
        role = member.guild.get_role(rid)
        if role and role in member.roles:
            await member.remove_roles(role)

    if selected:
        role = member.guild.get_role(selected[0])
        if role:
            await member.add_roles(role)

@bot.group(invoke_without_command=True)
async def p(ctx, member: discord.Member = None):
    member = member or ctx.author
    pts = points_data["points"].get(str(member.id), 0)
    await ctx.send(embed=embed_info(f"{member.mention} has {pts} points."))

@p.command()
@is_admin()
async def give(ctx, member: discord.Member, amount: int):
    uid = str(member.id)
    points_data["points"][uid] = points_data["points"].get(uid, 0) + amount
    await update_rank(member)
    save_all()
    await ctx.send(embed=embed_success("Points added."))

# =========================
# START
# =========================

bot.run(TOKEN)