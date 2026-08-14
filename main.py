import os
import re
import threading
from flask import Flask
from pymongo import MongoClient
import discord
from discord.ext import commands

# =========================
# إعداد الروم المخصص للبوت الثاني
# =========================
# ضع هنا ID الروم الخاص بالبوت الثاني فقط
ALLOWED_CHANNEL_ID = 123456789012345678  

# =========================
# إعدادات الرتب المسموح لها
# =========================

OWNER_ROLE_ID = 1533463569683845160
CO_OWNER_ROLE_ID = 1533463570564649121
NEW_ROLE_ID = 1533463593201307780

ALLOWED_ROLE_IDS = {
    OWNER_ROLE_ID,
    CO_OWNER_ROLE_ID,
    NEW_ROLE_ID
}

# =========================
# MongoDB (مستقل للبوت الثاني)
# =========================

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["pointsbot"]
# تم تغيير اسم الكولكشن إلى points_bot2 لفصل البيانات والليدربورد
points_collection = db["points_bot2"]

# =========================
# إعداد البوت
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="=",
    intents=intents,
    help_command=None
)

# =========================
# تقييد البوت بروم محدد للأوامر الرسمية
# =========================

@bot.check
async def restrict_channel(ctx):
    return ctx.channel.id == ALLOWED_CHANNEL_ID

# =========================
# الدوال المساعدة
# =========================

def has_points_permission(member):
    return any(role.id in ALLOWED_ROLE_IDS for role in member.roles)

def get_points(user_id):
    user = points_collection.find_one({"_id": str(user_id)})
    return user["points"] if user else 0

def set_points(user_id, points):
    points_collection.update_one(
        {"_id": str(user_id)},
        {"$set": {"points": points}},
        upsert=True
    )

# =========================
# أحداث البوت (Events)
# =========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Bot is Ready and Flying! 🚀")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # يتجاهل الرسائل إذا لم تكن في الروم المخصص للبوت الثاني
    if message.channel.id != ALLOWED_CHANNEL_ID:
        return

    await bot.process_commands(message)

    content = message.content.strip()

    if message.reference and content.startswith("نقاط"):
        try:
            referenced_msg = await message.channel.fetch_message(message.reference.message_id)
            target_member = referenced_msg.author
        except Exception:
            return

        if target_member.bot:
            await message.channel.send("❌ لا يمكنك إضافة أو خصم نقاط من البوتات!")
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

        # إضافة أو خصم بالرد
        match = re.search(r"^نقاط\s*([\+\-]\d+)$", content)
        if match:
            if not has_points_permission(message.author):
                await message.reply("❌ ليس لديك صلاحية لتعديل النقاط.", mention_author=False)
                return

            amount = int(match.group(1))
            current = get_points(target_member.id)
            current += amount

            if current < 0:
                current = 0

            set_points(target_member.id, current)

            if amount >= 0:
                embed = discord.Embed(
                    title="✨ إضافة نقاط",
                    description=f"✅ تمت إضافة **{amount}** نقطة إلى {target_member.mention}\n⭐ المجموع الحالي: **{current}**",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="🔻 خصم نقاط",
                    description=f"✅ تم خصم **{abs(amount)}** نقطة من {target_member.mention}\n⭐ المجموع الحالي: **{current}**",
                    color=discord.Color.red()
                )

            await message.reply(embed=embed, mention_author=False)

# =========================
# الأوامر الرسمية
# =========================

@bot.command(name="مساعدة")
async def help_command(ctx):
    embed = discord.Embed(
        title="📋 طريقة استخدام بوت النقاط",
        description=(
            "**بالرد على رسالة العضو (Reply):**\n"
            "• `نقاط+4` ➜ إضافة 4 نقاط للعضو\n"
            "• `نقاط-2` ➜ خصم نقطتين من العضو\n"
            "• `نقاط` ➜ عرض نقاط العضو المردود عليه\n\n"
            "**الأوامر العامة:**\n"
            "• `=توب` ➜ قائمة أفضل 10 أعضاء"
        ),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name="توب")
async def top(ctx):
    users = list(points_collection.find().sort("points", -1).limit(10))

    if not users:
        await ctx.send("📭 لا توجد نقاط مسجلة حتى الآن.")
        return

    description = ""
    for index, user in enumerate(users, start=1):
        member = ctx.guild.get_member(int(user["_id"]))
        name = member.display_name if member else f"<@{user['_id']}>"
        
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"**{index}.**"
        description += f"{medal} {name} — ⭐ **{user['points']}** نقطة\n"

    embed = discord.Embed(
        title="🏆 قائمة المتصدرين (TOP 10)",
        description=description,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"طلب بواسطة {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

# =========================
# Flask (Keep Alive)
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Points Bot is Online & Ready!"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================
# التشغيل
# =========================

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN غير موجود")

    bot.run(token)
