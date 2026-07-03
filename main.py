import asyncio
import json
import os
from telethon import TelegramClient, events, Button

# ================= CONFIGURATION =================
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'
BOT_TOKEN = '8918032442:AAF4kZgCz7ZMC8eAfcpr-f1qr4bTjfs_YyI'

OWNER_ID = 1969067694
AD_INTERVAL = 3600

DB_FILE = "commercial_db.json"
user_states = {}       # {user_id: {"step": str, "data": dict}}
pending_actions = {}   # {user_id: {"action": str, "payload": any}}  -> awaiting confirm
last_ad_messages = {}  # {channel_username: msg_id}

MAIN_MENU = [
    [Button.text("➕ Add Ad"), Button.text("📋 My Ads")],
    [Button.text("🗑️ Delete Ad")],
    [Button.text("📢 Add Channel"), Button.text("📊 My Channels")],
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


db = load_db()
client = TelegramClient('ad_scheduler_session', API_ID, API_HASH)


# ================= AD ROTATION ENGINE =================
async def commercial_ad_loop():
    await asyncio.sleep(5)
    while True:
        current_db = load_db()

        for user_id, user_data in current_db.items():
            if not user_data.get("loop_active", False):
                continue

            user_ads = user_data.get("ads", [])
            user_channels = user_data.get("channels", [])

            if not user_ads or not user_channels:
                continue

            current_idx = user_data.get("current_index", 0)
            if current_idx >= len(user_ads):
                current_idx = 0

            ad = user_ads[current_idx]

            for channel in user_channels:
                if channel in last_ad_messages:
                    try:
                        await client.delete_messages(channel, last_ad_messages[channel])
                    except Exception:
                        pass
                try:
                    new_msg = await client.send_message(
                        channel,
                        ad["text"],
                        buttons=Button.url(ad["btn_text"], url=ad["btn_url"])
                    )
                    last_ad_messages[channel] = new_msg.id
                except Exception as e:
                    print(f"Post error for {channel} (user {user_id}): {e}")

            current_db[user_id]["current_index"] = current_idx + 1

        save_db(current_db)
        await asyncio.sleep(AD_INTERVAL)


# ================= HELPERS =================
def user_is_busy(user_id: str) -> bool:
    return user_id in user_states


def start_flow(user_id: str, step: str, data: dict = None):
    user_states[user_id] = {"step": step, "data": data or {}}


def clear_flow(user_id: str):
    user_states.pop(user_id, None)


# The action a menu button would start if there wasn't a conflicting flow.
# Used to resume the requested action after a confirmed override.
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
        current_db[user_id] = {
            "channels": [],
            "ads": [],
            "loop_active": False,
            "current_index": 0
        }
        save_db(current_db)

    clear_flow(user_id)
    pending_actions.pop(user_id, None)

    welcome_text = (
        "💎 **Ad Management Console** 💎\n\n"
        "Welcome to your private, multi-channel ad scheduler.\n\n"
        "✨ **Isolated storage** — your ads and channels are kept separate from every other user's data, "
        "and your campaigns only run on the channels you add.\n\n"
        "⚙️ Use the menu below to get started:"
    )
    await event.reply(welcome_text, buttons=MAIN_MENU)


# ================= CALLBACK (CONFIRMATIONS) =================
@client.on(events.CallbackQuery())
async def handle_callback(event):
    user_id = str(event.sender_id)
    data = event.data.decode("utf-8")
    current_db = load_db()

    if user_id not in current_db:
        await event.answer("Please send /start first.", alert=True)
        return

    # ---- Overriding an in-progress flow ----
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

    # ---- Delete ad confirmation ----
    if data.startswith("confirm_delete:"):
        ad_id = int(data.split(":")[1])
        user_ads = current_db[user_id].get("ads", [])
        updated_ads = [ad for ad in user_ads if ad["id"] != ad_id]
        for i, ad in enumerate(updated_ads):
            ad["id"] = i + 1
        current_db[user_id]["ads"] = updated_ads
        current_db[user_id]["current_index"] = 0
        save_db(current_db)
        await event.edit(f"🗑️ **Deleted.** Campaign ID `{ad_id}` has been removed.")
        return

    if data == "cancel_delete":
        await event.edit("👍 Deletion cancelled.")
        return

    # ---- Start/Stop loop confirmation ----
    if data == "confirm_start_loop":
        current_db[user_id]["loop_active"] = True
        save_db(current_db)
        await event.edit("🟢 **Scheduler started.** Your ads will now rotate automatically across your linked channels.")
        return

    if data == "confirm_stop_loop":
        current_db[user_id]["loop_active"] = False
        save_db(current_db)
        await event.edit("🔴 **Scheduler stopped.** Automatic posting is paused.")
        return

    if data == "cancel_generic":
        await event.edit("👍 Action cancelled.")
        return


# ================= TEXT / STEP ROUTING =================
@client.on(events.NewMessage())
async def handle_commercial_inputs(event):
    user_id = str(event.sender_id)
    text = event.text.strip()

    current_db = load_db()
    if user_id not in current_db:
        return

    is_menu_button = text in MENU_ACTIONS

    # ---- Guard: block starting a new flow while one is unfinished ----
    if is_menu_button and user_is_busy(user_id):
        pending_actions[user_id] = {"label": text}
        await event.reply(
            "⚠️ **You have an unfinished action in progress.**\n\n"
            "Starting a new one will cancel it. Continue?",
            buttons=[
                [Button.inline("✅ Yes, cancel and continue", b"confirm_override"),
                 Button.inline("❌ No, keep current", b"cancel_override")]
            ]
        )
        return

    # ---- STEP ROUTING ----
    if user_id in user_states:
        state = user_states[user_id]["step"]

        if state == "w_chan":
            if not text.startswith("@"):
                await event.reply("❌ **Invalid format.** Username must start with `@`. Please try again:")
                return
            if text not in current_db[user_id]["channels"]:
                current_db[user_id]["channels"].append(text)
                save_db(current_db)
            clear_flow(user_id)
            await event.reply(
                f"✅ **Channel linked.** `{text}` has been added successfully.\n\n"
                f"⚠️ **Note:** Make sure the bot has *admin rights* in this channel."
            )
            return

        elif state == "w_text":
            user_states[user_id]["data"]["text"] = text
            user_states[user_id]["step"] = "w_btn_text"
            await event.reply("🔘 **Now send the button label:**\n(e.g., `⚡ Join Premium`)")
            return

        elif state == "w_btn_text":
            user_states[user_id]["data"]["btn_text"] = text
            user_states[user_id]["step"] = "w_btn_url"
            await event.reply("🔗 **Now send the destination URL for the button:**")
            return

        elif state == "w_btn_url":
            if not text.startswith("http"):
                await event.reply("❌ **Invalid link.** URL must start with `http://` or `https://`. Please try again:")
                return

            user_ads = current_db[user_id]["ads"]
            next_id = len(user_ads) + 1

            new_ad = {
                "id": next_id,
                "text": user_states[user_id]["data"]["text"],
                "btn_text": user_states[user_id]["data"]["btn_text"],
                "btn_url": text
            }
            current_db[user_id]["ads"].append(new_ad)
            save_db(current_db)

            clear_flow(user_id)
            await event.reply(f"📈 **Ad saved.** Campaign ID `{next_id}` has been created.")
            return

        elif state == "w_del":
            try:
                ad_id = int(text)
            except ValueError:
                await event.reply("⚠️ **Invalid input.** Please send a valid numeric Campaign ID:")
                return

            exists = any(ad["id"] == ad_id for ad in current_db[user_id].get("ads", []))
            clear_flow(user_id)
            if not exists:
                await event.reply(f"⚠️ **Not found.** No campaign with ID `{ad_id}`.")
                return

            await event.reply(
                f"🗑️ Delete Campaign ID `{ad_id}`? This can't be undone.",
                buttons=[
                    [Button.inline("✅ Yes, delete", f"confirm_delete:{ad_id}".encode()),
                     Button.inline("❌ Cancel", b"cancel_delete")]
                ]
            )
            return

    # ---- MENU BUTTON ACTIONS ----
    if text == "📋 My Ads":
        user_ads = current_db[user_id].get("ads", [])
        if not user_ads:
            await event.reply("📁 **No ads yet.** You haven't created any campaigns.")
            return
        res = "📊 **Your Active Campaigns:**\n\n"
        for ad in user_ads:
            res += f"🔹 **Campaign ID:** `{ad['id']}`\n📝 **Preview:** {ad['text'][:35]}...\n🔘 **Button:** `{ad['btn_text']}`\n\n"
        await event.reply(res)

    elif text == "📊 My Channels":
        user_chans = current_db[user_id].get("channels", [])
        if not user_chans:
            await event.reply("❌ **No channels linked yet.**")
            return
        res = "📢 **Linked Channels:**\n\n"
        for ch in user_chans:
            res += f"• 🎯 `{ch}`\n"
        await event.reply(res)

    elif text == "🟢 Start Loop":
        if not current_db[user_id]["ads"]:
            await event.reply("⚠️ **Cannot start.** Add at least one ad first (➕ Add Ad).")
            return
        if not current_db[user_id]["channels"]:
            await event.reply("⚠️ **Cannot start.** Add at least one channel first (📢 Add Channel).")
            return
        if current_db[user_id].get("loop_active"):
            await event.reply("ℹ️ Scheduler is already running.")
            return
        await event.reply(
            "🟢 Start the ad scheduler now?",
            buttons=[
                [Button.inline("✅ Yes, start", b"confirm_start_loop"),
                 Button.inline("❌ Cancel", b"cancel_generic")]
            ]
        )

    elif text == "🔴 Stop Loop":
        if not current_db[user_id].get("loop_active"):
            await event.reply("ℹ️ Scheduler is already stopped.")
            return
        await event.reply(
            "🔴 Stop the ad scheduler?",
            buttons=[
                [Button.inline("✅ Yes, stop", b"confirm_stop_loop"),
                 Button.inline("❌ Cancel", b"cancel_generic")]
            ]
        )

    elif text in MENU_ACTIONS:
        MENU_ACTIONS[text](user_id)
        await event.reply(MENU_PROMPTS[text])


# ================= STARTUP =================
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("🚀 Ad scheduler bot is running.")
    client.loop.create_task(commercial_ad_loop())
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
