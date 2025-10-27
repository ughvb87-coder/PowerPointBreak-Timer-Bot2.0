# PowerPointBreak × MinexxProo — All-in-One Telegram Bot (ClawCloud-ready)
# Features: Countdown + Giveaway (timed & instant) + Join verify + Approval + Owner Panel + Bot ON/OFF
# Token is read from environment variable BOT_TOKEN (do NOT hardcode).

import os
import json
import time
import random
import re
import threading
from typing import Dict, Any, Optional

import telebot
from telebot import types

# -------------- CONFIG (EDIT THESE IF NEEDED) --------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")  # <-- set this in ClawCloud Environment Variables

OWNER_ID = 5692210187               # @MinexxProo
CHANNEL_USERNAME = "@PowerPointBreak"
GROUP_USERNAME = "@PowerPointBreakConversion"

STATE_FILE = "state.json"
# -----------------------------------------------------------

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Please set environment variable BOT_TOKEN.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DEFAULT_POST = (
    "🎮💥 POWERPOINTBREAK MEGA GIVEAWAY 💥🎮\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🔥 15× EXPRESSVPN PREMIUM ACCOUNTS 🔥\n"
    "🕹️ Level: Legendary Edition\n"
    "🕓 Start Time: 8:30 PM (BD Time)\n"
    "⏳ Ending Soon – Stay Ready!\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💫 Rewards for Real Players Only 💫\n"
    "🎯 Click Below To Join the Mission 👇"
)

# In-memory runtime countdown trackers per chat
COUNTDOWNS: Dict[int, Dict[str, Any]] = {}

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        state = {
            "bot_status": "online",
            "approved_users": [],
            "approved_chats": [],
            "post_template": DEFAULT_POST,
            "participants": {}  # chat_id -> [{"id":..., "username":...}, ...]
        }
        save_state(state)
        return state
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state: Dict[str, Any]):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

STATE = load_state()

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_approved_user(user_id: int) -> bool:
    return user_id in STATE["approved_users"] or is_owner(user_id)

def is_approved_chat(chat_id: int) -> bool:
    return chat_id in STATE["approved_chats"]

def bot_online() -> bool:
    return STATE.get("bot_status", "online") == "online"

def parse_duration(text: str) -> int:
    h = m = s = 0
    mh = re.search(r"(\\d+)h", text)
    mm = re.search(r"(\\d+)m", text)
    ms = re.search(r"(\\d+)s", text)
    if mh: h = int(mh.group(1))
    if mm: m = int(mm.group(1))
    if ms: s = int(ms.group(1))
    return h*3600 + m*60 + s

def seconds_to_hms(secs: int):
    if secs < 0: secs = 0
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02}:{m:02}:{s:02}", h, m, s

def ensure_participants_chat(chat_id: int):
    if str(chat_id) not in STATE["participants"]:
        STATE["participants"][str(chat_id)] = []
        save_state(STATE)

def is_chat_admin(user_id: int, chat_id: int) -> bool:
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

def admin_or_owner(user_id: int, chat_id: Optional[int] = None) -> bool:
    if is_owner(user_id):
        return True
    if chat_id is not None:
        return is_chat_admin(user_id, chat_id)
    return False

def require_online(func):
    def wrapper(message, *args, **kwargs):
        if not bot_online() and not is_owner(message.from_user.id):
            bot.reply_to(message, "🚫 Bot is currently <b>OFFLINE</b>. Contact admin: @MinexxProo")
            return
        return func(message, *args, **kwargs)
    return wrapper

