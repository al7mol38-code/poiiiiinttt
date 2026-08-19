import os
import re
import time
import threading
from flask import Flask
from pymongo import MongoClient
import discord
from discord.ext import commands

# =========================
# إعدادات الرتب
# =========================
OWNER_ROLE_ID = 1533463569683845160
CO_OWNER_ROLE_ID = 1533463570564649121
NEW_ROLE_ID = 1533463593201307780

ALLOWED_ROLE_IDS = {OWNER_ROLE_ID, CO_OWNER_ROLE_ID, NEW_ROLE_ID}
RESET_ALLOWED_ROLE_IDS = {CO_OWNER_ROLE_ID, OWNER_ROLE_ID}

# =========================
# MongoDB
# =========================
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(
    MONGO_URI,
    connectTimeoutMS=30000,
    socketTimeoutMS=30000,
    serverSelectionTimeoutMS=30000,
    retryWrites=True
)

db = client["pointsbot"]
points_collection = db["points_bot1"]

# =========================
# إعداد البوت
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="=", intents=intents, help_command=None)

# =========================
# الدوال المساعدة
# =========================
def has_points_permission(member):
    return any(role.id in ALLOWED_ROLE_IDS for role in member.roles)

def has_reset_permission(member):
    return any(role.id in RESET_ALLOWED_ROLE_IDS for role in member.roles)

def get_points(user_id):
    try:
        user = points_collection.find_one({"_id": str(user_id)})
        return user["points"] if user else 0
    except Exception as e:
        print(f"MongoDB Error: {e}")
        return 0

def set_points(user_id, points):
    try:
        points_collection.update_one(
            {"_id": str(user_id)},
            {"$set": {"points": points}},
            upsert=True
        )
    except Exception as e:
        print(f"MongoDB Update Error: {e}")

# =========================
# أحداث البوت
# =========================
@bot.event
async def on_ready():
    print(f"Bot 1 Logged in as: {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    # العمليات بواسطة الرد (Reply)
    if message.reference:
        try:
            referenced_msg = await message.channel.fetch_message(message.reference.message_id)
            target_member = referenced_msg.author
        except Exception:
            await bot.process_commands(message)
            return

        # منع التعامل مع البوتات إذا كانت الرسالة تخص النقاط
        if target_member.bot and (content == "نقاط" or re.search(r"^نقاط\s*[\+\-]\d+$", content)):
            await message.channel.send("❌ لا يمكنك التعامل مع البوتات!")
            return

        # عرض النقاط بالرد
        if content == "نقاط":
            user_pts = get_points(target_member.id)
            embed = discord.Embed(
                description=f"⭐ نقاط {target_member.mention}: **{user_pts}**",
                color=discord.Color.blue()
            )
            await message.reply(embed=embed, mention_author=False)
            return

        # إضافة / خصم بالرد
        match = re.search(r"^نقاط\s*([\+\-]\d+)$", content)
        if match:
            if not has_points_permission(message.author):
                await message.reply("❌ ليس لديك صلاحية لتعديل النقاط.", mention_author=False)
                return

            amount = int(match.group(1))
            current = max(0, get_points(target_member.id) + amount)
            set_points(target_member.id, current)

            color = discord.Color.green() if amount >= 0 else discord.Color.red()
            action_text = f"إضافة **{amount}**" if amount >= 0 else f"خصم **{abs(amount)}**"
            
            embed = discord.Embed(
                title="✨ تحديث النقاط",
                description=f"✅ تم {action_text} نقطة لـ {target_member.mention}\n⭐ المجموع الحالي: **{current}**",
                color=color
            )
            await message.reply(embed=embed, mention_author=False)
            return

    # معالجة باقي الأوامر الرسمية مثل (=توب، =تصفير، الخ)
    await bot.process_commands(message)

# =========================
# الأوامر الرسمية
# =========================
@bot.command(name="مساعدة")
async def help_command(ctx):
    embed = discord.Embed(
        title="📋 قائمة الأوامر",
        description=(
            "**بالرد على العضو:**\n"
            "• `نقاط` ➜ عرض النقاط\n"
            "• `نقاط+5` ➜ إضافة نقاط\n"
            "• `نقاط-2` ➜ خصم نقاط\n\n"
            "**الأوامر العامة:**\n"
            "• `=توب` ➜ قائمة أفضل 10 أعضاء\n"
            "• `=تصفير` ➜ تصفير جميع النقاط\n"
            "• `=تصفير @العضو` ➜ تصفير نقاط عضو معين"
        ),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name="توب")
async def top(ctx):
    try:
        users = list(points_collection.find().sort("points", -1).limit(10))
    except Exception as e:
        await ctx.send("❌ حدث خطأ أثناء جلب قائمة المتصدرين.")
        print(f"Top Command Error: {e}")
        return

    if not users:
        await ctx.send("📭 لا توجد نقاط مسجلة.")
        return

    description = ""
    for index, user in enumerate(users, start=1):
        member = ctx.guild.get_member(int(user["_id"]))
        name = member.display_name if member else f"<@{user['_id']}>"
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"**{index}.**"
        description += f"{medal} {name} — ⭐ **{user['points']}** نقطة\n"

    embed = discord.Embed(title="🏆 قائمة المتصدرين", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command(name="تصفير", aliases=["ريست", "reset"])
async def reset_points(ctx, member: discord.Member = None):
    if not has_reset_permission(ctx.author):
        await ctx.send("❌ ليس لديك صلاحية لإجراء التصفير.")
        return

    if member:
        set_points(member.id, 0)
        await ctx.send(f"🔄 تم تصفير نقاط {member.mention} بنجاح!")
    else:
        try:
            points_collection.delete_many({})
            await ctx.send("⚠️ **تم تصفير جميع النقاط بنجاح!**")
        except Exception as e:
            await ctx.send("❌ حدث خطأ أثناء تصفير قاعدة البيانات.")
            print(f"Reset Error: {e}")

# =========================
# Flask (Keep Alive)
# =========================
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot 1 Online"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================
# نقطة التشغيل
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    
    # مهلة لتفادي حظر التكرار مع Cloudflare
    time.sleep(5)
    
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ لم يتم العثور على DISCORD_TOKEN في البيئة!")
