# -*- coding: utf-8 -*-
# PowerPointBreak Timer Bot — Render Free 24/7 Stable Version
# Features: /start /help /panel /enable /viewusers /viewchats /giveaway /giveaway2
# /count <min> /pause /resume /stop /winner [n] /setpost /showpost /resetpost /boton /botoff
# Keepalive: Flask (binds PORT) + single long-polling (webhook cleared) to avoid 409

import os, json, time, threading, random, signal, sys
from datetime import datetime, timedelta

import telebot
from telebot import types
from flask import Flask

# ---------------- Config ----------------
# Use env if set; else fallback to provided token (you can delete the fallback if you want)
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8482683142:AAH8u_8RdvKUO24KGMa2UAkWJij3RFtDG7Y"

# Optional owner/admin setup (set in Render -> Environment Variables if you want):
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # your numeric telegram user id, 0 -> auto owner at first /start
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")  # e.g. @mychannel
GROUP_USERNAME   = os.getenv("GROUP_USERNAME",   "")  # e.g. @mygroup

DATA_DIR   = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CHATS_FILE = os.path.join(DATA_DIR, "chats.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
POST_FILE  = os.path.join(DATA_DIR, "post.json")

os.makedirs(DATA_DIR, exist_ok=True)

def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

users  = _load(USERS_FILE, {})     # {user_id: {"name": str, "joined": "iso"}}
chats  = _load(CHATS_FILE, {})     # {chat_id: {"type": "private/group", "title": str}}
state  = _load(STATE_FILE, {       # runtime toggles + countdown
    "bot_enabled": True,
    "countdown_active": False,
    "countdown_end": None,         # iso
    "participants": [],            # user_ids for current giveaway
    "paused": False,
})
post   = _load(POST_FILE, {        # default giveaway post
    "text": "🎁 Giveaway! Tap the button to join.\n\n⏳ Ends soon… Good luck!",
})

def persist():
    _save(USERS_FILE, users)
    _save(CHATS_FILE, chats)
    _save(STATE_FILE, state)
    _save(POST_FILE, post)

# ---------------- Bot Init ----------------
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)

# Utility
def is_owner(uid: int) -> bool:
    global OWNER_ID
    if OWNER_ID == 0 and uid != 0:
        # First /start user becomes the owner (only once)
        OWNER_ID = uid
    return uid == OWNER_ID

def owner_or_admin(message) -> bool:
    if is_owner(message.from_user.id):
        return True
    # Basic admin check: chat admins if in groups
    if message.chat.type in ("group", "supergroup"):
        try:
            member = bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in ("administrator", "creator")
        except Exception:
            return False
    return False

def user_link(u):
    name = (u.first_name or "") + (" " + u.last_name if u.last_name else "")
    name = name.strip() or u.username or str(u.id)
    return f'<a href="tg://user?id={u.id}">{telebot.util.escape(name)}</a>'

# ---------------- Buttons ----------------
def join_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Join Giveaway", callback_data="join"))
    return kb

# ---------------- Commands ----------------
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    users[str(message.from_user.id)] = {
        "name": message.from_user.full_name,
        "joined": datetime.utcnow().isoformat()
    }
    chats[str(message.chat.id)] = {
        "type": message.chat.type,
        "title": message.chat.title or message.from_user.full_name
    }
    persist()
    if is_owner(message.from_user.id):
        bot.reply_to(message, "👑 Welcome Owner! Use /panel to open the Owner Dashboard.")
    else:
        bot.reply_to(message, "Welcome! Use /help to see commands.")

@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message):
    text = (
        "<b>🧭 Commands</b>\n"
        "/start — start the bot\n"
        "/help — show help\n\n"
        "<b>Owner/Admin</b>\n"
        "/panel — owner panel\n"
        "/enable — enable bot\n"
        "/botoff /boton — toggle bot\n"
        "/viewusers — list users\n"
        "/viewchats — list chats\n\n"
        "<b>Giveaway</b>\n"
        "/giveaway — post default giveaway with join button\n"
        "/giveaway2 &lt;msg&gt; — instant giveaway post\n"
        "/count &lt;minutes&gt; — start countdown\n"
        "/pause /resume /stop — control countdown\n"
        "/winner [n] — pick n winners (default 1)\n"
        "/setpost &lt;text&gt; — set default post text\n"
        "/showpost — show current default post\n"
        "/resetpost — reset default post"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=["panel"])
