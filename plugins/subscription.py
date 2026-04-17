from pyrogram import Client, filters, enums
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_subscription, set_subscription, update_user_task, send_log_api, get_db
from config import OWNER_ID, FORCE_CHANNEL_ID
import time
import datetime
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# PLAN DEFINITIONS — Update prices/limits here
# ═══════════════════════════════════════════
PLANS = {
    "trial": {
        "name": "🎁 Trial Plan",
        "emoji": "🎁",
        "price": "FREE",
        "task_limit": 1,
        "forward_limit": 20000,   # Fast copy/forward method limit
        "dl_limit": 5000,         # Download+Upload (restricted) method limit
        "duration": 86400,        # 24 hours
        "live_monitor_limit": 0,
        "one_time": True,         # Only once per user ever
        "color": "🟢",
        "badge": "FREE TRIAL",
    },
    "daily_39": {
        "name": "⚡ Daily Pass",
        "emoji": "⚡",
        "price": "₹39",
        "task_limit": 5,
        "forward_limit": 100000,
        "dl_limit": 19999,
        "duration": 86400,        # 1 day
        "live_monitor_limit": 2,
        "one_time": False,
        "color": "🔵",
        "badge": "POPULAR",
    },
    "monthly_259": {
        "name": "💎 Monthly Pro",
        "emoji": "💎",
        "price": "₹259",
        "task_limit": 50,
        "forward_limit": 1000000,
        "dl_limit": 200000,
        "duration": 2592000,      # 30 days
        "live_monitor_limit": 5,
        "one_time": False,
        "color": "🟣",
        "badge": "BEST VALUE",
    },
    "ultra_389": {
        "name": "🚀 Ultra Pass",
        "emoji": "🚀",
        "price": "₹389",
        "task_limit": float('inf'),
        "forward_limit": float('inf'),
        "dl_limit": 1000000,
        "duration": 259200,       # 3 days
        "live_monitor_limit": 15,
        "one_time": False,
        "color": "🟠",
        "badge": "POWER USER",
    },
    "lifetime_2999": {
        "name": "♾️ Lifetime",
        "emoji": "♾️",
        "price": "₹2999",
        "task_limit": float('inf'),
        "forward_limit": float('inf'),
        "dl_limit": float('inf'),
        "duration": 0,            # Never expires
        "live_monitor_limit": 30,
        "one_time": False,
        "color": "🔴",
        "badge": "ULTIMATE",
    },
}

# Legacy plan key mapping for backward compatibility
LEGACY_PLAN_MAP = {
    "free": "trial",
    "day_19": "daily_39",
    "month_199": "monthly_259",
    "unlimited_299": "ultra_389",
}

def fmt_limit(val):
    if val == float('inf'): return "**UNLIMITED ∞**"
    return f"`{val:,}`"

def fmt_tasks(val):
    if val == float('inf'): return "**Unlimited ∞**"
    return f"`{val}`"

# ═══════════════════════════════════════════
# DATABASE HELPERS FOR TRIAL
# ═══════════════════════════════════════════
async def has_used_trial(user_id: int) -> bool:
    database = await get_db()
    rec = await database.trial_used.find_one({"_id": user_id})
    return rec is not None

async def mark_trial_used(user_id: int):
    database = await get_db()
    await database.trial_used.update_one({"_id": user_id}, {"$set": {"used": True}}, upsert=True)

