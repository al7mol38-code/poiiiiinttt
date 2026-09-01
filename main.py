import os
import re
import aiosqlite
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

# مسار حفظ قاعدة البيانات
DB_NAME = "points.db"

# =========================
# إعداد البوت
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="=", intents=intents, help_command=None)

# =========================
# التعامل مع قاعدة البيانات (SQLite)
# =========================
async def init_db():
    """إنشاء الجدول تلقائياً عند تشغيل البوت"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS points_bot1 (
                user_id TEXT PRIMARY KEY,
                points INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def get_points(user_id: int) -> int:
    """جلب نقاط المستخدم"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT points FROM points_bot1 WHERE user_id = ?", (str(user_id),)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def set_points(user_id: int, points: int):
    """إضافة أو تحديث نقاط المستخدم"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO points_bot1 (user_id, points)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET points = excluded.points
        """, (str(user_id), points))
        await db.commit()

# =========================
# الدوال المساعدة للصلاحيات
# =========================
def has_points_permission(member: discord.Member) -> bool:
    return any(role.id in ALLOWED_ROLE_IDS for role in member.roles)

def has_reset_permission(member: discord.Member) -> bool:
    return any(role.id in RESET_ALLOWED_ROLE_IDS for role in member.roles)

# =========================
# أحداث البوت
# =========================
@bot.event
async def on_ready():
    await init_db()  # تجهيز قاعدة البيانات
    print(f"✅ تم تشغيل البوت بنجاح باسم: {bot.user}")

@bot.event
async def on_message(message: discord.Message):
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

        # منع التعامل مع البوتات
        if target_member.bot and (content == "نقاط" or re.search(r"^نقاط\s*[\+\-]\d+$", content)):
            await message.channel.send("❌ لا يمكنك التعامل مع البوتات!")
            return

        # عرض النقاط بالرد
        if content == "نقاط":
            user_pts = await get_points(target_member.id)
            embed = discord.Embed(
                description=f"⭐ نقاط {target_member.mention}: **{user_pts}**",
                color=discord.Color.blue()
            )
            await message.reply(embed=embed, mention_author=False)
            return

        # إضافة / خصم نقاط بالرد
        match = re.search(r"^نقاط\s*([\+\-]\d+)$", content)
        if match:
            if not has_points_permission(message.author):
                await message.reply("❌ ليس لديك صلاحية لتعديل النقاط.", mention_author=False)
                return

            amount = int(match.group(1))
            current_pts = await get_points(target_member.id)
            new_pts = max(0, current_pts + amount)
            await set_points(target_member.id, new_pts)

            color = discord.Color.green() if amount >= 0 else discord.Color.red()
            action_text = f"إضافة **{amount}**" if amount >= 0 else f"خصم **{abs(amount)}**"

            embed = discord.Embed(
                title="✨ تحديث النقاط",
                description=f"✅ تم {action_text} نقطة لـ {target_member.mention}\n⭐ المجموع الحالي: **{new_pts}**",
                color=color
            )
            await message.reply(embed=embed, mention_author=False)
            return

    # معالجة الأوامر الرسمية
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
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, points FROM points_bot1 ORDER BY points DESC LIMIT 10") as cursor:
            users = await cursor.fetchall()

    if not users:
        await ctx.send("📭 لا توجد نقاط مسجلة.")
        return

    description = ""
    for index, (user_id, points) in enumerate(users, start=1):
        member = ctx.guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"**{index}.**"
        description += f"{medal} {name} — ⭐ **{points}** نقطة\n"

    embed = discord.Embed(title="🏆 قائمة المتصدرين", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command(name="تصفير", aliases=["ريست", "reset"])
async def reset_points(ctx, member: discord.Member = None):
    if not has_reset_permission(ctx.author):
        await ctx.send("❌ ليس لديك صلاحية لإجراء التصفير.")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        if member:
            await set_points(member.id, 0)
            await ctx.send(f"🔄 تم تصفير نقاط {member.mention} بنجاح!")
        else:
            await db.execute("DELETE FROM points_bot1")
            await db.commit()
            await ctx.send("⚠️ **تم تصفير جميع النقاط بنجاح!**")

# =========================
# تشغيل البوت
# =========================
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ لم يتم العثور على DISCORD_TOKEN في البيئة!")
