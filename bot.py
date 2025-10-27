# -*- coding: utf-8 -*-
# PowerPointBreak × MinexxProo — PREMIUM TIMER & GIVEAWAY BOT (v2.0)
# Host: Render Free (Flask keepalive + single polling)
# Features:
#  • /start /help (Premium UI)
#  • Owner Panel: /panel  (ON/OFF, Users, Chats, Refresh)
#  • Approve System: /enable  → owner gets [Approve/Reject]
#  • Giveaway: /giveaway (default), /giveaway2 <text> (instant), /chkparticipate, /winner [n]
#  • Join-Verify (must be in channel & group)
#  • Countdown: /count <XhYmZs>, pause/resume/stop/refresh buttons + per-sec progress
#  • End-Post: /setpost /showpost /resetpost  (auto-post after countdown if set)

import os, json, re, time, random, threading, signal, sys
from datetime import datetime
from typing import Dict, Any

import telebot
from telebot import types
from flask import Flask

# ========= CONFIG via ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()  # set in Render Variables
OWNER_ID  = int(os.getenv("OWNER_ID", "5692210187"))
CHAN_USER = os.getenv("CHANNEL_USERNAME", "@PowerPointBreak")
GRP_USER  = os.getenv("GROUP_USERNAME", "@PowerPointBreakConversion")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set. Add it in Render -> Environment Variables.")

# ========= KEEPALIVE (Render needs a PORT) =========
app = Flask(__name__)

@app.route("/")
def home():
    return "PowerPointBreak v2.0 — OK"

def run_flask():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# ========= DATA (persistent) =========
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

STATE_FILE = os.path.join(DATA_DIR, "state.json")
def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        state = {
            "bot_status": "online",
            "approved_users": [],     # reserved if needed later
            "approved_chats": [],     # chat_ids where bot enabled
            "post_template": (
                "🎮💥 POWERPOINTBREAK MEGA GIVEAWAY 💥🎮\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🔥 15× EXPRESSVPN PREMIUM ACCOUNTS 🔥\n"
                "🕓 Time: 8:30 PM (BD Time)\n"
                "⏳ Ending Soon – Stay Ready!\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🎯 Click Below To Join 👇"
            ),
            "participants": {},       # chat_id -> [{"id":..., "username":...}]
        }
        save_state(state); return state
    with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_state(state: Dict[str, Any]):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

STATE = load_state()

# ========= BOT =========
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)

# countdown runtime
COUNT = {}  # chat_id -> {"running":bool,"paused":bool,"left":int,"msg_id":int,"total":int,"end_post":bool}

# ========= HELPERS =========
def is_owner(uid: int) -> bool: return uid == OWNER_ID

def is_admin(uid: int, chat_id: int) -> bool:
    try:
        m = bot.get_chat_member(chat_id, uid)
        return m.status in ("administrator","creator")
    except Exception:
        return False

def admin_or_owner(uid: int, chat_id: int) -> bool:
    return is_owner(uid) or is_admin(uid, chat_id)

def verify_join(uid: int) -> bool:
    """must be in channel & group; returns True if joined"""
    try:
        ch = bot.get_chat_member(CHAN_USER, uid)
        gr = bot.get_chat_member(GRP_USER,  uid)
        ok1 = ch.status not in ("left","kicked")
        ok2 = gr.status not in ("left","kicked")
        return ok1 and ok2
    except Exception:
        return False

def ensure_participants(chat_id: int):
    if str(chat_id) not in STATE["participants"]:
        STATE["participants"][str(chat_id)] = []
        save_state(STATE)

def hms(sec: int):
    if sec < 0: sec = 0
    H = sec//3600; M = (sec%3600)//60; S = sec%60
    return f"{H:02}:{M:02}:{S:02}"

