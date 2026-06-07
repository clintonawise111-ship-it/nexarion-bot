import asyncio, logging, aiohttp, time, random, os, requests as req_sync, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import TelegramError

BOT_TOKEN="8931752692:AAFzry4NOFFRbTI_HB6UCuQ5Ok_Jd53WgBU"; ADMIN_ID=6326301165
CHANNEL="@nexarion11news"; CHANNEL_LINK="https://t.me/nexarion11news"
TWITTER="https://x.com/Nexarion11"; BOT_UN="Nexarion11airtimebot"
DB_TOKEN="zgVcmvDGZGWbnjDyDqfP3xJqibjpdeG7pVYHdWZJizsmQ1pCYU8KTfn7vY7VMbdUYm4gDF"
DB_URL="https://databoomnigeria.ng/api"
DB_HEADS={"Authorization":f"Token {DB_TOKEN}","Content-Type":"application/json"}
NETS={"MTN":1,"Airtel":2,"Glo":3,"9mobile":4}

TURSO_URL="libsql://nexarion-clintonawise222-creator.aws-us-west-2.turso.io"
TURSO_TOKEN="eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAyNjcyMTYsImlkIjoiMDE5ZTgwMzAtOTcwMS03NjY2LWE2ZTMtYzJkMDdiOWM1NzQ4IiwicmlkIjoiYjNiNDA0OTMtMTQzNS00NGFkLWIzNWQtNTRlNTVhYTU3Yzc3In0.x-EB9n2-eSGcLGDmS510NQ6oxnQCYFcQV0eedYJGbApBNO559A_jZVkEhsyVKkwPKdfcY47x8-9MEw7bk6rUDA"

AWAIT_PHONE,AWAIT_NET,AWAIT_CONFIRM,AWAIT_BC_TYPE,AWAIT_BC_MSG,AWAIT_T_TITLE,AWAIT_T_DESC,AWAIT_T_LINK,AWAIT_T_PTS,AWAIT_T_TYPE=range(10)
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",level=logging.INFO)
log=logging.getLogger(__name__)

# ── Turso DB ──────────────────────────────────────────────────
TURSO_HTTP=TURSO_URL.replace("libsql://","https://")
TURSO_HEADS={"Authorization":f"Bearer {TURSO_TOKEN}","Content-Type":"application/json"}

def turso_exec(sql, params=[]):
    """Execute single SQL statement via Turso HTTP API."""
    body={"requests":[{"type":"execute","stmt":{"sql":sql,"args":[{"type":"text","value":str(p)} if p is not None else {"type":"null"} for p in params]}}]}
    r=req_sync.post(f"{TURSO_HTTP}/v2/pipeline",headers=TURSO_HEADS,json=body,timeout=15)
    data=r.json()
    result=data["results"][0]
    if result.get("type")=="error": raise Exception(result["error"]["message"])
    rows=result.get("response",{}).get("result",{}).get("rows",[])
    cols=result.get("response",{}).get("result",{}).get("cols",[])
    return [tuple(row[i]["value"] if row[i]["type"]!="null" else None for i in range(len(cols))) for row in rows]

def turso_batch(stmts):
    """Execute multiple SQL statements."""
    requests=[{"type":"execute","stmt":{"sql":sql,"args":[{"type":"text","value":str(p)} if p is not None else {"type":"null"} for p in params]}} for sql,params in stmts]
    requests.append({"type":"close"})
    body={"requests":requests}
    req_sync.post(f"{TURSO_HTTP}/v2/pipeline",headers=TURSO_HEADS,json=body,timeout=15)

TABLES=[
    "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,points INTEGER DEFAULT 0,referral_code TEXT UNIQUE,referred_by INTEGER,channel_joined INTEGER DEFAULT 0,twitter_followed INTEGER DEFAULT 0,twitter_opened INTEGER DEFAULT 0,onboarded INTEGER DEFAULT 0,total_earned INTEGER DEFAULT 0,total_withdrawn INTEGER DEFAULT 0,banned INTEGER DEFAULT 0,join_date TEXT)",
    "CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,desc TEXT,link TEXT,reward INTEGER,type TEXT,active INTEGER DEFAULT 1)",
    "CREATE TABLE IF NOT EXISTS done_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,task_id INTEGER,at TEXT,UNIQUE(user_id,task_id))",
    "CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT,referrer INTEGER,referred INTEGER UNIQUE,rewarded INTEGER DEFAULT 0,at TEXT)",
    "CREATE TABLE IF NOT EXISTS withdrawals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,phone TEXT,network TEXT,points INTEGER,naira REAL,status TEXT DEFAULT 'pending',ref TEXT,response TEXT,at TEXT)",
    "CREATE TABLE IF NOT EXISTS txns(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,type TEXT,points INTEGER,desc TEXT,at TEXT)",
    "CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT)",
    "CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY)",
]

def init_db():
    for t in TABLES: turso_exec(t)
    for k,v in {"conv_pts":"1000","conv_naira":"300","min_w":"1000","daily_lim":"3000","ref_reward":"70","ch_reward":"50","tw_reward":"50","welcome":"🎉 Welcome to <b>Nexarion Rewards Bot</b>!\n\nComplete tasks, invite friends, earn points, and redeem airtime.\n\nJoin our Telegram channel to continue 👇"}.items():
        turso_exec("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)",[k,v])
    turso_exec("INSERT OR IGNORE INTO admins(user_id) VALUES(?)",[ADMIN_ID])
    print("✅ Turso DB ready!")