# ═══════════════════════════════════════════
# FORCE SUBSCRIBE CHECK
# ═══════════════════════════════════════════
async def check_force_sub(client, message):
    user_id = message.from_user.id
    if user_id == int(OWNER_ID):
        return True
    INVITE_LINK = "https://t.me/Univora88"
    try:
        member = await client.get_chat_member(FORCE_CHANNEL_ID, user_id)
        VALID = [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
        if member.status in VALID:
            return True
        else:
            raise UserNotParticipant
    except UserNotParticipant:
        await message.reply_text(
            "⚠️ **Access Verification Required**\n\n"
            "To use **ExtractX**, you must join our official channel.\n"
            "1. Join the channel below.\n"
            "2. Click **Check Access** to proceed.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Official Channel", url=INVITE_LINK)],
                [InlineKeyboardButton("🔄 Check Access", url=f"https://t.me/{client.me.username}?start=check")]
            ])
        )
        return False
    except Exception as e:
        logger.warning(f"Force sub check error for {user_id}: {e}")
        return True

# ═══════════════════════════════════════════
# ACCESS CHECK ENGINE
# ═══════════════════════════════════════════
async def check_user_access(user_id):
    """
    Returns: (is_allowed, reason_message, forward_limit, tasks_remaining)
    forward_limit = fast copy limit (the main file_limit used everywhere)
    """
    if user_id == int(OWNER_ID):
        return True, "Owner Access", float('inf'), "Unlimited"

    sub = await get_subscription(user_id)
    if not sub:
        plan_key = "trial"
        expiry = 0
        tasks = 0
    else:
        plan_key = sub.get("plan_type", "trial")
        # Migrate legacy keys
        plan_key = LEGACY_PLAN_MAP.get(plan_key, plan_key)
        if plan_key not in PLANS:
            plan_key = "trial"
        expiry = sub.get("expiry_date", 0)
        tasks = sub.get("tasks_done", 0)

    now = time.time()

    # Expiry check (skip for trial and lifetime)
    plan = PLANS[plan_key]
    if plan_key not in ("trial", "lifetime_2999") and expiry > 0 and now > expiry:
        await set_subscription(user_id, "trial", 0)
        plan_key = "trial"
        plan = PLANS["trial"]
        tasks = 0

    task_limit = plan["task_limit"]
    forward_limit = plan["forward_limit"]

    if task_limit != float('inf') and tasks >= task_limit:
        return False, (
            f"⚠️ **Task Limit Reached!**\n\n"
            f"Your **{plan['name']}** allows `{task_limit}` tasks.\n"
            f"You've used all of them.\n\n"
            f"📲 Use /showplan to upgrade!"
        ), forward_limit, 0

    remaining = (task_limit - tasks) if task_limit != float('inf') else "Unlimited"
    return True, "Access Granted", forward_limit, remaining

async def record_task_use(user_id):
    if user_id == int(OWNER_ID): return
    await update_user_task(user_id, 1)