# ------------------- /start & Approval -------------------
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    if is_owner(message.from_user.id):
        bot.reply_to(message, "👑 Welcome Owner! Use /panel to open the Owner Dashboard.")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔗 Join @PowerPointBreak", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"))
    kb.add(types.InlineKeyboardButton("🚀 Send Access Request", callback_data=f"req_access:{message.from_user.id}"))
    bot.send_message(
        message.chat.id,
        ("👋 Welcome to PowerPointBreak System!\n"
         "To use this bot, you must get approval from the Owner.\n\n"
         f"Owner: @MinexxProo\nChannel: {CHANNEL_USERNAME}\n━━━━━━━━━━━━━━━━━━"),
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("req_access:"))
def cb_req_access(call: types.CallbackQuery):
    requester_id = int(call.data.split(":")[1])
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_user:{requester_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_user:{requester_id}")
    )
    uname = f"@{call.from_user.username}" if call.from_user.username else str(call.from_user.id)
    bot.send_message(OWNER_ID, f"🆕 <b>New Access Request</b>\nRequester: {uname} (ID: {requester_id})\nWants to use the bot in their own Channel/Group.", reply_markup=kb)
    bot.answer_callback_query(call.id, "✅ Request sent to Owner.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_user:") or c.data.startswith("reject_user:"))
def cb_decide_user(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 Owner only.")
        return
    action, user_id = call.data.split(":")
    user_id = int(user_id)
    if action == "approve_user":
        if user_id not in STATE["approved_users"]:
            STATE["approved_users"].append(user_id)
            save_state(STATE)
        bot.send_message(user_id, "✅ Approved!\nYou can now use this bot in your Channel/Group.\nTips: Add the bot as Admin and run <b>/enable</b> in your chat.\nContact admin if needed: @MinexxProo")
        bot.answer_callback_query(call.id, "User approved.")
    else:
        bot.send_message(user_id, "❌ Request Rejected by Admin.\nContact admin: @MinexxProo")
        bot.answer_callback_query(call.id, "User rejected.")

# ------------------- Chat activation -------------------
@bot.message_handler(commands=["enable"])
@require_online
def cmd_enable(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only chat admins can request activation.")
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Approve this chat", callback_data=f"approve_chat:{message.chat.id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_chat:{message.chat.id}")
    )
    title = message.chat.title or str(message.chat.id)
    bot.send_message(OWNER_ID, f"🧩 <b>Activation Request</b>\nChat: \"{title}\" (ID: {message.chat.id})\nRequester: @{message.from_user.username or message.from_user.id}", reply_markup=kb)
    bot.reply_to(message, "⏳ Sent activation request to Owner.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_chat:") or c.data.startswith("reject_chat:"))
def cb_decide_chat(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 Owner only.")
        return
    action, chat_id = call.data.split(":")
    chat_id = int(chat_id)
    if action == "approve_chat":
        if chat_id not in STATE["approved_chats"]:
            STATE["approved_chats"].append(chat_id)
            save_state(STATE)
        try:
            bot.send_message(chat_id, "✅ This chat is now approved to use the bot features.")
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Chat approved.")
    else:
        try:
            bot.send_message(chat_id, "❌ Activation rejected by Owner.\nContact admin: @MinexxProo")
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Chat rejected.")

# ------------------- Owner Panel & ON/OFF -------------------
@bot.message_handler(commands=["panel"])
def cmd_panel(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👥 View Users", callback_data="panel_view_users"),
           types.InlineKeyboardButton("🏷 View Chats", callback_data="panel_view_chats"))
    kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="panel_refresh"))
    if STATE["bot_status"] == "online":
        kb.add(types.InlineKeyboardButton("🔴 Turn Off Bot", callback_data="panel_off"))
    else:
        kb.add(types.InlineKeyboardButton("🟢 Turn On Bot", callback_data="panel_on"))
    text = (f"🧩 <b>PowerPointBreak × MinexxProo — Owner Panel</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 Approved Users: {len(STATE['approved_users'])}\n"
            f"🏷 Approved Channels/Groups: {len(STATE['approved_chats'])}\n"
            f"⚙️ Bot Status: {'✅ Online' if STATE['bot_status']=='online' else '❌ Offline'}")
    bot.send_message(message.chat.id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("panel_"))