def parse_duration(text: str) -> int:
    # supports: 1h20m15s / 15m / 90s (any order ok)
    h=m=s=0
    a = re.search(r"(\d+)\s*h", text, re.I); b = re.search(r"(\d+)\s*m", text, re.I); c = re.search(r"(\d+)\s*s", text, re.I)
    if a: h=int(a.group(1))
    if b: m=int(b.group(1))
    if c: s=int(c.group(1))
    if not(a or b or c) and text.isdigit(): s=int(text)
    return h*3600+m*60+s

def pbar(done:int, total:int, width:int=10):
    if total<=0: total=1
    r=max(0.0,min(1.0,done/total)); fill=int(round(width*r))
    return "▰"*fill + "▱"*(width-fill)

def require_online(func):
    def wrapper(message, *a, **kw):
        if STATE.get("bot_status","online")!="online" and not is_owner(message.from_user.id):
            bot.reply_to(message,"🚫 Bot is OFF. Contact admin: @MinexxProo"); return
        return func(message,*a,**kw)
    return wrapper

# ========= /start =========
@bot.message_handler(commands=["start"])
def cmd_start(m: types.Message):
    if is_owner(m.from_user.id):
        bot.reply_to(m,"👑 Welcome Owner!\nUse /panel to open the Owner Dashboard.")
    else:
        bot.reply_to(m,
            "🌟 <b>PowerPointBreak × MinexxProo</b>\n"
            "Welcome! Use /help to view commands.\n\n"
            f"📢 Channel: {CHAN_USER}\n"
            f"💬 Group: {GRP_USER}"
        )

# ========= HELP (Premium UI) =========
@bot.message_handler(commands=["help"])
def cmd_help(m: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🎁 Giveaway", callback_data="help_giveaway"),
        types.InlineKeyboardButton("🕒 Countdown", callback_data="help_timer")
    )
    kb.row(
        types.InlineKeyboardButton("🏆 Winner", callback_data="help_winner"),
        types.InlineKeyboardButton("⚙️ Admin Panel", callback_data="help_admin")
    )
    kb.row(types.InlineKeyboardButton("📜 All Commands", callback_data="help_all"))
    bot.send_message(m.chat.id,
        "🌟 <b>PowerPointBreak × MinexxProo — Premium Command Menu</b>\n"
        "Choose a category below:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("help_"))
def cb_help(c: types.CallbackQuery):
    bot.answer_callback_query(c.id)
    if c.data=="help_giveaway":
        bot.send_message(c.message.chat.id,
            "🎁 <b>Giveaway</b>\n"
            "`/giveaway` — Default giveaway post\n"
            "`/giveaway2 <msg>` — Instant custom post\n"
            "`/chkparticipate` — Participants list (admin only)\n"
            "`/winner [n]` — Pick winner(s)\n"
            "`/setpost <text>` `/showpost` `/resetpost`",
            parse_mode="Markdown")
    elif c.data=="help_timer":
        bot.send_message(c.message.chat.id,
            "🕒 <b>Countdown</b>\n"
            "`/count <time>` — e.g., 1h20m15s / 90s\n"
            "Controls: Pause / Resume / Stop / Refresh (buttons)",
            parse_mode="Markdown")
    elif c.data=="help_winner":
        bot.send_message(c.message.chat.id,
            "🏆 <b>Winners</b>\n"
            "`/chkparticipate` — View participants (admin)\n"
            "`/winner [n]` — Choose random winners",
            parse_mode="Markdown")
    elif c.data=="help_admin":
        bot.send_message(c.message.chat.id,
            "⚙️ <b>Admin/Owner</b>\n"
            "`/panel` — Owner Dashboard\n"
            "`/enable` — Chat activation request\n"
            "`/botoff` `/boton` — Toggle bot\n"
            "`/viewusers` `/viewchats` (optional)\n",
            parse_mode="Markdown")
    else:
        bot.send_message(c.message.chat.id,
            "📜 <b>All Commands</b>\n"
            "`/start` `/help` `/panel` `/enable` `/botoff` `/boton`\n"
            "`/giveaway` `/giveaway2` `/chkparticipate` `/winner`\n"
            "`/setpost` `/showpost` `/resetpost`\n"
            "`/count` + pause/resume/stop/refresh buttons",
            parse_mode="Markdown")

# ========= OWNER PANEL =========
@bot.message_handler(commands=["panel"])
def cmd_panel(m: types.Message):
    if not is_owner(m.from_user.id): return
    kb = types.InlineKeyboardMarkup()
    if STATE["bot_status"]=="online":
        kb.add(types.InlineKeyboardButton("🔴 Turn Off Bot", callback_data="panel_off"))
    else:
        kb.add(types.InlineKeyboardButton("🟢 Turn On Bot",  callback_data="panel_on"))
    kb.row(
        types.InlineKeyboardButton("👥 View Users", callback_data="panel_users"),
        types.InlineKeyboardButton("💬 View Chats", callback_data="panel_chats"),
    )
    kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="panel_refresh"))
    bot.send_message(m.chat.id,
        f"🧩 <b>Owner Panel</b>\n"
        f"Status: {'✅ Online' if STATE['bot_status']=='online' else '❌ Offline'}\n"
        f"Approved Chats: {len(STATE['approved_chats'])}",
        reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("panel_"))