def cmd_panel(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 View Users",  callback_data="panel_users"),
        types.InlineKeyboardButton("📋 View Chats", callback_data="panel_chats"),
    )
    kb.add(types.InlineKeyboardButton(
        "🔴 Turn Off Bot" if state["bot_enabled"] else "🟢 Turn On Bot",
        callback_data="panel_toggle"
    ))
    text = (
        "<b>🧩 PowerPointBreak × Owner Panel</b>\n"
        f"Approved Users: <code>{len(users)}</code>\n"
        f"Approved Chats/Groups: <code>{len(chats)}</code>\n"
        f"Bot Status: {'✅ Online' if state['bot_enabled'] else '⛔ Offline'}"
    )
    bot.reply_to(message, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("panel_"))
def on_panel_buttons(c: types.CallbackQuery):
    if not is_owner(c.from_user.id):
        bot.answer_callback_query(c.id, "Owner only.")
        return
    if c.data == "panel_users":
        lines = ["<b>Approved Users</b>"]
        for uid, info in list(users.items())[:100]:
            lines.append(f"• <code>{uid}</code> — {telebot.util.escape(info.get('name',''))}")
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "\n".join(lines) if len(lines) > 1 else "No users yet.")
    elif c.data == "panel_chats":
        lines = ["<b>Approved Chats</b>"]
        for cid, info in list(chats.items())[:100]:
            lines.append(f"• <code>{cid}</code> — {telebot.util.escape(info.get('title',''))}")
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "\n".join(lines) if len(lines) > 1 else "No chats yet.")
    elif c.data == "panel_toggle":
        state["bot_enabled"] = not state["bot_enabled"]
        persist()
        bot.answer_callback_query(c.id, "Toggled.")
        try:
            bot.delete_message(c.message.chat.id, c.message.id)
        except Exception:
            pass