def cb_panel(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 Owner only.")
        return
    if call.data == "panel_view_users":
        users = STATE["approved_users"]
        lines = [f"{i+1}. <code>{uid}</code>" for i, uid in enumerate(users)] or ["(empty)"]
        bot.send_message(call.message.chat.id, "👥 <b>Approved Users</b>\n" + "\n".join(lines))
    elif call.data == "panel_view_chats":
        chats = STATE["approved_chats"]
        lines = [f"{i+1}. <code>{cid}</code>" for i, cid in enumerate(chats)] or ["(empty)"]
        bot.send_message(call.message.chat.id, "🏷 <b>Approved Chats</b>\n" + "\n".join(lines))
    elif call.data == "panel_refresh":
        bot.answer_callback_query(call.id, "🔄 Refreshed.")
        cmd_panel(message=types.SimpleNamespace(chat=call.message.chat, from_user=call.from_user))
    elif call.data == "panel_off":
        STATE["bot_status"] = "offline"
        save_state(STATE)
        for chat_id in STATE["approved_chats"]:
            try:
                bot.send_message(chat_id, "🚫 PowerPointBreak Bot has been temporarily disabled by the admin.\nContact @MinexxProo for more information.")
            except Exception:
                pass
        bot.answer_callback_query(call.id, "Bot turned OFF.")
    elif call.data == "panel_on":
        STATE["bot_status"] = "online"
        save_state(STATE)
        for chat_id in STATE["approved_chats"]:
            try:
                bot.send_message(chat_id, "✅ PowerPointBreak Bot is now active again!\nAll functions restored successfully.")
            except Exception:
                pass
        bot.answer_callback_query(call.id, "Bot turned ON.")

@bot.message_handler(commands=["botoff"])
def cmd_botoff(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    STATE["bot_status"] = "offline"
    save_state(STATE)
    for chat_id in STATE["approved_chats"]:
        try:
            bot.send_message(chat_id, "🚫 PowerPointBreak Bot has been temporarily disabled by the admin.\nContact @MinexxProo for more information.")
        except Exception:
            pass
    bot.reply_to(message, "Bot turned OFF.")

@bot.message_handler(commands=["boton"])
def cmd_boton(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    STATE["bot_status"] = "online"
    save_state(STATE)
    for chat_id in STATE["approved_chats"]:
        try:
            bot.send_message(chat_id, "✅ PowerPointBreak Bot is now active again!\nAll functions restored successfully.")
        except Exception:
            pass
    bot.reply_to(message, "Bot turned ON.")

# ------------------- Helper: membership verify -------------------
def verify_membership(user_id: int) -> bool:
    try:
        ch = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        gr = bot.get_chat_member(GROUP_USERNAME, user_id)
        return ch.status not in ("left", "kicked") and gr.status not in ("left", "kicked")
    except Exception:
        return False

# ------------------- Giveaway: Join flow -------------------
@bot.callback_query_handler(func=lambda c: c.data in ("join_giveaway", "join_giveaway_again"))
def cb_join_giveaway(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    user = call.from_user
    if not bot_online() and not is_owner(user.id):
        bot.answer_callback_query(call.id, "🚫 Bot OFF. Contact @MinexxProo")
        return

    if not verify_membership(user.id):
        try:
            bot.send_message(user.id, (
                "🚫 You haven’t joined all required places!\n"
                f"Please join first 👇\n"
                f"📢 Channel → {CHANNEL_USERNAME}\n"
                f"💬 Group → {GROUP_USERNAME}\n"
                "Then press [🎯 Join Giveaway] again ✅"
            ))
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Join required channels/groups first.")
        return

    ensure_participants_chat(chat_id)
    plist = STATE["participants"][str(chat_id)]
    if not any(p["id"] == user.id for p in plist):
        plist.append({"id": user.id, "username": f"@{user.username}" if user.username else str(user.id)})
        save_state(STATE)

    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🎯 Join Giveaway Again", callback_data="join_giveaway_again"))
        bot.send_message(user.id, (
            "🎉 Congratulations! You’ve Successfully Joined 🎉\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💫 You are now officially part of this Giveaway!\n"
            "Stay active — winners will be announced soon! 🏆\n\n"
            f"📢 Channel: {CHANNEL_USERNAME}\n"
            f"💬 Group: {GROUP_USERNAME}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 Every Second Counts • Stay Focused\n"
            "#PowerPointBreak #MinexxProo"
        ), reply_markup=kb)
    except Exception:
        pass
    bot.answer_callback_query(call.id, "✅ Joined!")

@bot.message_handler(commands=["chkparticipate"])
@require_online
def cmd_chkparticipate(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can view participants.")
        return
    ensure_participants_chat(message.chat.id)
    plist = STATE["participants"][str(message.chat.id)]
    if not plist:
        bot.reply_to(message, "📋 Giveaway Participant List\n(Empty)")
        return
    lines = [f"{i+1}) {p['username']} (ID: {p['id']})" for i, p in enumerate(plist)]
    bot.reply_to(message, "📋 Giveaway Participant List\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + f"\n━━━━━━━━━━━━━━━━━━\nTotal: {len(plist)}\n👑 Only visible to Owner/Admin")

@bot.message_handler(commands=["winner"])
@require_online
def cmd_winner(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can pick winner.")
        return
    ensure_participants_chat(message.chat.id)
    plist = STATE["participants"][str(message.chat.id)]
    if not plist:
        bot.reply_to(message, "⚠️ No participants yet.")
        return
    parts = message.text.strip().split()
    count = 1
    if len(parts) > 1 and parts[1].isdigit():
        count = max(1, min(int(parts[1]), len(plist)))
    winners = random.sample(plist, count)
    if count == 1:
        w = winners[0]
        bot.send_message(message.chat.id, f"🏆 <b>Giveaway Winner Selected!</b>\n🎉 Winner: {w['username']}\n━━━━━━━━━━━━━━━━━━\nContact Admin: @MinexxProo\n#PowerPointBreak #MinexxProo")
    else:
        lines = [f"{i+1}) {w['username']}" for i, w in enumerate(winners)]
        bot.send_message(message.chat.id, "🏆 <b>Giveaway Winners</b>\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━\nContact Admin: @MinexxProo\n#PowerPointBreak #MinexxProo")

# ------------------- Giveaway posts -------------------
@bot.message_handler(commands=["setpost"])
@require_online
def cmd_setpost(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can set post.")
        return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /setpost <your giveaway message>")
        return
    STATE["post_template"] = parts[1]
    save_state(STATE)
    bot.reply_to(message, "✅ Giveaway post updated successfully! Use /showpost to preview.")

@bot.message_handler(commands=["showpost"])
def cmd_showpost(message: types.Message):
    bot.reply_to(message, f"📝 Current Giveaway Post:\n\n{STATE['post_template']}")

@bot.message_handler(commands=["resetpost"])
@require_online
def cmd_resetpost(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can reset post.")
        return
    STATE["post_template"] = DEFAULT_POST
    save_state(STATE)
    bot.reply_to(message, "♻️ Giveaway post reset to default.")

@bot.message_handler(commands=["giveaway"])
@require_online
def cmd_giveaway(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can start giveaway.")
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎯 Join Giveaway Now", callback_data="join_giveaway"))
    bot.send_message(message.chat.id, STATE["post_template"], reply_markup=kb)

@bot.message_handler(commands=["giveaway2"])
@require_online
def cmd_giveaway2(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id) and not (is_approved_user(message.from_user.id) and is_approved_chat(message.chat.id)):
        bot.reply_to(message, "🚫 Not allowed. Ask approval from @MinexxProo")
        return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /giveaway2 <your message>")
        return
    text = parts[1]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎯 Join Giveaway", callback_data="join_giveaway"))
    bot.send_message(message.chat.id, text, reply_markup=kb)

# ------------------- Countdown System -------------------
def format_countdown_text(total: int, remaining: int) -> str:
    percent = int((1 - remaining / total) * 10) if total > 0 else 10
    percent = max(0, min(10, percent))
    bar = "▰" * percent + "▱" * (10 - percent)
    tl, H, M, S = seconds_to_hms(remaining)
    text = (
        "⏳ Counting Down...\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Progress: {bar} {percent*10}%\n"
        f"Time Left: {tl}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Keep Watching 👀 • Every Moment Matters\n"
        "#PowerPointBreak #MinexxProo\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    return text

def countdown_loop(chat_id: int):
    data = COUNTDOWNS.get(chat_id)
    if not data:
        return
    while data["remaining"] >= 0 and not data.get("stopped", False):
        if not data.get("paused", False):
            try:
                txt = format_countdown_text(data["total"], data["remaining"])
                bot.edit_message_text(txt, chat_id, data["message_id"])
            except Exception:
                pass
            time.sleep(1)
            data["remaining"] -= 1
        else:
            time.sleep(1)
    if not data.get("stopped", False):
        try:
            bot.send_message(chat_id, (
                "🎉✨ TIME IS OVER! ✨🎉\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🔥 Countdown Completed Successfully! 🔥\n"
                "💎 Every second has its own value, and you made each one count. 💫\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "#PowerPointBreak #MinexxProo"
            ))
            if STATE.get("post_template"):
                try:
                    bot.send_message(CHANNEL_USERNAME, STATE["post_template"])
                except Exception:
                    pass
                try:
                    bot.send_message(GROUP_USERNAME, STATE["post_template"])
                except Exception:
                    pass
        except Exception:
            pass
    COUNTDOWNS.pop(chat_id, None)

@bot.message_handler(commands=["count"])
@require_online
def cmd_count(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can start countdown.")
        return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /count 1h30m20s  (or 45m, 90s, 2h)")
        return
    seconds = parse_duration(parts[1])
    if seconds <= 0:
        bot.reply_to(message, "⚠️ Invalid duration.")
        return
    tl, H, M, S = seconds_to_hms(seconds)
    start_text = (
        "🎉 Countdown Started!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Duration: {H} Hours {M} Minutes {S} Seconds\n"
        "💫 Let’s Begin The Countdown!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Progress: ▰▱▱▱▱▱▱▱▱▱ 10%\n"
        f"Time Left: {tl}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✨ Powered by {CHANNEL_USERNAME}\n"
        "🔥 Every Second Counts • Stay Focused\n"
        "#PowerPointBreak #MinexxProo\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(message.chat.id, start_text)

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⏸ Pause", callback_data=f"cd_pause:{message.chat.id}"),
        types.InlineKeyboardButton("▶️ Resume", callback_data=f"cd_resume:{message.chat.id}")
    )
    kb.row(
        types.InlineKeyboardButton("⏹ Stop", callback_data=f"cd_stop:{message.chat.id}"),
        types.InlineKeyboardButton("🔁 Refresh", callback_data=f"cd_refresh:{message.chat.id}")
    )
    bot.send_message(message.chat.id, "Admin Controls:", reply_markup=kb)

    COUNTDOWNS[message.chat.id] = {
        "remaining": seconds,
        "total": seconds,
        "paused": False,
        "stopped": False,
        "message_id": msg.message_id
    }
    th = threading.Thread(target=countdown_loop, args=(message.chat.id,), daemon=True)
    COUNTDOWNS[message.chat.id]["thread"] = th
    th.start()

def cd_admin_guard(call: types.CallbackQuery, chat_id: int) -> bool:
    if not admin_or_owner(call.from_user.id, chat_id):
        bot.answer_callback_query(call.id, "🚫 Admin/Owner only.")
        return False
    return True

@bot.callback_query_handler(func=lambda c: c.data.startswith(("cd_pause:", "cd_resume:", "cd_stop:", "cd_refresh:")))
def cb_countdown_controls(call: types.CallbackQuery):
    action, chat_id = call.data.split(":")
    chat_id = int(chat_id)
    data = COUNTDOWNS.get(chat_id)
    if not data:
        bot.answer_callback_query(call.id, "⚠️ No active countdown.")
        return
    if not cd_admin_guard(call, chat_id):
        return
    if action == "cd_pause":
        data["paused"] = True
        bot.answer_callback_query(call.id, "⏸ Paused.")
        try:
            tl, *_ = seconds_to_hms(data["remaining"])
            bot.send_message(chat_id, f"⏸ <b>Timer Paused by Admin.</b>\nTime Left: {tl}")
        except Exception:
            pass
    elif action == "cd_resume":
        data["paused"] = False
        bot.answer_callback_query(call.id, "▶️ Resumed.")
        try:
            tl, *_ = seconds_to_hms(data["remaining"])
            bot.send_message(chat_id, f"▶️ <b>Timer Resumed.</b>\nTime Left: {tl}")
        except Exception:
            pass
    elif action == "cd_stop":
        data["stopped"] = True
        bot.answer_callback_query(call.id, "⏹ Stopped.")
        bot.send_message(chat_id, "⏹ <b>Timer Stopped by Admin.</b>")
        COUNTDOWNS.pop(chat_id, None)
    elif action == "cd_refresh":
        bot.answer_callback_query(call.id, "🔁 Refreshed.")
        try:
            txt = format_countdown_text(data["total"], data["remaining"])
            bot.edit_message_text(txt, chat_id, data["message_id"])
        except Exception:
            pass

# ------------------- Timed giveaway helper -------------------
@bot.message_handler(commands=["settime"])
@require_online
def cmd_settime(message: types.Message):
    if not admin_or_owner(message.from_user.id, message.chat.id):
        bot.reply_to(message, "🚫 Only Owner/Admin can set giveaway time.")
        return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /settime 30m")
        return
    seconds = parse_duration(parts[1])
    if seconds <= 0:
        bot.reply_to(message, "⚠️ Invalid time.")
        return
    tl, *_ = seconds_to_hms(seconds)
    percent_bar = "▰" + "▱"*9
    bot.send_message(message.chat.id, f"⏳ Giveaway ends in: {tl}\nProgress: {percent_bar} 10%")

# ------------------- Status / Help -------------------
@bot.message_handler(commands=["status"])
def cmd_status(message: types.Message):
    st = "✅ Online" if bot_online() else "❌ Offline"
    bot.reply_to(message, f"⚙️ Bot Status: {st}\nOwner: @MinexxProo\nChannel: {CHANNEL_USERNAME}\nGroup: {GROUP_USERNAME}")

@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message):
    bot.reply_to(message, (
        "<b>PowerPointBreak × MinexxProo — Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "/mode countdown — switch to countdown mode (Owner/Admin)\n"
        "/mode giveaway — switch to giveaway mode (Owner/Admin)\n"
        "/count <time> — start countdown (Owner/Admin)\n"
        "/settime <time> — set giveaway time label (Owner/Admin)\n"
        "/pause /resume /stop /refresh — countdown controls (Owner/Admin)\n"
        "/giveaway — post default giveaway with join (Owner/Admin)\n"
        "/giveaway2 <msg> — instant giveaway post (Owner/Admin/Approved)\n"
        "/chkparticipate — view participants (Owner/Admin)\n"
        "/winner [n] — pick winner(s) (Owner/Admin)\n"
        "/setpost <text> — set default giveaway post (Owner/Admin)\n"
        "/showpost — show current default post\n"
        "/resetpost — reset default post (Owner/Admin)\n"
        "/enable — request chat activation (Chat Admin)\n"
        "/panel — owner panel (Owner)\n"
        "/botoff /boton — toggle bot (Owner)\n"
        "/viewusers /viewchats /approvelist — lists (Owner)\n"
        "/revoke <id> — revoke user/chat access (Owner)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Members can only join giveaways via button."
    ))

@bot.message_handler(commands=["mode"])
def cmd_mode(message: types.Message):
    bot.reply_to(message, "✅ Mode switching is implicit via commands. Use /count, /giveaway, /giveaway2.")

# ------------------- Run -------------------
def main():
    print("Bot is running (ClawCloud).")
    bot.infinity_polling(skip_pending=True, timeout=30)

# ------------------- Keepalive for Render free plan -------------------
# This creates a tiny web server so Render's "Web Service" stays alive
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "PowerPointBreak Bot is running OK!"

def run():
    app.run(host='0.0.0.0', port=8080)

# Start keepalive web server in background thread
threading.Thread(target=run).start()
# ----------------------------------------------------------------------

# Now start the Telegram bot
if __name__ == "__main__":
    print("Bot is running (Render Free 24/7 mode).")
    bot.infinity_polling(skip_pending=True, timeout=30)