# ═══════════════════════════════════════════
# PLAN UI BUILDERS
# ═══════════════════════════════════════════
def build_status_card(first_name, user_id, plan_key, plan, tasks_done, expiry):
    task_limit = plan["task_limit"]
    fwd_limit = plan["forward_limit"]
    dl_limit = plan["dl_limit"]
    live_limit = plan["live_monitor_limit"]

    tasks_str = f"{tasks_done}/{task_limit}" if task_limit != float('inf') else f"{tasks_done}/∞"
    fwd_str = f"{fwd_limit:,}" if fwd_limit != float('inf') else "Unlimited ∞"
    dl_str = f"{dl_limit:,}" if dl_limit != float('inf') else "Unlimited ∞"
    live_str = str(live_limit) if live_limit > 0 else "None"

    if expiry > 0:
        exp_dt = datetime.datetime.fromtimestamp(expiry)
        exp_str = exp_dt.strftime("%d %b %Y • %I:%M %p")
        remaining_secs = expiry - time.time()
        if remaining_secs > 0:
            remaining_days = int(remaining_secs // 86400)
            remaining_hrs = int((remaining_secs % 86400) // 3600)
            time_left = f"{remaining_days}d {remaining_hrs}h remaining"
        else:
            time_left = "Expired"
    elif plan_key == "lifetime_2999":
        exp_str = "Never Expires ♾️"
        time_left = "Forever"
    elif plan_key == "trial":
        exp_str = "24h from first use"
        time_left = "Single use"
    else:
        exp_str = "Lifetime"
        time_left = "Forever"

    text = (
        f"╔══════════════════════╗\n"
        f"║   📊 YOUR PLAN STATUS   ║\n"
        f"╚══════════════════════╝\n\n"
        f"👤 **{first_name}** • `{user_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{plan['color']} **Active Plan:** {plan['name']}\n"
        f"💰 **Price:** `{plan['price']}`\n"
        f"🏷️ **Badge:** `{plan['badge']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **Usage Stats:**\n"
        f"  ⚡ Tasks Used: `{tasks_str}`\n"
        f"  🔗 Fast Copy Limit: `{fwd_str}` files\n"
        f"  📦 DL+Upload Limit: `{dl_str}` files\n"
        f"  📡 Live Monitors: `{live_str}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ **Validity:** `{exp_str}`\n"
        f"🕐 **Time Left:** `{time_left}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⬇️ **Tap a plan below to see full details & upgrade:**"
    )
    return text

def build_plan_keyboard(show_trial_btn=True):
    buttons = []
    if show_trial_btn:
        buttons.append([InlineKeyboardButton("🎁 Trial Plan — FREE", callback_data="plan_info:trial")])
    buttons.append([
        InlineKeyboardButton("⚡ Daily — ₹39", callback_data="plan_info:daily_39"),
        InlineKeyboardButton("💎 Monthly — ₹259", callback_data="plan_info:monthly_259"),
    ])
    buttons.append([
        InlineKeyboardButton("🚀 Ultra — ₹389", callback_data="plan_info:ultra_389"),
        InlineKeyboardButton("♾️ Lifetime — ₹2999", callback_data="plan_info:lifetime_2999"),
    ])
    buttons.append([InlineKeyboardButton("📲 Contact Admin to Buy", url="https://t.me/Univora_Support")])
    return InlineKeyboardMarkup(buttons)

def build_plan_detail(plan_key):
    plan = PLANS[plan_key]
    fwd = fmt_limit(plan['forward_limit'])
    dl = fmt_limit(plan['dl_limit'])
    tasks = fmt_tasks(plan['task_limit'])
    live = str(plan['live_monitor_limit']) if plan['live_monitor_limit'] > 0 else "Not Available"

    if plan['duration'] == 0:
        validity = "**Lifetime — Never Expires ♾️**"
    elif plan['duration'] == 86400:
        validity = "**24 Hours**"
    elif plan['duration'] == 259200:
        validity = "**3 Days**"
    elif plan['duration'] == 2592000:
        validity = "**30 Days**"
    else:
        validity = f"{int(plan['duration']//86400)} Days"

    trial_note = "\n⚠️ _Only 1 trial per account (ever)_" if plan.get("one_time") else ""

    text = (
        f"╔══════════════════════╗\n"
        f"║  {plan['emoji']}  {plan['name'].upper()}  ║\n"
        f"╚══════════════════════╝\n\n"
        f"💰 **Price:** `{plan['price']}`\n"
        f"⏳ **Validity:** {validity}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **Plan Features:**\n\n"
        f"  🔢 **Total Tasks:** {tasks}\n"
        f"  🔗 **Fast Copy Limit:** {fwd} files\n"
        f"     _(For channels with forwarding ON)_\n"
        f"  📦 **DL+Upload Limit:** {dl} files\n"
        f"     _(For restricted channels)_\n"
        f"  📡 **Live Monitors:** `{live}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ **What's Included:**\n"
        f"  • Bypass all private channel restrictions\n"
        f"  • Smart filters (Video/Doc/Photo/Audio)\n"
        f"  • Caption Editor & Word Replace\n"
        f"  • Custom Thumbnail Override\n"
        f"  • Multi-destination forwarding\n"
        f"  • Blazing-fast server-side copy{trial_note}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📲 **To activate, contact admin below!**"
    )
    return text

# ═══════════════════════════════════════════
# /showplan COMMAND
# ═══════════════════════════════════════════
@Client.on_message(filters.command("showplan") | filters.command("myplan") | filters.command("plan"))
async def show_plan(client, message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    # Owner special card
    if user_id == int(OWNER_ID):
        text = (
            "╔══════════════════════╗\n"
            "║  👑  OWNER GOD MODE  👑  ║\n"
            "╚══════════════════════╝\n\n"
            f"👤 **{first_name}** • `{user_id}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔴 **Plan:** `God Mode — Unlimited`\n"
            "⚡ **Tasks:** `∞ Unlimited`\n"
            "🔗 **Fast Copy:** `∞ Unlimited`\n"
            "📦 **DL+Upload:** `∞ Unlimited`\n"
            "📡 **Live Monitors:** `∞ Unlimited`\n"
            "⏳ **Validity:** `Forever`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ _You have complete control over ExtractX._"
        )
        await message.reply_text(text)
        return

    # Get subscription
    sub = await get_subscription(user_id)
    if not sub:
        plan_key = "trial"
        expiry = 0
        tasks_done = 0
    else:
        plan_key = sub.get("plan_type", "trial")
        plan_key = LEGACY_PLAN_MAP.get(plan_key, plan_key)
        if plan_key not in PLANS:
            plan_key = "trial"
        expiry = sub.get("expiry_date", 0)
        tasks_done = sub.get("tasks_done", 0)

        # Normalize expired plans
        if plan_key not in ("trial", "lifetime_2999") and expiry > 0 and time.time() > expiry:
            plan_key = "trial"
            expiry = 0

    plan = PLANS[plan_key]

    # Check if trial already used
    trial_available = not await has_used_trial(user_id) if plan_key != "trial" else True

    text = build_status_card(first_name, user_id, plan_key, plan, tasks_done, expiry)
    kb = build_plan_keyboard(show_trial_btn=trial_available)

    await message.reply_text(text, reply_markup=kb)

    # Silent log
    try:
        await send_log_api(
            f"💳 **PLAN CHECKED**\n\n"
            f"👤 [{first_name}](tg://user?id={user_id})\n"
            f"🆔 `{user_id}`\n"
            f"💎 **Plan:** `{plan['name']}`\n"
            f"📊 **Tasks Used:** `{tasks_done}`"
        )
    except: pass

# ═══════════════════════════════════════════
# PLAN DETAIL CALLBACK
# ═══════════════════════════════════════════
@Client.on_callback_query(filters.regex(r"^plan_info:(.+)$"))
async def plan_info_callback(client, callback):
    plan_key = callback.data.split(":")[1]
    if plan_key not in PLANS:
        await callback.answer("Invalid plan!", show_alert=True)
        return

    text = build_plan_detail(plan_key)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 Contact Admin to Buy", url="https://t.me/Univora_Support")],
        [InlineKeyboardButton("⬅️ Back to Plans", callback_data="show_plans_back")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except:
        await callback.answer()

@Client.on_callback_query(filters.regex("^show_plans_back$"))
async def show_plans_back_callback(client, callback):
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "User"

    sub = await get_subscription(user_id)
    if not sub:
        plan_key = "trial"; expiry = 0; tasks_done = 0
    else:
        plan_key = LEGACY_PLAN_MAP.get(sub.get("plan_type", "trial"), sub.get("plan_type", "trial"))
        if plan_key not in PLANS: plan_key = "trial"
        expiry = sub.get("expiry_date", 0)
        tasks_done = sub.get("tasks_done", 0)
        if plan_key not in ("trial", "lifetime_2999") and expiry > 0 and time.time() > expiry:
            plan_key = "trial"; expiry = 0

    plan = PLANS[plan_key]
    trial_available = not await has_used_trial(user_id) if plan_key != "trial" else True
    text = build_status_card(first_name, user_id, plan_key, plan, tasks_done, expiry)
    kb = build_plan_keyboard(show_trial_btn=trial_available)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except:
        await callback.answer()

# ═══════════════════════════════════════════
# ADMIN COMMANDS
# ═══════════════════════════════════════════
@Client.on_message(filters.command("addpremium") & filters.user(int(OWNER_ID)))
async def add_premium(client, message):
    try:
        args = message.command
        plan_ids = list(PLANS.keys())
        plan_ids_str = "\n".join([f"`{k}` — {v['name']} ({v['price']})" for k in plan_ids if k != "trial"])
        if len(args) < 3:
            await message.reply_text(f"Usage: `/addpremium <user_id> <plan_id>`\n\n**Plans:**\n{plan_ids_str}")
            return

        target_id = int(args[1])
        plan_id = args[2].lower()
        # Support legacy keys
        plan_id = LEGACY_PLAN_MAP.get(plan_id, plan_id)

        if plan_id not in PLANS or plan_id == "trial":
            await message.reply_text("❌ Invalid Plan ID.")
            return

        duration = PLANS[plan_id]["duration"]
        expiry = time.time() + duration if duration > 0 else 0

        await set_subscription(target_id, plan_id, expiry)

        plan = PLANS[plan_id]
        exp_str = datetime.datetime.fromtimestamp(expiry).strftime("%d %b %Y %H:%M") if expiry > 0 else "Lifetime"
        await message.reply_text(
            f"✅ **Premium Activated!**\n\n"
            f"👤 User: `{target_id}`\n"
            f"{plan['emoji']} Plan: **{plan['name']}**\n"
            f"⏳ Expires: `{exp_str}`"
        )

        # Log
        try:
            await send_log_api(
                f"🎁 **PREMIUM GRANTED**\n\n"
                f"👤 **User ID:** `{target_id}`\n"
                f"💎 **Plan:** `{plan['name']}`\n"
                f"⏳ **Expires:** `{exp_str}`\n"
                f"👮 **By Admin:** `{message.from_user.id}`"
            )
        except: pass

        # Notify user
        try:
            await client.send_message(
                target_id,
                f"🎉 **Premium Activated!**\n\n"
                f"You've been upgraded to **{plan['name']}**!\n"
                f"⏳ Valid until: `{exp_str}`\n\n"
                f"Use /showplan to see your full limits.\n"
                f"⚡ _Powered by Univora_"
            )
        except: pass

    except Exception as e:
        await message.reply_text(f"Error: {e}")

@Client.on_message(filters.command("removepremium") & filters.user(int(OWNER_ID)))
async def remove_premium(client, message):
    try:
        args = message.command
        if len(args) < 2:
            await message.reply_text("Usage: `/removepremium <user_id>`")
            return
        target_id = int(args[1])
        await set_subscription(target_id, "trial", 0)
        await message.reply_text(f"✅ **Premium Removed.** User `{target_id}` is now on Trial Plan.")
        try:
            await send_log_api(
                f"🔻 **PREMIUM REVOKED**\n\n"
                f"👤 **User ID:** `{target_id}`\n"
                f"👮 **By Admin:** `{message.from_user.id}`"
            )
        except: pass
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@Client.on_message(filters.command("givetrial") & filters.user(int(OWNER_ID)))
async def give_trial(client, message):
    """Admin can grant trial to a user who already used it"""
    try:
        args = message.command
        if len(args) < 2:
            await message.reply_text("Usage: `/givetrial <user_id>`")
            return
        target_id = int(args[1])
        database = await get_db()
        await database.trial_used.delete_one({"_id": target_id})
        await set_subscription(target_id, "trial", time.time() + 86400)
        await message.reply_text(f"✅ Trial reset & granted to `{target_id}`.")
    except Exception as e:
        await message.reply_text(f"Error: {e}")
