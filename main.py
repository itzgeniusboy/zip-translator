import asyncio
import json
import os
from datetime import datetime, time as dtime
from telethon import TelegramClient, events, Button

# ================= CONFIGURATION =================
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'
BOT_TOKEN = '8918032442:AAF4kZgCz7ZMC8eAfcpr-f1qr4bTjfs_YyI'

OWNER_ID = 1969067694
CHECK_INTERVAL = 60          # scheduler tick, in seconds
DEFAULT_INTERVAL_MIN = 60    # fallback ad interval if user doesn't set one

DB_FILE = "commercial_db.json"
MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

user_states = {}       # {user_id: {"step": str, "data": dict}}
pending_actions = {}   # {user_id: {"label": str}}  -> awaiting override confirm
last_ad_messages = {}  # {"<ad_id>:<channel>": msg_id}

MAIN_MENU = [
    [Button.text("➕ Add Ad"), Button.text("📋 My Ads")],
    [Button.text("🗑️ Delete Ad")],
    [Button.text("📢 Add Channel"), Button.text("📊 My Channels")],
    [Button.text("📈 A/B Results")],
    [Button.text("🟢 Start Loop"), Button.text("🔴 Stop Loop")],
]

# ================= SECURE JSON ENGINE =================
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


client = TelegramClient('ad_scheduler_session', API_ID, API_HASH)