@bot.message_handler(commands=["enable"])
def cmd_enable(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    state["bot_enabled"] = True
    persist()
    bot.reply_to(message, "✅ Bot enabled.")

@bot.message_handler(commands=["botoff", "boton"])
def cmd_botonoff(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    state["bot_enabled"] = (message.text.split()[0] == "/boton")
    persist()
    bot.reply_to(message, f"{'🟢 On' if state['bot_enabled'] else '🔴 Off'}")

@bot.message_handler(commands=["viewusers"])
def cmd_viewusers(message: types.Message):
    if not owner_or_admin(message):
        return
    lines = ["<b>Approved Users</b>"]
    for uid, info in list(users.items())[:200]:
        lines.append(f"• <code>{uid}</code> — {telebot.util.escape(info.get('name',''))}")
    bot.reply_to(message, "\n".join(lines) if len(lines) > 1 else "No users yet.")

@bot.message_handler(commands=["viewchats"])
def cmd_viewchats(message: types.Message):
    if not owner_or_admin(message):
        return
    lines = ["<b>Chats</b>"]
    for cid, info in list(chats.items())[:200]:
        lines.append(f"• <code>{cid}</code> — {telebot.util.escape(info.get('title',''))}")
    bot.reply_to(message, "\n".join(lines) if len(lines) > 1 else "No chats yet.")

# -------- Giveaway & Countdown ----------
@bot.message_handler(commands=["giveaway"])
def cmd_giveaway(message: types.Message):
    if not owner_or_admin(message):
        return
    if not state["bot_enabled"]:
        bot.reply_to(message, "⛔ Bot is currently off.")
        return
    kb = join_keyboard()
    bot.reply_to(message, post["text"], reply_markup=kb)

@bot.message_handler(commands=["giveaway2"])
def cmd_giveaway2(message: types.Message):
    if not owner_or_admin(message):
        return
    if not state["bot_enabled"]:
        bot.reply_to(message, "⛔ Bot is currently off.")
        return
    text = message.text.partition(" ")[2].strip() or "🎁 Giveaway! Tap to join."
    kb = join_keyboard()
    bot.reply_to(message, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "join")
def on_join(c: types.CallbackQuery):
    if not state["bot_enabled"]:
        bot.answer_callback_query(c.id, "Bot is off now.")
        return
    uid = c.from_user.id
    if str(uid) not in users:
        users[str(uid)] = {"name": c.from_user.full_name, "joined": datetime.utcnow().isoformat()}
    if uid not in state["participants"]:
        state["participants"].append(uid)
        persist()
        bot.answer_callback_query(c.id, "Joined! ✅")
    else:
        bot.answer_callback_query(c.id, "You already joined.")

@bot.message_handler(commands=["setpost"])
def cmd_setpost(message: types.Message):
    if not owner_or_admin(message):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        bot.reply_to(message, "Send: /setpost <text>")
        return
    post["text"] = text
    persist()
    bot.reply_to(message, "✅ Default giveaway post updated.")

@bot.message_handler(commands=["showpost"])
def cmd_showpost(message: types.Message):
    if not owner_or_admin(message):
        return
    bot.reply_to(message, "<b>Current Giveaway Post:</b>\n\n" + post["text"])

@bot.message_handler(commands=["resetpost"])
def cmd_resetpost(message: types.Message):
    if not owner_or_admin(message):
        return
    post["text"] = "🎁 Giveaway! Tap the button to join.\n\n⏳ Ends soon… Good luck!"
    persist()
    bot.reply_to(message, "✅ Reset to default.")

def _countdown_worker():
    while True:
        try:
            if state.get("countdown_active") and not state.get("paused"):
                end_iso = state.get("countdown_end")
                if end_iso:
                    end = datetime.fromisoformat(end_iso)
                    if datetime.utcnow() >= end:
                        # pick winner(s)
                        winners = []
                        parts = list(state.get("participants", []))
                        if parts:
                            winners.append(random.choice(parts))
                        state["countdown_active"] = False
                        persist()
                        try:
                            text = "⏱ Countdown finished!\n"
                            if winners:
                                w = winners[0]
                                text += f"🏆 Winner: <a href='tg://user?id={w}'>User {w}</a>"
                            else:
                                text += "No participants."
                            # try to notify owner if exists
                            if OWNER_ID:
                                bot.send_message(OWNER_ID, text)
                        except Exception:
                            pass
            time.sleep(2)
        except Exception:
            time.sleep(5)

@bot.message_handler(commands=["count"])
def cmd_count(message: types.Message):
    if not owner_or_admin(message):
        return
    try:
        minutes = int(message.text.split(maxsplit=1)[1])
    except Exception:
        bot.reply_to(message, "Usage: /count <minutes>")
        return
    if minutes <= 0 or minutes > 24*60:
        bot.reply_to(message, "Give 1..1440 minutes.")
        return
    state["countdown_active"] = True
    state["paused"] = False
    state["participants"] = []
    state["countdown_end"] = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
    persist()
    bot.reply_to(message, f"⏳ Countdown started for <b>{minutes}</b> minutes.\nParticipants cleared. Use /pause /resume /stop.")

@bot.message_handler(commands=["pause"])
def cmd_pause(message: types.Message):
    if not owner_or_admin(message):
        return
    state["paused"] = True
    persist()
    bot.reply_to(message, "⏸ Paused.")

@bot.message_handler(commands=["resume"])
def cmd_resume(message: types.Message):
    if not owner_or_admin(message):
        return
    state["paused"] = False
    persist()
    bot.reply_to(message, "▶️ Resumed.")

@bot.message_handler(commands=["stop"])
def cmd_stop(message: types.Message):
    if not owner_or_admin(message):
        return
    state["countdown_active"] = False
    persist()
    bot.reply_to(message, "⏹ Stopped.")

@bot.message_handler(commands=["winner"])
def cmd_winner(message: types.Message):
    if not owner_or_admin(message):
        return
    try:
        n = int(message.text.split(maxsplit=1)[1])
    except Exception:
        n = 1
    parts = list(state.get("participants", []))
    if not parts:
        bot.reply_to(message, "No participants yet.")
        return
    n = max(1, min(n, len(parts)))
    winners = random.sample(parts, n)
    txt = "🏆 Winner(s):\n" + "\n".join([f"• <a href='tg://user?id={w}'>User {w}</a>" for w in winners])
    bot.reply_to(message, txt)

# ---------------- KeepAlive (Flask) ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "PowerPointBreak Bot is running OK!"

def run_flask():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# ---------------- Runner ----------------
def start_bot():
    # Hard-protect: avoid 409 by clearing webhook before polling
    try:
        bot.remove_webhook()
    except Exception:
        pass
    time.sleep(1)
    print("Bot is running (Render Free 24/7 mode).")
    # NB: skip_pending=True prevents processing duplicate updates after restarts
    bot.infinity_polling(skip_pending=True, timeout=30)

def handle_sigterm(*_):
    print("SIGTERM received, shutting down gracefully…")
    try:
        bot.stop_polling()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

if __name__ == "__main__":
    # Background keepalive server
    threading.Thread(target=run_flask, daemon=True).start()
    # Countdown monitor
    threading.Thread(target=_countdown_worker, daemon=True).start()
    # Start the bot (single polling loop)
    start_bot()