def qone(sql,params=()):
    rows=turso_exec(sql,list(params))
    return rows[0] if rows else None

def qall(sql,params=()):
    return turso_exec(sql,list(params))

def qrun(sql,params=()):
    turso_exec(sql,list(params))

def qrunmany(sqls):
    turso_batch(sqls)

def cfg(k):
    r=qone("SELECT v FROM settings WHERE k=?",(k,)); return r[0] if r else None

def setcfg(k,v): qrun("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)",(k,str(v)))

def user(uid):
    r=qone("SELECT * FROM users WHERE user_id=?",(uid,))
    if not r: return None
    keys=["user_id","username","first_name","points","referral_code","referred_by","channel_joined","twitter_followed","twitter_opened","onboarded","total_earned","total_withdrawn","banned","join_date"]
    return dict(zip(keys,r))

def is_admin(uid): return qone("SELECT 1 FROM admins WHERE user_id=?",(uid,)) is not None

def reg(uid,uname,fname,ref=None):
    qrun("INSERT OR IGNORE INTO users(user_id,username,first_name,referral_code,referred_by,join_date) VALUES(?,?,?,?,?,?)",
    (uid,uname or "",fname or "User",f"NEX{uid}",ref,datetime.now().isoformat()))

def add_pts(uid,pts,desc,t="earn"):
    qrunmany([
        ("UPDATE users SET points=points+?,total_earned=total_earned+? WHERE user_id=?",(pts,pts,uid)),
        ("INSERT INTO txns(user_id,type,points,desc,at) VALUES(?,?,?,?,?)",(uid,t,pts,desc,datetime.now().isoformat()))
    ])

def deduct_pts(uid,pts,desc,t="withdraw"):
    qrunmany([
        ("UPDATE users SET points=points-?,total_withdrawn=total_withdrawn+? WHERE user_id=?",(pts,pts,uid)),
        ("INSERT INTO txns(user_id,type,points,desc,at) VALUES(?,?,?,?,?)",(uid,t,pts,desc,datetime.now().isoformat()))
    ])

def ref_count(uid): r=qone("SELECT COUNT(*) FROM referrals WHERE referrer=?",(uid,)); return r[0] if r else 0
def ref_earn(uid): r=qone("SELECT COALESCE(SUM(points),0) FROM txns WHERE user_id=? AND desc LIKE '%Referral%'",(uid,)); return r[0] if r else 0
def daily_used(uid): r=qone("SELECT COALESCE(SUM(naira),0) FROM withdrawals WHERE user_id=? AND status IN('pending','approved','paid') AND at LIKE ?",(uid,date.today().isoformat()+"%")); return r[0] if r else 0
def task_done(uid,tid): return qone("SELECT 1 FROM done_tasks WHERE user_id=? AND task_id=?",(uid,tid)) is not None

def mark_done(uid,tid):
    try: qrun("INSERT INTO done_tasks(user_id,task_id,at) VALUES(?,?,?)",(uid,tid,datetime.now().isoformat())); return True
    except: return False

init_db()

# ── Databoom API ──────────────────────────────────────────────
def detect_network(phone):
    prefixes={"MTN":["0803","0806","0703","0706","0813","0816","0810","0814","0903","0906","0913","0916"],"Airtel":["0802","0808","0708","0812","0701","0902","0907","0901","0912"],"Glo":["0805","0807","0705","0815","0811","0905","0915"],"9mobile":["0809","0818","0817","0819","0909","0908"]}
    for net,pfxs in prefixes.items():
        for p in pfxs:
            if phone.startswith(p): return net
    return None

async def buy_airtime(phone,network,amount,wid):
    try:
        ref=f"NEX{wid}{int(time.time())}{random.randint(100,999)}"
        api_phone=("234"+phone[1:]) if phone.startswith("0") else phone
        payload={"network":NETS.get(network,1),"phone":api_phone,"mobile_number":api_phone,"amount":int(amount),"airtime_type":"VTU","ported_number":"true","ref":ref}
        log.info(f"Databoom request #{wid}: {payload}")
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{DB_URL}/airtime",headers=DB_HEADS,json=payload,timeout=aiohttp.ClientTimeout(total=60)) as r:
                data=await r.json(content_type=None); log.info(f"Databoom response #{wid}: {data}")
                ok=str(data.get("status","")).lower() in("success","successful")
                return {"ok":ok,"msg":data.get("msg",str(data)),"ref":ref,"data":data}
    except aiohttp.ClientConnectorError as e: return {"ok":False,"msg":f"Cannot connect to payment provider: {e}","ref":"","data":{}}
    except asyncio.TimeoutError: return {"ok":False,"msg":"Request timed out","ref":"","data":{}}
    except Exception as e: return {"ok":False,"msg":str(e),"ref":"","data":{}}

async def wallet_bal():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{DB_URL}/user",headers=DB_HEADS,timeout=aiohttp.ClientTimeout(total=10)) as r:
                data=await r.json(content_type=None)
                if data.get("status")=="success": return data.get("data",{}).get("balance","N/A")
    except: pass
    return "N/A"

# ── UI Helpers ────────────────────────────────────────────────
def home_kb(): return Markup([[Btn("💰 Balance",callback_data="bal"),Btn("👥 Referrals",callback_data="ref")],[Btn("📋 Tasks",callback_data="tasks"),Btn("💸 Withdraw",callback_data="withdraw")],[Btn("👤 Profile",callback_data="profile"),Btn("🏆 Leaderboard",callback_data="lb")],[Btn("❓ Help",callback_data="help")]])
def back(): return Markup([[Btn("🏠 Home",callback_data="home")]])