def cb_panel(c: types.CallbackQuery):
    if not is_owner(c.from_user.id): 
        bot.answer_callback_query(c.id, "Owner only."); return
    if c.data=="panel_off":
        STATE["bot_status"]="offline"; save_state(STATE)
        for cid in STATE["approved_chats"]:
            try: bot.send_message(cid,"🚫 Bot disabled by Admin. Contact @MinexxProo")
            except: pass
        bot.answer_callback_query(c.id,"OFF")
    elif c.data=="panel_on":
        STATE["bot_status"]="online"; save_state(STATE)
        for cid in STATE["approved_chats"]:
            try: bot.send_message(cid,"✅ Bot active again!")
            except: pass
        bot.answer_callback_query(c.id,"ON")
    elif c.data=="panel_users":
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id,"👥 Approved Users (reserved)\n(Use OWNER only features)")
    elif c.data=="panel_chats":
        bot.answer_callback_query(c.id)
        lines=[f"{i+1}. <code>{cid}</code>" for i,cid in enumerate(STATE["approved_chats"])] or ["(empty)"]
        bot.send_message(c.message.chat.id,"💬 Approved Chats\n"+"\n".join(lines))
    else:  # refresh
        bot.answer_callback_query(c.id,"Refreshed.")
        cmd_panel(types.SimpleNamespace(chat=c.message.chat, from_user=c.from_user))

@bot.message_handler(commands=["botoff"])
def cmd_botoff(m: types.Message):
    if not is_owner(m.from_user.id): return
    STATE["bot_status"]="offline"; save_state(STATE); bot.reply_to(m,"🔴 Bot OFF")

@bot.message_handler(commands=["boton"])
def cmd_boton(m: types.Message):
    if not is_owner(m.from_user.id): return
    STATE["bot_status"]="online"; save_state(STATE); bot.reply_to(m,"🟢 Bot ON")

# ========= APPROVE SYSTEM =========
@bot.message_handler(commands=["enable"])
def cmd_enable(m: types.Message):
    # Only chat admins (or owner) can request
    if not (is_owner(m.from_user.id) or is_admin(m.from_user.id, m.chat.id)):
        bot.reply_to(m,"🚫 Only chat admins can request activation."); return
    if m.chat.id in STATE["approved_chats"]:
        bot.reply_to(m,"✅ This chat already approved."); return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_chat:{m.chat.id}"),
           types.InlineKeyboardButton("❌ Reject",  callback_data=f"reject_chat:{m.chat.id}"))
    try:
        bot.send_message(OWNER_ID, f"🧩 Activation Request\nChat ID: <code>{m.chat.id}</code>", reply_markup=kb)
        bot.reply_to(m,"📝 Request sent to Owner. Please wait.")
    except:
        bot.reply_to(m,"⚠️ Could not notify owner. DM @MinexxProo")