# ================= TIME HELPERS =================
def parse_hhmm(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def in_active_window(ad, now):
    """True if 'now' falls inside the ad's configured posting hours (or ad has no window)."""
    start, end = ad.get("start_hour"), ad.get("end_hour")
    if not start or not end:
        return True
    try:
        s, e = parse_hhmm(start), parse_hhmm(end)
    except Exception:
        return True
    n = now.time()
    if s <= e:
        return s <= n <= e
    return n >= s or n <= e  # overnight window, e.g. 22:00-06:00


def ad_is_due(ad, now):
    next_due = ad.get("next_due")
    if not next_due:
        return True
    try:
        return now >= datetime.fromisoformat(next_due)
    except Exception:
        return True


# ================= AD ROTATION ENGINE =================
async def commercial_ad_loop():
    await asyncio.sleep(5)
    while True:
        now = datetime.now()
        current_db = load_db()

        for user_id, user_data in current_db.items():
            if not user_data.get("loop_active", False):
                continue

            user_channels = user_data.get("channels", [])
            if not user_channels:
                continue

            changed = False
            for ad in user_data.get("ads", []):
                if not in_active_window(ad, now):
                    continue
                if not ad_is_due(ad, now):
                    continue

                for channel in user_channels:
                    key = f"{ad['id']}:{channel}"
                    if key in last_ad_messages:
                        try:
                            await client.delete_messages(channel, last_ad_messages[key])
                        except Exception:
                            pass
                    try:
                        buttons = Button.inline(ad["btn_text"], data=f"click:{ad['id']}".encode())
                        if ad.get("media_path") and os.path.exists(ad["media_path"]):
                            new_msg = await client.send_file(
                                channel, ad["media_path"], caption=ad["text"], buttons=buttons
                            )
                        else:
                            new_msg = await client.send_message(channel, ad["text"], buttons=buttons)
                        last_ad_messages[key] = new_msg.id
                        ad["views"] = ad.get("views", 0) + 1
                    except Exception as e:
                        print(f"Post error for {channel} (ad {ad['id']}, user {user_id}): {e}")

                interval = ad.get("interval_minutes", DEFAULT_INTERVAL_MIN)
                ad["next_due"] = datetime.fromtimestamp(now.timestamp() + interval * 60).isoformat()
                changed = True

            if changed:
                current_db[user_id]["ads"] = user_data["ads"]

        save_db(current_db)
        await asyncio.sleep(CHECK_INTERVAL)


# ================= HELPERS =================
def user_is_busy(user_id):
    return user_id in user_states


def start_flow(user_id, step, data=None):
    user_states[user_id] = {"step": step, "data": data or {}}


def clear_flow(user_id):
    user_states.pop(user_id, None)


MENU_ACTIONS = {
    "➕ Add Ad": lambda uid: start_flow(uid, "w_text"),
    "🗑️ Delete Ad": lambda uid: start_flow(uid, "w_del"),
    "📢 Add Channel": lambda uid: start_flow(uid, "w_chan"),
}

MENU_PROMPTS = {
    "➕ Add Ad": "📝 **Send the caption text for your new ad:**",
    "🗑️ Delete Ad": "🔢 **Send the Campaign ID you want to delete:**",
    "📢 Add Channel": "📣 **Send the target channel username (must start with @):**\nExample: `@your_channel`",
}


# ================= MAIN PANEL =================
@client.on(events.NewMessage(pattern=r'/start|/admin'))
async def user_panel(event):
    user_id = str(event.sender_id)
    current_db = load_db()

    if user_id not in current_db:
        current_db[user_id] = {"channels": [], "ads": [], "loop_active": False}
        save_db(current_db)

    clear_flow(user_id)
    pending_actions.pop(user_id, None)

    welcome_text = (
        "💎 **Ad Management Console** 💎\n\n"
        "Welcome to your private, multi-channel ad scheduler.\n\n"
        "✨ Each ad now runs on its **own interval and posting hours**, supports **photo/video**, "
        "and can be tagged into an **A/B test group** for performance comparison.\n\n"
        "⚙️ Use the menu below to get started:"
    )
    await event.reply(welcome_text, buttons=MAIN_MENU)


# ================= CALLBACKS =================
@client.on(events.CallbackQuery())
async def handle_callback(event):
    user_id = str(event.sender_id)
    data = event.data.decode("utf-8")
    current_db = load_db()

    if user_id not in current_db and not data.startswith("click:"):
        await event.answer("Please send /start first.", alert=True)
        return

    # ---- Ad click tracking (fires for whoever clicks, not just the owner) ----
    if data.startswith("click:"):
        ad_id = int(data.split(":")[1])
        for uid, udata in current_db.items():
            for ad in udata.get("ads", []):
                if ad["id"] == ad_id:
                    ad["clicks"] = ad.get("clicks", 0) + 1
                    save_db(current_db)
                    try:
                        await event.answer(url=ad["btn_url"])
                    except Exception:
                        await event.answer(f"Link: {ad['btn_url']}", alert=True)
                    return
        await event.answer("Link unavailable.", alert=True)
        return

    if data == "confirm_override":
        pending = pending_actions.pop(user_id, None)
        if not pending:
            await event.edit("⚠️ This confirmation has expired.")
            return
        clear_flow(user_id)
        label = pending["label"]
        MENU_ACTIONS[label](user_id)
        await event.edit(f"✅ Previous action cancelled.\n\n{MENU_PROMPTS[label]}")
        return

    if data == "cancel_override":
        pending_actions.pop(user_id, None)
        await event.edit("👍 Kept your current action. Please finish it before starting a new one.")
        return

    if data.startswith("confirm_delete:"):
        ad_id = int(data.split(":")[1])
        ads = current_db[user_id].get("ads", [])
        updated = [a for a in ads if a["id"] != ad_id]
        for i, a in enumerate(updated):
            a["id"] = i + 1
        current_db[user_id]["ads"] = updated
        save_db(current_db)
        await event.edit(f"🗑️ **Deleted.** Campaign ID `{ad_id}` has been removed.")
        return

    if data == "cancel_delete":
        await event.edit("👍 Deletion cancelled.")
        return

    if data == "confirm_start_loop":
        current_db[user_id]["loop_active"] = True
        save_db(current_db)
        await event.edit("🟢 **Scheduler started.** Ads will post based on each ad's own interval and hours.")
        return

    if data == "confirm_stop_loop":
        current_db[user_id]["loop_active"] = False
        save_db(current_db)
        await event.edit("🔴 **Scheduler stopped.**")
        return

    if data == "cancel_generic":
        await event.edit("👍 Action cancelled.")
        return


# ================= TEXT / STEP ROUTING =================
@client.on(events.NewMessage())
async def handle_commercial_inputs(event):
    user_id = str(event.sender_id)
    text = (event.raw_text or "").strip()

    current_db = load_db()
    if user_id not in current_db:
        return

    is_menu_button = text in MENU_ACTIONS

    if is_menu_button and user_is_busy(user_id):
        pending_actions[user_id] = {"label": text}
        await event.reply(
            "⚠️ **You have an unfinished action in progress.**\n\nStarting a new one will cancel it. Continue?",
            buttons=[[Button.inline("✅ Yes, cancel and continue", b"confirm_override"),
                      Button.inline("❌ No, keep current", b"cancel_override")]]
        )
        return

    # ---- STEP ROUTING ----
    if user_id in user_states:
        state = user_states[user_id]["step"]
        sdata = user_states[user_id]["data"]

        if state == "w_chan":
            if not text.startswith("@"):
                await event.reply("❌ **Invalid format.** Username must start with `@`. Try again:")
                return
            if text not in current_db[user_id]["channels"]:
                current_db[user_id]["channels"].append(text)
                save_db(current_db)
            clear_flow(user_id)
            await event.reply(f"✅ **Channel linked.** `{text}` added.\n⚠️ Make sure the bot is an *admin* there.")
            return

        elif state == "w_text":
            sdata["text"] = text
            user_states[user_id]["step"] = "w_media"
            await event.reply("🖼️ **Send a photo/video for this ad, or type /skip for text-only:**")
            return

        elif state == "w_media":
            if text == "/skip":
                sdata["media_path"] = None
                sdata["media_type"] = None
            elif event.photo or event.video:
                ext = "jpg" if event.photo else "mp4"
                path = os.path.join(MEDIA_DIR, f"{user_id}_{int(datetime.now().timestamp())}.{ext}")
                await event.download_media(file=path)
                sdata["media_path"] = path
                sdata["media_type"] = "photo" if event.photo else "video"
            else:
                await event.reply("⚠️ Send a photo, a video, or type /skip:")
                return
            user_states[user_id]["step"] = "w_btn_text"
            await event.reply("🔘 **Now send the button label:**\n(e.g., `⚡ Join Premium`)")
            return

        elif state == "w_btn_text":
            sdata["btn_text"] = text
            user_states[user_id]["step"] = "w_btn_url"
            await event.reply("🔗 **Now send the destination URL for the button:**")
            return

        elif state == "w_btn_url":
            if not text.startswith("http"):
                await event.reply("❌ **Invalid link.** Must start with `http://` or `https://`. Try again:")
                return
            sdata["btn_url"] = text
            user_states[user_id]["step"] = "w_interval"
            await event.reply(f"⏱️ **How often should this ad repost?**\nSend minutes (e.g. `30`), or /skip for default ({DEFAULT_INTERVAL_MIN} min):")
            return

        elif state == "w_interval":
            if text == "/skip":
                sdata["interval_minutes"] = DEFAULT_INTERVAL_MIN
            else:
                try:
                    val = int(text)
                    if val < 1:
                        raise ValueError
                    sdata["interval_minutes"] = val
                except ValueError:
                    await event.reply("⚠️ Send a valid number of minutes, or /skip:")
                    return
            user_states[user_id]["step"] = "w_hours"
            await event.reply("🕐 **Restrict posting to certain hours?**\nSend as `HH:MM-HH:MM` (24h, e.g. `09:00-23:00`), or /skip to post any time:")
            return

        elif state == "w_hours":
            if text == "/skip":
                sdata["start_hour"], sdata["end_hour"] = None, None
            else:
                try:
                    start, end = text.split("-")
                    parse_hhmm(start.strip())
                    parse_hhmm(end.strip())
                    sdata["start_hour"], sdata["end_hour"] = start.strip(), end.strip()
                except Exception:
                    await event.reply("⚠️ **Invalid format.** Use `HH:MM-HH:MM` (e.g. `09:00-23:00`), or /skip:")
                    return
            user_states[user_id]["step"] = "w_abtest"
            await event.reply("🧪 **Part of an A/B test?**\nSend a group name to compare it against other ads (e.g. `promo1`), or /skip:")
            return

        elif state == "w_abtest":
            sdata["test_group"] = None if text == "/skip" else text

            ads = current_db[user_id]["ads"]
            next_id = len(ads) + 1
            new_ad = {
                "id": next_id,
                "text": sdata["text"],
                "media_path": sdata.get("media_path"),
                "media_type": sdata.get("media_type"),
                "btn_text": sdata["btn_text"],
                "btn_url": sdata["btn_url"],
                "interval_minutes": sdata["interval_minutes"],
                "start_hour": sdata.get("start_hour"),
                "end_hour": sdata.get("end_hour"),
                "test_group": sdata.get("test_group"),
                "clicks": 0,
                "views": 0,
                "next_due": None,
            }
            current_db[user_id]["ads"].append(new_ad)
            save_db(current_db)
            clear_flow(user_id)

            summary = (
                f"📈 **Ad saved.** Campaign ID `{next_id}`\n"
                f"⏱️ Every {new_ad['interval_minutes']} min"
                + (f" | 🕐 {new_ad['start_hour']}-{new_ad['end_hour']}" if new_ad['start_hour'] else "")
                + (f" | 🧪 Group: {new_ad['test_group']}" if new_ad['test_group'] else "")
            )
            await event.reply(summary)
            return

        elif state == "w_del":
            try:
                ad_id = int(text)
            except ValueError:
                await event.reply("⚠️ **Invalid input.** Send a valid numeric Campaign ID:")
                return
            exists = any(a["id"] == ad_id for a in current_db[user_id].get("ads", []))
            clear_flow(user_id)
            if not exists:
                await event.reply(f"⚠️ **Not found.** No campaign with ID `{ad_id}`.")
                return
            await event.reply(
                f"🗑️ Delete Campaign ID `{ad_id}`? This can't be undone.",
                buttons=[[Button.inline("✅ Yes, delete", f"confirm_delete:{ad_id}".encode()),
                          Button.inline("❌ Cancel", b"cancel_delete")]]
            )
            return

    # ---- MENU BUTTON ACTIONS ----
    if text == "📋 My Ads":
        ads = current_db[user_id].get("ads", [])
        if not ads:
            await event.reply("📁 **No ads yet.**")
            return
        res = "📊 **Your Active Campaigns:**\n\n"
        for ad in ads:
            ctr = (ad.get("clicks", 0) / ad["views"] * 100) if ad.get("views") else 0
            res += (
                f"🔹 **ID `{ad['id']}`** — {ad['text'][:30]}...\n"
                f"⏱️ Every {ad.get('interval_minutes', DEFAULT_INTERVAL_MIN)} min"
                + (f" | 🕐 {ad['start_hour']}-{ad['end_hour']}" if ad.get('start_hour') else "")
                + (f" | 🧪 {ad['test_group']}" if ad.get('test_group') else "")
                + f"\n👁️ {ad.get('views', 0)} views · 🖱️ {ad.get('clicks', 0)} clicks · CTR {ctr:.1f}%\n\n"
            )
        await event.reply(res)

    elif text == "📈 A/B Results":
        ads = current_db[user_id].get("ads", [])
        groups = {}
        for ad in ads:
            g = ad.get("test_group")
            if g:
                groups.setdefault(g, []).append(ad)
        if not groups:
            await event.reply("🧪 **No A/B test groups yet.** Tag ads with a group name while creating them.")
            return
        res = "📈 **A/B Test Results:**\n\n"
        for g, group_ads in groups.items():
            res += f"🧪 **Group: {g}**\n"
            for ad in sorted(group_ads, key=lambda a: -a.get("clicks", 0)):
                ctr = (ad.get("clicks", 0) / ad["views"] * 100) if ad.get("views") else 0
                res += f"  • ID `{ad['id']}`: {ad.get('views',0)} views, {ad.get('clicks',0)} clicks, {ctr:.1f}% CTR\n"
            res += "\n"
        await event.reply(res)

    elif text == "📊 My Channels":
        chans = current_db[user_id].get("channels", [])
        if not chans:
            await event.reply("❌ **No channels linked yet.**")
            return
        res = "📢 **Linked Channels:**\n\n" + "\n".join(f"• 🎯 `{c}`" for c in chans)
        await event.reply(res)

    elif text == "🟢 Start Loop":
        if not current_db[user_id]["ads"]:
            await event.reply("⚠️ Add at least one ad first.")
            return
        if not current_db[user_id]["channels"]:
            await event.reply("⚠️ Add at least one channel first.")
            return
        if current_db[user_id].get("loop_active"):
            await event.reply("ℹ️ Scheduler is already running.")
            return
        await event.reply("🟢 Start the ad scheduler now?", buttons=[
            [Button.inline("✅ Yes, start", b"confirm_start_loop"), Button.inline("❌ Cancel", b"cancel_generic")]
        ])

    elif text == "🔴 Stop Loop":
        if not current_db[user_id].get("loop_active"):
            await event.reply("ℹ️ Scheduler is already stopped.")
            return
        await event.reply("🔴 Stop the ad scheduler?", buttons=[
            [Button.inline("✅ Yes, stop", b"confirm_stop_loop"), Button.inline("❌ Cancel", b"cancel_generic")]
        ])

    elif text in MENU_ACTIONS:
        MENU_ACTIONS[text](user_id)
        await event.reply(MENU_PROMPTS[text])


# ================= STARTUP =================
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("🚀 Advanced ad scheduler bot is running.")
    client.loop.create_task(commercial_ad_loop())
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