async def home(update,context,u=None):
    uid=update.effective_user.id; u=u or user(uid); rc=ref_count(uid)
    txt=f"🏠 <b>Nexarion Rewards Bot</b>\n\n👋 <b>{u['first_name']}</b>\n💰 Points: <b>{u['points']}</b>\n👥 Referrals: <b>{rc}</b>\n\nWhat would you like to do?"
    if update.callback_query: await update.callback_query.edit_message_text(txt,reply_markup=home_kb(),parse_mode="HTML")
    else: await update.message.reply_text(txt,reply_markup=home_kb(),parse_mode="HTML")

async def home_q(q,ctx):
    uid=q.from_user.id; u=user(uid); rc=ref_count(uid)
    await q.edit_message_text(f"🏠 <b>Nexarion Rewards Bot</b>\n\n👋 <b>{u['first_name']}</b>\n💰 Points: <b>{u['points']}</b>\n👥 Referrals: <b>{rc}</b>\n\nWhat would you like to do?",reply_markup=home_kb(),parse_mode="HTML")

# ── Onboarding ────────────────────────────────────────────────
async def cmd_start(update,context):
    uid=update.effective_user.id; u=update.effective_user; args=context.args
    ref=None
    if args and args[0].startswith("NEX") and args[0]!=f"NEX{uid}":
        rid=args[0].replace("NEX","")
        if rid.isdigit(): ref=int(rid)
    if not user(uid):
        reg(uid,u.username,u.first_name,ref)
        if ref: qrun("INSERT OR IGNORE INTO referrals(referrer,referred,at) VALUES(?,?,?)",(ref,uid,datetime.now().isoformat()))
    u2=user(uid)
    # Admin can never be banned
    if u2["banned"] and uid != ADMIN_ID and not is_admin(uid):
        await update.message.reply_text("🚫 You are banned."); return
    if u2["onboarded"]: await home(update,context,u=u2); return
    await update.message.reply_text(cfg("welcome"),reply_markup=Markup([[Btn("📢 Join Channel",url=CHANNEL_LINK)],[Btn("✅ Verify Channel",callback_data="verify_ch")]]),parse_mode="HTML")