@bot.callback_query_handler(func=lambda c: c.data.startswith(("approve_chat:","reject_chat:")))
def cb_approve_chat(c: types.CallbackQuery):
    if not is_owner(c.from_user.id):
        bot.answer_callback_query(c.id,"Owner only."); return
    _act, id_str = c.data.split(":"); chat_id = int(id_str)
    if _act=="approve_chat":
        if chat_id not in STATE["approved_chats"]:
            STATE["approved_chats"].append(chat_id); save_state(STATE)
        try: bot.send_message(chat_id,"✅ Activation approved! Use /help.")
        except: pass
        bot.answer_callback_query(c.id,"Approved.")
    else:
        try: bot.send_message(chat_id,"❌ Activation rejected by Owner.")
        except: pass
        bot.answer_callback_query(c.id,"Rejected.")

# ========= GIVEAWAY =========
@bot.message_handler(commands=["setpost"])
@require_online
def cmd_setpost(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    text = m.text.split(" ",1)[1] if " " in m.text else ""
    if not text: bot.reply_to(m,"Usage: /setpost <text>"); return
    STATE["post_template"]=text; save_state(STATE)
    bot.reply_to(m,"✅ Giveaway post updated.")

@bot.message_handler(commands=["showpost"])
def cmd_showpost(m: types.Message):
    bot.reply_to(m, "📝 Current Post:\n\n"+STATE["post_template"])

@bot.message_handler(commands=["resetpost"])
@require_online
def cmd_resetpost(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    # back to default
    STATE["post_template"] = (
        "🎮💥 POWERPOINTBREAK MEGA GIVEAWAY 💥🎮\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔥 15× EXPRESSVPN PREMIUM ACCOUNTS 🔥\n"
        "🕓 Time: 8:30 PM (BD Time)\n"
        "⏳ Ending Soon – Stay Ready!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 Click Below To Join 👇"
    )
    save_state(STATE); bot.reply_to(m,"🔄 Reset to default post.")

@bot.message_handler(commands=["giveaway"])
@require_online
def cmd_giveaway(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎯 Join Giveaway", callback_data="join_giveaway"))
    bot.send_message(m.chat.id, STATE["post_template"], reply_markup=kb)

@bot.message_handler(commands=["giveaway2"])
@require_online
def cmd_giveaway2(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    text = m.text.split(" ",1)[1] if " " in m.text else "🎁 Giveaway! Tap below to join 👇"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎯 Join Giveaway", callback_data="join_giveaway"))
    bot.send_message(m.chat.id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ("join_giveaway","join_giveaway_again"))
def cb_join(c: types.CallbackQuery):
    chat_id = c.message.chat.id; uid = c.from_user.id
    if STATE.get("bot_status")!="online" and not is_owner(uid):
        bot.answer_callback_query(c.id,"Bot OFF."); return
    if not verify_join(uid):
        try:
            bot.send_message(uid,
                "🚫 You haven’t joined all required places!\n"
                f"📢 Channel → {CHAN_USER}\n"
                f"💬 Group → {GRP_USER}\n"
                "Then press [🎯 Join Giveaway] again ✅"
            )
        except: pass
        bot.answer_callback_query(c.id,"Join channel & group first."); return
    ensure_participants(chat_id)
    P = STATE["participants"][str(chat_id)]
    if not any(p["id"]==uid for p in P):
        P.append({"id":uid,"username":f"@{c.from_user.username}" if c.from_user.username else str(uid)})
        save_state(STATE)
    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🎯 Join Giveaway Again", callback_data="join_giveaway_again"))
        bot.send_message(uid,
            "🎉 Congratulations! You’ve Successfully Joined 🎉\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💫 You are now officially part of this Giveaway!\n"
            "Stay active — winners will be announced soon! 🏆\n\n"
            f"📢 Channel: {CHAN_USER}\n"
            f"💬 Group: {GRP_USER}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 Every Second Counts • Stay Focused\n"
            "#PowerPointBreak #MinexxProo",
            reply_markup=kb)
    except: pass
    bot.answer_callback_query(c.id,"✅ Joined!")

@bot.message_handler(commands=["chkparticipate"])
@require_online
def cmd_chk(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    ensure_participants(m.chat.id)
    P = STATE["participants"][str(m.chat.id)]
    if not P:
        bot.reply_to(m,"📋 Participants: (empty)"); return
    lines = [f"{i+1}) {p['username']} (ID: {p['id']})" for i,p in enumerate(P)]
    bot.reply_to(m,"📋 Giveaway Participant List\n━━━━━━━━━━━━━━━━━━\n"+"\n".join(lines)+f"\n━━━━━━━━━━━━━━━━━━\nTotal: {len(P)}\n👑 Visible to Owner/Admin")

@bot.message_handler(commands=["winner"])
@require_online
def cmd_winner(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    ensure_participants(m.chat.id)
    P = STATE["participants"][str(m.chat.id)]
    if not P:
        bot.reply_to(m,"⚠️ No participants yet."); return
    parts = m.text.split()
    n = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 1
    n = max(1, min(n, len(P)))
    W = random.sample(P, n)
    if n==1:
        w = W[0]
        bot.send_message(m.chat.id,
            f"🏆 <b>Giveaway Winner Selected!</b>\n🎉 Winner: {w['username']}\n"
            "━━━━━━━━━━━━━━━━━━\nContact Admin: @MinexxProo\n#PowerPointBreak #MinexxProo")
    else:
        lines = [f"{i+1}) {w['username']}" for i,w in enumerate(W)]
        bot.send_message(m.chat.id,
            "🏆 <b>Giveaway Winners</b>\n"+ "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━\nContact Admin: @MinexxProo\n#PowerPointBreak #MinexxProo")

# ========= COUNTDOWN =========
def edit_safe(chat_id:int, msg_id:int, text:str):
    try: bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    except: pass

def countdown_worker(chat_id:int):
    T = COUNT[chat_id]
    total = T["total"]; msg_id = T["msg_id"]
    while T["running"] and T["left"]>=0:
        if T["paused"]:
            time.sleep(1); continue
        left = T["left"]; done = total-left
        bar = pbar(done,total)
        txt = (
            "⏳ <b>Counting Down...</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"Progress: {bar} {int((done/max(1,total))*100)}%\n"
            f"Time Left: <b>{hms(left)}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Keep Watching 👀 • Every Moment Matters\n"
            "#PowerPointBreak #MinexxProo"
        )
        edit_safe(chat_id,msg_id,txt)
        if left==0: break
        T["left"]-=1; time.sleep(1)
    if T["running"] and T["left"]==0:
        # finish + end-post (if any)
        bot.send_message(chat_id,
            "🎉✨ <b>TIME IS OVER!</b> ✨🎉\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 Countdown Completed Successfully! 🔥\n"
            "💎 Every second counts. 💫\n"
            "━━━━━━━━━━━━━━━━━━\n#PowerPointBreak #MinexxProo")
        if T.get("end_post", False):  # auto post default message if chosen
            bot.send_message(chat_id, STATE["post_template"])
    T["running"]=False

@bot.message_handler(commands=["count"])
@require_online
def cmd_count(m: types.Message):
    if not admin_or_owner(m.from_user.id, m.chat.id): return
    if m.chat.id not in STATE["approved_chats"] and not is_owner(m.from_user.id):
        bot.reply_to(m,"🔒 This chat is not approved. Ask owner with /enable."); return
    arg = m.text.split(" ",1)[1] if " " in m.text else ""
    secs = parse_duration(arg)
    if secs<=0: bot.reply_to(m,"Usage: /count 1h20m15s (or 90s)"); return

    # Start message + control buttons
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("⏸ Pause", callback_data="cd_pause"),
           types.InlineKeyboardButton("▶️ Resume", callback_data="cd_resume"))
    kb.row(types.InlineKeyboardButton("⏹ Stop", callback_data="cd_stop"),
           types.InlineKeyboardButton("🔁 Refresh", callback_data="cd_refresh"))
    kb.add(types.InlineKeyboardButton("📌 End-Post ON/OFF", callback_data="cd_toggle_post"))

    start_text = (
        "🎉 <b>Countdown Started!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Duration: {hms(secs)}\n"
        "💫 Let’s Begin The Countdown!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Progress: ▱▱▱▱▱▱▱▱▱▱ 0%\n"
        f"Time Left: <b>{hms(secs)}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✨ Powered by @PowerPointBreak\n"
        "🔥 Every Second Counts • Stay Focused\n"
        "#PowerPointBreak #MinexxProo"
    )
    msg = bot.send_message(m.chat.id, start_text, reply_markup=kb)

    COUNT[m.chat.id] = {"running":True,"paused":False,"left":secs,"msg_id":msg.message_id,"total":secs,"end_post":True}
    threading.Thread(target=countdown_worker, args=(m.chat.id,), daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data in ("cd_pause","cd_resume","cd_stop","cd_refresh","cd_toggle_post"))
def cb_count_buttons(c: types.CallbackQuery):
    chat_id = c.message.chat.id
    T = COUNT.get(chat_id)
    if not T or not T["running"]:
        bot.answer_callback_query(c.id,"No active countdown."); return
    # only chat admins/owner can control
    if not admin_or_owner(c.from_user.id, chat_id):
        bot.answer_callback_query(c.id,"Admin only."); return

    if c.data=="cd_pause":
        T["paused"]=True; bot.answer_callback_query(c.id,"Paused.")
    elif c.data=="cd_resume":
        T["paused"]=False; bot.answer_callback_query(c.id,"Resumed.")
    elif c.data=="cd_stop":
        T["running"]=False; bot.answer_callback_query(c.id,"Stopped.")
        bot.send_message(chat_id,"⏹ Timer Stopped.")
    elif c.data=="cd_refresh":
        # force one redraw
        left=T["left"]; done=T["total"]-left; bar=pbar(done,T["total"])
        txt=("⏳ <b>Counting Down...</b>\n━━━━━━━━━━━━━━━━━━\n"
             f"Progress: {bar} {int((done/max(1,T['total']))*100)}%\n"
             f"Time Left: <b>{hms(left)}</b>\n━━━━━━━━━━━━━━━━━━\n"
             "Keep Watching 👀 • Every Moment Matters\n#PowerPointBreak #MinexxProo")
        edit_safe(chat_id,T["msg_id"],txt); bot.answer_callback_query(c.id,"Refreshed.")
    else:
        T["end_post"] = not T["end_post"]
        bot.answer_callback_query(c.id, f"End-Post: {'ON' if T['end_post'] else 'OFF'}")

# ========= OPTIONAL VIEWS =========
@bot.message_handler(commands=["viewusers"])
def cmd_viewusers(m: types.Message):
    if not is_owner(m.from_user.id): return
    bot.reply_to(m,"(Reserved for future user-approval list)")

@bot.message_handler(commands=["viewchats"])
def cmd_viewchats(m: types.Message):
    if not is_owner(m.from_user.id): return
    lines = [f"{i+1}. <code>{cid}</code>" for i,cid in enumerate(STATE["approved_chats"])] or ["(empty)"]
    bot.reply_to(m,"💬 Approved Chats\n"+"\n".join(lines))

# ========= STARTUP =========
def start_bot():
    # Prevent 409 Conflict
    try: bot.remove_webhook()
    except: pass
    time.sleep(1)
    print("PowerPointBreak v2.0 — bot polling started.")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

def handle_sigterm(*_):
    print("Shutting down…"); sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

if __name__ == "__main__":
    # keepalive + bot
    threading.Thread(target=run_flask, daemon=True).start()
    start_bot()