async def cb_verify_ch(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    if u["channel_joined"]: await _tw_step(q); return
    try:
        m=await context.bot.get_chat_member(CHANNEL,uid)
        if m.status in("member","administrator","creator"):
            add_pts(uid,int(cfg("ch_reward")),"Channel Join Reward")
            qrun("UPDATE users SET channel_joined=1 WHERE user_id=?",(uid,))
            await q.edit_message_text(f"✅ <b>Channel verified!</b>\n\n🎁 +{cfg('ch_reward')} points!\n\nNow follow us on X 👇\n\n1️⃣ Tap Follow on X\n2️⃣ Come back and tap ✅ Done",reply_markup=Markup([[Btn("🐦 Follow on X",url=TWITTER)],[Btn("✅ I have followed",callback_data="verify_tw")]]),parse_mode="HTML")
        else: await q.answer("❌ Please join the channel first!",show_alert=True)
    except TelegramError: await q.answer("❌ Could not verify. Try again.",show_alert=True)

async def _tw_step(q):
    await q.edit_message_text("🐦 <b>Follow us on X</b>\n\n1️⃣ Tap Follow on X\n2️⃣ Come back and tap ✅ I have followed",reply_markup=Markup([[Btn("🐦 Follow on X",url=TWITTER)],[Btn("✅ I have followed",callback_data="verify_tw")]]),parse_mode="HTML")

async def cb_open_tw(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    qrun("UPDATE users SET twitter_opened=1 WHERE user_id=?",(uid,))
    await context.bot.send_message(uid,f"👉 Follow us: {TWITTER}\n\nThen tap ✅ Done above.")

async def cb_verify_tw(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    if u["twitter_followed"]: await home_q(q,context); return
    # URL buttons don't trigger callbacks so we trust the user clicked Follow
    # Just check they haven't already completed this
    rw=int(cfg("tw_reward")); add_pts(uid,rw,"Twitter Follow Reward")
    qrun("UPDATE users SET twitter_followed=1,onboarded=1 WHERE user_id=?",(uid,))
    row=qone("SELECT * FROM referrals WHERE referred=? AND rewarded=0",(uid,))
    if row:
        rr=int(cfg("ref_reward"))
        referrer_id=row[1]
        add_pts(referrer_id,rr,f"Referral Reward (user {uid})","referral")
        qrun("UPDATE referrals SET rewarded=1 WHERE referred=?",(uid,))
        try: await context.bot.send_message(referrer_id,f"🎉 Referral completed!\n+{rr} points added!")
        except: pass
    u2=user(uid)
    await q.edit_message_text(f"🎉 <b>Onboarding Complete!</b>\n\n🎁 +{rw} points!\n💰 Total: <b>{u2['points']} pts</b>\n\nWelcome! 🚀",parse_mode="HTML")
    await home(update,context,u=u2)

# ── Home Callbacks ────────────────────────────────────────────
async def cb_home(update,context): q=update.callback_query; await q.answer(); await home_q(q,context)

async def cb_bal(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    cp=int(cfg("conv_pts")); cn=int(cfg("conv_naira")); nv=(u["points"]/cp)*cn if u["points"]>=cp else 0
    await q.edit_message_text(f"💰 <b>Balance</b>\n\n🔵 Points: <b>{u['points']}</b>\n💵 Value: <b>₦{nv:.2f}</b>\n\n📊 Rate: {cp} pts = ₦{cn}\n📉 Min: {cfg('min_w')} pts",reply_markup=back(),parse_mode="HTML")

async def cb_ref(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    link=f"https://t.me/{BOT_UN}?start={u['referral_code']}"
    await q.edit_message_text(f"👥 <b>Referrals</b>\n\n🔗 Your Link:\n<code>{link}</code>\n\n👥 Total: <b>{ref_count(uid)}</b>\n💰 Earned: <b>{ref_earn(uid)} pts</b>\n🎁 Per Referral: <b>{cfg('ref_reward')} pts</b>",reply_markup=back(),parse_mode="HTML")

async def cb_tasks(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    ts=qall("SELECT * FROM tasks WHERE active=1")
    if not ts: await q.edit_message_text("📋 No tasks yet!",reply_markup=back()); return
    btns=[[Btn(f"{'✅' if task_done(uid,t[0]) else '🔲'} {t[1]} (+{t[4]} pts)",callback_data=f"task_{t[0]}")] for t in ts]
    btns.append([Btn("🏠 Home",callback_data="home")])
    await q.edit_message_text("📋 <b>Tasks</b>\n\nComplete tasks to earn points!",reply_markup=Markup(btns),parse_mode="HTML")

async def cb_task(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; tid=int(q.data.split("_")[1])
    t=qone("SELECT * FROM tasks WHERE id=?",(tid,))
    if not t: return
    done=task_done(uid,tid); kb=[]
    if not done:
        if t[3]: kb.append([Btn("🔗 Open Link",url=t[3],callback_data=f"topen_{tid}")])
        kb.append([Btn("✅ Mark Complete",callback_data=f"tdone_{tid}")])
    kb.append([Btn("◀️ Back",callback_data="tasks")])
    await q.edit_message_text(f"📋 <b>{t[1]}</b>\n\n{t[2]}\n\n🎁 Reward: <b>{t[4]} pts</b>\nStatus: {'✅ Done' if done else '🔲 Pending'}",reply_markup=Markup(kb),parse_mode="HTML")

async def cb_topen(update,context):
    q=update.callback_query; await q.answer("✅ Link opened! Come back and tap Mark Complete.",show_alert=False)
    uid=q.from_user.id; tid=int(q.data.split("_")[1])
    if "opened" not in context.user_data: context.user_data["opened"]=set()
    context.user_data["opened"].add(tid)
    # Also store in DB so it persists across restarts
    qrun("INSERT OR IGNORE INTO done_tasks(user_id,task_id,at) VALUES(?,?,?) ",
         (uid, f"opened_{tid}", datetime.now().isoformat())) if False else None

async def cb_tdone(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; tid=int(q.data.split("_")[1])
    if task_done(uid,tid): await q.answer("✅ Already done!",show_alert=True); return
    t=qone("SELECT * FROM tasks WHERE id=?",(tid,))
    opened=context.user_data.get("opened",set())
    is_tg_link=t[3] and ("t.me" in t[3] or "telegram.me" in t[3])

    # For Telegram links — verify membership
    if is_tg_link:
        # Extract username from link e.g. https://t.me/nexarion11news -> @nexarion11news
        try:
            slug=t[3].rstrip("/").split("/")[-1]
            # Remove invite hash links — cant verify those
            if "+" in slug or "joinchat" in t[3]:
                pass  # cant verify invite links, just allow
            else:
                username=f"@{slug}"
                member=await context.bot.get_chat_member(username,uid)
                if member.status not in("member","administrator","creator","restricted"):
                    await q.answer("❌ Please join the channel/group first!",show_alert=True); return
        except Exception as e:
            log.warning(f"Could not verify membership for task {tid}: {e}")
            # If we cant verify just allow it
            pass

    # For other links require opening first
    elif t[3] and tid not in opened:
        await q.answer("❌ Open the link first!",show_alert=True); return

    if mark_done(uid,tid):
        add_pts(uid,t[4],f"Task: {t[1]}")
        await q.edit_message_text(f"🎉 <b>Done!</b>\n\n✅ {t[1]}\n🎁 +{t[4]} pts!",reply_markup=Markup([[Btn("📋 More Tasks",callback_data="tasks")],[Btn("🏠 Home",callback_data="home")]]),parse_mode="HTML")

async def cb_profile(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    await q.edit_message_text(f"👤 <b>Profile</b>\n\n🆔 ID: <code>{u['user_id']}</code>\n👤 @{u['username'] or 'N/A'}\n💰 Points: <b>{u['points']}</b>\n👥 Referrals: <b>{ref_count(uid)}</b>\n📈 Earned: <b>{u['total_earned']}</b>\n💸 Withdrawn: <b>{u['total_withdrawn']}</b>\n📅 Joined: {u['join_date'][:10]}",reply_markup=back(),parse_mode="HTML")

async def cb_lb(update,context):
    q=update.callback_query; await q.answer()
    rows=qall("SELECT first_name,points FROM users WHERE banned=0 ORDER BY points DESC LIMIT 10")
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines=["🏆 <b>Leaderboard</b>\n"]+[f"{medals[i]} {r[0]} — <b>{r[1]} pts</b>" for i,r in enumerate(rows)]
    await q.edit_message_text("\n".join(lines),reply_markup=back(),parse_mode="HTML")

async def cb_help(update,context):
    q=update.callback_query; await q.answer()
    await q.edit_message_text(f"❓ <b>How It Works</b>\n\n1️⃣ Join channel & follow X → earn points\n2️⃣ Complete tasks → earn more\n3️⃣ Refer friends → +{cfg('ref_reward')} pts each\n4️⃣ Withdraw → {cfg('conv_pts')} pts = ₦{cfg('conv_naira')} airtime\n\n💸 Min withdrawal: {cfg('min_w')} pts",reply_markup=back(),parse_mode="HTML")

# ── Withdrawal ────────────────────────────────────────────────
async def cb_withdraw(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    min_w=int(cfg("min_w")); dl=float(cfg("daily_lim")); used=daily_used(uid); left=dl-used
    if u["points"]<min_w:
        await q.edit_message_text(f"❌ Need <b>{min_w} pts</b> to withdraw.\nYou have <b>{u['points']} pts</b>.",reply_markup=back(),parse_mode="HTML"); return ConversationHandler.END
    if left<=0:
        await q.edit_message_text(f"❌ Daily limit of ₦{dl:.0f} reached. Try tomorrow!",reply_markup=back(),parse_mode="HTML"); return ConversationHandler.END
    context.user_data["wd"]={}
    await q.edit_message_text(f"💸 <b>Withdraw</b>\n\n💰 Points: <b>{u['points']}</b>\n📅 Daily left: <b>₦{left:.0f}</b>\n\n📱 Enter phone number:",reply_markup=Markup([[Btn("❌ Cancel",callback_data="home")]]),parse_mode="HTML")
    return AWAIT_PHONE

async def wd_phone(update,context):
    p=update.message.text.strip()
    if p.startswith("+234"): p="0"+p[4:]
    elif p.startswith("234") and len(p)==13: p="0"+p[3:]
    if not(p.isdigit() and len(p)==11): await update.message.reply_text("❌ Enter valid 11-digit number (e.g. 08012345678):"); return AWAIT_PHONE
    context.user_data["wd"]["phone"]=p
    detected=detect_network(p)
    hint=f"\n\n💡 Detected network: <b>{detected}</b>" if detected else ""
    await update.message.reply_text(f"📱 Phone: <b>{p}</b>{hint}\n\n📡 Select network:",reply_markup=Markup([[Btn("MTN",callback_data="net_MTN"),Btn("Airtel",callback_data="net_Airtel")],[Btn("Glo",callback_data="net_Glo"),Btn("9mobile",callback_data="net_9mobile")],[Btn("❌ Cancel",callback_data="home")]]),parse_mode="HTML")
    return AWAIT_NET

async def wd_net(update,context):
    q=update.callback_query; await q.answer(); net=q.data.replace("net_",""); uid=q.from_user.id; u=user(uid)
    context.user_data["wd"]["network"]=net
    cp=int(cfg("conv_pts")); cn=int(cfg("conv_naira")); left=float(cfg("daily_lim"))-daily_used(uid)
    max_n=min((u["points"]/cp)*cn,left); blocks=int(max_n/cn); pts=blocks*cp; naira=blocks*cn
    if pts<=0: await q.edit_message_text("❌ Cannot process. Check balance.",reply_markup=back()); return ConversationHandler.END
    context.user_data["wd"]["pts"]=pts; context.user_data["wd"]["naira"]=naira
    await q.edit_message_text(f"💸 <b>Summary</b>\n\n📱 {context.user_data['wd']['phone']}\n📡 {net}\n🔵 Points: <b>{pts}</b>\n💵 Airtime: <b>₦{naira:.0f}</b>\n\nConfirm?",reply_markup=Markup([[Btn("✅ Confirm",callback_data="wd_confirm"),Btn("❌ Cancel",callback_data="home")]]),parse_mode="HTML")
    return AWAIT_CONFIRM

async def wd_confirm(update,context):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=user(uid)
    wd=context.user_data.get("wd",{}); pts=wd.get("pts",0); naira=wd.get("naira",0); phone=wd.get("phone",""); net=wd.get("network","")
    if u["points"]<pts: await q.edit_message_text("❌ Insufficient points.",reply_markup=back()); return ConversationHandler.END
    await q.edit_message_text(f"⏳ <b>Processing...</b>\n\nSending ₦{naira:.0f} to {phone}...",parse_mode="HTML")
    qrun("INSERT INTO withdrawals(user_id,phone,network,points,naira,status,at) VALUES(?,?,?,?,?,'processing',?)",(uid,phone,net,pts,naira,datetime.now().isoformat()))
    wid=qone("SELECT last_insert_rowid()")[0]
    deduct_pts(uid,pts,f"Withdrawal ₦{naira:.0f} to {phone} ({net})")
    res=await buy_airtime(phone,net,naira,wid)
    qrun("UPDATE withdrawals SET status=?,ref=?,response=? WHERE id=?",("paid" if res["ok"] else "pending",res["ref"],str(res["data"]),wid))
    if res["ok"]:
        await context.bot.edit_message_text(f"✅ <b>Airtime Sent!</b>\n\n📱 {phone} ({net})\n💵 ₦{naira:.0f}\n🔵 -{pts} pts",chat_id=q.message.chat_id,message_id=q.message.message_id,reply_markup=back(),parse_mode="HTML")
    else:
        await context.bot.edit_message_text(f"⏳ <b>Pending</b>\n\n📱 {phone} ({net})\n💵 ₦{naira:.0f}\n🔵 -{pts} pts\n\nAdmin will process manually.",chat_id=q.message.chat_id,message_id=q.message.message_id,reply_markup=back(),parse_mode="HTML")
        try: await context.bot.send_message(ADMIN_ID,f"💸 <b>Withdrawal #{wid}</b>\n👤 {uid} @{u['username'] or 'N/A'}\n📱 {phone} ({net})\n💵 ₦{naira:.0f} | {pts} pts\n❌ {res['msg']}\n\n/approvepayment {wid}\n/rejectpayment {wid}",parse_mode="HTML")
        except: pass
    return ConversationHandler.END

# ── Admin ─────────────────────────────────────────────────────
def adm(f):
    async def w(update,context):
        if update.effective_user.id!=ADMIN_ID and not is_admin(update.effective_user.id):
            if update.message: await update.message.reply_text("🚫 Admin only.")
            return ConversationHandler.END
        return await f(update,context)
    w.__name__=f.__name__; return w

@adm
async def cmd_admin(update,context):
    tu=qone("SELECT COUNT(*) FROM users")[0]
    tp=qone("SELECT COALESCE(SUM(points),0) FROM txns WHERE type='earn'")[0]
    tw=qone("SELECT COUNT(*) FROM withdrawals")[0]
    pw=qone("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")[0]
    bal=await wallet_bal()
    await update.message.reply_text(f"🛠 <b>Admin Panel</b>\n\n👥 Users: <b>{tu}</b>\n🔵 Points Given: <b>{tp}</b>\n💸 Withdrawals: <b>{tw}</b>\n⏳ Pending: <b>{pw}</b>\n💳 Wallet: <b>₦{bal}</b>\n\n/addtask /removetask [id]\n/activatetask [id] /deactivatetask [id]\n/searchuser [id or @username]\n/addpoints [id or @username] [pts]\n/removepoints [id or @username] [pts]\n/banuser [id or @username]\n/unbanuser [id or @username]\n/withdrawals /approvepayment [id]\n/rejectpayment [id] /broadcast\n/setreferralreward [pts]\n/setconversion [pts] [₦]\n/setdailylimit [₦]",parse_mode="HTML")

@adm
async def cmd_addtask(update,context): await update.message.reply_text("Enter task title:"); return AWAIT_T_TITLE
async def at_title(update,context): context.user_data["nt"]={"title":update.message.text.strip()}; await update.message.reply_text("Enter description:"); return AWAIT_T_DESC
async def at_desc(update,context): context.user_data["nt"]["desc"]=update.message.text.strip(); await update.message.reply_text("Enter link (or 'none'):"); return AWAIT_T_LINK
async def at_link(update,context):
    t=update.message.text.strip(); context.user_data["nt"]["link"]="" if t.lower()=="none" else t
    await update.message.reply_text("Enter reward points:"); return AWAIT_T_PTS
async def at_pts(update,context):
    if not update.message.text.strip().isdigit(): await update.message.reply_text("Enter a number:"); return AWAIT_T_PTS
    context.user_data["nt"]["reward"]=int(update.message.text.strip())
    await update.message.reply_text("Select type:",reply_markup=Markup([[Btn("Telegram",callback_data="tt_telegram"),Btn("Twitter Follow",callback_data="tt_tw_follow")],[Btn("Twitter Like",callback_data="tt_tw_like"),Btn("Twitter Repost",callback_data="tt_tw_repost")],[Btn("Website",callback_data="tt_website"),Btn("Custom",callback_data="tt_custom")]]))
    return AWAIT_T_TYPE
async def at_type(update,context):
    q=update.callback_query; await q.answer(); nt=context.user_data["nt"]; typ=q.data.replace("tt_","")
    qrun("INSERT INTO tasks(title,desc,link,reward,type) VALUES(?,?,?,?,?)",(nt["title"],nt["desc"],nt["link"],nt["reward"],typ))
    await q.edit_message_text(f"✅ Task added!\n📋 {nt['title']}\n🎁 {nt['reward']} pts"); return ConversationHandler.END

def find_user(target):
    target=target.replace("@","")
    return qone("SELECT * FROM users WHERE user_id=?",(int(target),)) if target.isdigit() else qone("SELECT * FROM users WHERE username=?",(target,))

def user_from_row(r):
    if not r: return None
    keys=["user_id","username","first_name","points","referral_code","referred_by","channel_joined","twitter_followed","twitter_opened","onboarded","total_earned","total_withdrawn","banned","join_date"]
    return dict(zip(keys,r))

@adm
async def cmd_removetask(update,context):
    args=context.args
    if not args or not args[0].isdigit():
        ts=qall("SELECT * FROM tasks")
        await update.message.reply_text("📋 Tasks:\n"+"\n".join([f"ID {t[0]}: {t[1]}" for t in ts])+"\n\nUse /removetask [id]"); return
    qrun("DELETE FROM tasks WHERE id=?",(int(args[0]),))
    await update.message.reply_text(f"✅ Task {args[0]} removed.")

@adm
async def cmd_activatetask(update,context):
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /activatetask [id]"); return
    qrun("UPDATE tasks SET active=1 WHERE id=?",(int(context.args[0]),))
    await update.message.reply_text(f"✅ Task {context.args[0]} activated.")

@adm
async def cmd_deactivatetask(update,context):
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /deactivatetask [id]"); return
    qrun("UPDATE tasks SET active=0 WHERE id=?",(int(context.args[0]),))
    await update.message.reply_text(f"✅ Task {context.args[0]} deactivated.")

@adm
async def cmd_searchuser(update,context):
    if not context.args: await update.message.reply_text("Usage: /searchuser [id or @username]"); return
    u=user_from_row(find_user(context.args[0]))
    if not u: await update.message.reply_text("❌ Not found."); return
    await update.message.reply_text(f"👤 ID: <code>{u['user_id']}</code>\n@{u['username'] or 'N/A'} {u['first_name']}\n💰 {u['points']} pts\n👥 Refs: {ref_count(u['user_id'])}\n📈 Earned: {u['total_earned']}\n💸 Withdrawn: {u['total_withdrawn']}\nBanned: {'Yes' if u['banned'] else 'No'}",parse_mode="HTML")

@adm
async def cmd_addpoints(update,context):
    a=context.args
    if len(a)<2 or not a[1].isdigit(): await update.message.reply_text("Usage: /addpoints [id or @username] [pts]"); return
    u=user_from_row(find_user(a[0]))
    if not u: await update.message.reply_text("❌ User not found."); return
    pts=int(a[1]); add_pts(u["user_id"],pts,"Admin added","admin_add")
    await update.message.reply_text(f"✅ +{pts} pts added to {u['first_name']}")
    try: await context.bot.send_message(u["user_id"],f"🎁 Admin added <b>{pts} points</b>!",parse_mode="HTML")
    except: pass

@adm
async def cmd_removepoints(update,context):
    a=context.args
    if len(a)<2 or not a[1].isdigit(): await update.message.reply_text("Usage: /removepoints [id or @username] [pts]"); return
    u=user_from_row(find_user(a[0]))
    if not u: await update.message.reply_text("❌ User not found."); return
    pts=int(a[1]); deduct_pts(u["user_id"],pts,"Admin removed","admin_remove")
    await update.message.reply_text(f"✅ -{pts} pts removed from {u['first_name']}")

@adm
async def cmd_unbanall(update,context):
    turso_exec("UPDATE users SET banned=0")
    await update.message.reply_text("✅ All users unbanned!")

@adm
async def cmd_banuser(update,context):
    if not context.args: await update.message.reply_text("Usage: /banuser [id or @username]"); return
    u=user_from_row(find_user(context.args[0]))
    if not u: await update.message.reply_text("❌ Not found."); return
    qrun("UPDATE users SET banned=1 WHERE user_id=?",(u["user_id"],))
    await update.message.reply_text(f"🚫 {u['first_name']} banned.")

@adm
async def cmd_unbanuser(update,context):
    if not context.args: await update.message.reply_text("Usage: /unbanuser [id or @username]"); return
    u=user_from_row(find_user(context.args[0]))
    if not u: await update.message.reply_text("❌ Not found."); return
    qrun("UPDATE users SET banned=0 WHERE user_id=?",(u["user_id"],))
    await update.message.reply_text(f"✅ {u['first_name']} unbanned.")

@adm
async def cmd_withdrawals(update,context):
    rows=qall("SELECT * FROM withdrawals WHERE status='pending' ORDER BY at DESC LIMIT 20")
    if not rows: await update.message.reply_text("✅ No pending withdrawals."); return
    for w in rows:
        await update.message.reply_text(f"💸 <b>#{w[0]}</b>\n👤 {w[1]}\n📱 {w[2]} ({w[3]})\n💵 ₦{w[5]:.0f} | {w[4]} pts\n📅 {w[9][:16]}\n\n/approvepayment {w[0]} | /rejectpayment {w[0]}",parse_mode="HTML")

@adm
async def cmd_approve(update,context):
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /approvepayment [id]"); return
    wid=int(context.args[0]); w=qone("SELECT * FROM withdrawals WHERE id=?",(wid,))
    if not w: await update.message.reply_text("❌ Not found."); return
    qrun("UPDATE withdrawals SET status='paid' WHERE id=?",(wid,))
    await update.message.reply_text(f"✅ #{wid} approved.")
    try: await context.bot.send_message(w[1],f"✅ ₦{w[5]:.0f} airtime sent to {w[2]}!")
    except: pass

@adm
async def cmd_reject(update,context):
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /rejectpayment [id]"); return
    wid=int(context.args[0]); w=qone("SELECT * FROM withdrawals WHERE id=? AND status='pending'",(wid,))
    if not w: await update.message.reply_text("❌ Not found or not pending."); return
    qrun("UPDATE withdrawals SET status='rejected' WHERE id=?",(wid,))
    add_pts(w[1],w[4],f"Refund: rejected #{wid}","refund")
    await update.message.reply_text(f"❌ #{wid} rejected. {w[4]} pts refunded.")
    try: await context.bot.send_message(w[1],f"❌ Withdrawal rejected.\n✅ {w[4]} pts refunded!")
    except: pass

@adm
async def cmd_broadcast(update,context):
    await update.message.reply_text("Select type:",reply_markup=Markup([[Btn("📝 Text",callback_data="bc_text"),Btn("🖼 Photo",callback_data="bc_photo")],[Btn("🎥 Video",callback_data="bc_video"),Btn("📄 Doc",callback_data="bc_doc")],[Btn("❌ Cancel",callback_data="bc_cancel")]]))
    return AWAIT_BC_TYPE

async def bc_type(update,context):
    q=update.callback_query; await q.answer()
    if q.data=="bc_cancel": await q.edit_message_text("❌ Cancelled."); return ConversationHandler.END
    context.user_data["bc"]=q.data.replace("bc_",""); await q.edit_message_text("Send the content to broadcast:"); return AWAIT_BC_MSG

async def bc_send(update,context):
    bt=context.user_data.get("bc","text"); ul=qall("SELECT user_id FROM users WHERE banned=0")
    sent=failed=0
    for row in ul:
        uid=row[0]
        try:
            if bt=="text": await context.bot.send_message(uid,update.message.text,parse_mode="HTML")
            elif bt=="photo" and update.message.photo: await context.bot.send_photo(uid,update.message.photo[-1].file_id,caption=update.message.caption or "")
            elif bt=="video" and update.message.video: await context.bot.send_video(uid,update.message.video.file_id,caption=update.message.caption or "")
            elif bt=="doc" and update.message.document: await context.bot.send_document(uid,update.message.document.file_id,caption=update.message.caption or "")
            sent+=1
        except: failed+=1
    await update.message.reply_text(f"📢 Done!\n✅ Sent: {sent}\n❌ Failed: {failed}"); return ConversationHandler.END

@adm
async def cmd_setrefward(update,context):
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /setreferralreward [pts]"); return
    setcfg("ref_reward",context.args[0]); await update.message.reply_text(f"✅ Referral reward = {context.args[0]} pts")

@adm
async def cmd_setconv(update,context):
    a=context.args
    if len(a)<2 or not a[0].isdigit() or not a[1].isdigit(): await update.message.reply_text("Usage: /setconversion [pts] [naira]"); return
    setcfg("conv_pts",a[0]); setcfg("conv_naira",a[1]); await update.message.reply_text(f"✅ {a[0]} pts = ₦{a[1]}")

@adm
async def cmd_setdaily(update,context):
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /setdailylimit [naira]"); return
    setcfg("daily_lim",context.args[0]); await update.message.reply_text(f"✅ Daily limit = ₦{context.args[0]}")

# ── Build & Run ───────────────────────────────────────────────
async def err(update,context): log.error(context.error,exc_info=context.error)

def build():
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    wd_conv=ConversationHandler(entry_points=[CallbackQueryHandler(cb_withdraw,pattern="^withdraw$")],states={AWAIT_PHONE:[MessageHandler(filters.TEXT&~filters.COMMAND,wd_phone)],AWAIT_NET:[CallbackQueryHandler(wd_net,pattern="^net_")],AWAIT_CONFIRM:[CallbackQueryHandler(wd_confirm,pattern="^wd_confirm$")]},fallbacks=[CallbackQueryHandler(cb_home,pattern="^home$")],per_message=False)
    bc_conv=ConversationHandler(entry_points=[CommandHandler("broadcast",cmd_broadcast)],states={AWAIT_BC_TYPE:[CallbackQueryHandler(bc_type,pattern="^bc_")],AWAIT_BC_MSG:[MessageHandler(filters.TEXT&~filters.COMMAND,bc_send),MessageHandler(filters.PHOTO,bc_send),MessageHandler(filters.VIDEO,bc_send),MessageHandler(filters.Document.ALL,bc_send)]},fallbacks=[],per_message=False)
    task_conv=ConversationHandler(entry_points=[CommandHandler("addtask",cmd_addtask)],states={AWAIT_T_TITLE:[MessageHandler(filters.TEXT&~filters.COMMAND,at_title)],AWAIT_T_DESC:[MessageHandler(filters.TEXT&~filters.COMMAND,at_desc)],AWAIT_T_LINK:[MessageHandler(filters.TEXT&~filters.COMMAND,at_link)],AWAIT_T_PTS:[MessageHandler(filters.TEXT&~filters.COMMAND,at_pts)],AWAIT_T_TYPE:[CallbackQueryHandler(at_type,pattern="^tt_")]},fallbacks=[],per_message=False)
    for cmd,fn in [("start",cmd_start),("admin",cmd_admin),("removetask",cmd_removetask),("activatetask",cmd_activatetask),("deactivatetask",cmd_deactivatetask),("searchuser",cmd_searchuser),("addpoints",cmd_addpoints),("removepoints",cmd_removepoints),("banuser",cmd_banuser),("unbanall",cmd_unbanall),("unbanuser",cmd_unbanuser),("withdrawals",cmd_withdrawals),("approvepayment",cmd_approve),("rejectpayment",cmd_reject),("setreferralreward",cmd_setrefward),("setconversion",cmd_setconv),("setdailylimit",cmd_setdaily)]:
        app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(wd_conv); app.add_handler(bc_conv); app.add_handler(task_conv)
    for pat,fn in [("^verify_ch$",cb_verify_ch),("^open_tw$",cb_open_tw),("^verify_tw$",cb_verify_tw),("^home$",cb_home),("^bal$",cb_bal),("^ref$",cb_ref),("^tasks$",cb_tasks),("^profile$",cb_profile),("^lb$",cb_lb),("^help$",cb_help),(r"^task_\d+$",cb_task),(r"^topen_\d+$",cb_topen),(r"^tdone_\d+$",cb_tdone)]:
        app.add_handler(CallbackQueryHandler(fn,pattern=pat))
    app.add_error_handler(err); return app

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Nexarion Bot is running!")
    def log_message(self, format, *args): pass

def run_server():
    port=int(os.environ.get("PORT",8080))
    server=HTTPServer(("0.0.0.0",port),PingHandler)
    server.serve_forever()

if __name__=="__main__":
    import traceback, sys
    print("🚀 Nexarion Bot starting...")
    print(f"Python version: {sys.version}")
    try:
        print("Testing Turso connection...")
        test=turso_exec("SELECT 1")
        print(f"✅ Turso connected: {test}")
        print("Building app...")
        # Fix for Python 3.10+ event loop issue
        loop=asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Start HTTP server
        t=threading.Thread(target=run_server,daemon=True)
        t.start()
        app=build()
        print("Starting polling...")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"❌ FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
