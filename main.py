import asyncio
import json
import os
from telethon import TelegramClient, events, Button

# ================= CONFIGURATION =================
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'

# Naya token inject kar diya hai ✅
BOT_TOKEN = '8918032442:AAF4kZgCz7ZMC8eAfcpr-f1qr4bTjfs_YyI'

OWNER_ID = 1969067694  
AD_INTERVAL = 3600  

DB_FILE = "commercial_db.json"
user_states = {}
last_ad_messages = {} # {channel_username: msg_id}

# ================= SECURE JSON ENGINE =================
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Database Initialize
db = load_db()
# =======================================================

client = TelegramClient('ad_scheduler_session', API_ID, API_HASH)

# --- PREMIUM ISOLATED AD ENGINE ---
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
                # Purana message clear karo 
                if channel in last_ad_messages:
                    try: await client.delete_messages(channel, last_ad_messages[channel])
                    except: pass
                
                # Dedicated context posting
                try:
                    new_msg = await client.send_message(
                        channel,
                        ad["text"],
                        buttons=Button.url(ad["btn_text"], url=ad["btn_url"])
                    )
                    last_ad_messages[channel] = new_msg.id
                except Exception as e:
                    print(f"Bypass Error for {channel} under user {user_id}: {e}")
            
            current_db[user_id]["current_index"] = current_idx + 1
            
        save_db(current_db)
        await asyncio.sleep(AD_INTERVAL)

# --- CENTRAL PLATFORM CONSOLE ---
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
        
    user_buttons = [
        [Button.text("➕ Add My Ad"), Button.text("📋 List My Ads")],
        [Button.text("🗑️ Delete My Ad")],
        [Button.text("📢 Add My Channel"), Button.text("📊 Show My Channels")],
        [Button.text("🟢 Start My Ads Loop"), Button.text("🔴 Stop My Ads Loop")]
    ]
    
    welcome_text = (
        "💎 **SaaS Premium Ad Management Console** 💎\n\n"
        "Welcome! Yeh ek public, serverless multi-channel ad controller console hai.\n\n"
        "✨ **Privacy Isolation:** Aapka ad aur channel data secured database mein isolated hai. "
        "Aapka campaign sirf aapke added platforms par hi execute hoga.\n\n"
        "⚙️ **Control Command Center:** Niche diye gaye layout interface ka use karein:"
    )
    await event.reply(welcome_text, buttons=user_buttons)

# --- CONTROLLER SYSTEM HANDLING INPUTS ---
@client.on(events.NewMessage())
async def handle_commercial_inputs(event):
    user_id = str(event.sender_id)
    text = event.text.strip()
    
    current_db = load_db()
    if user_id not in current_db:
        return

    # 1. STEP ROUTING
    if user_id in user_states:
        state = user_states[user_id]["step"]
        
        if state == "w_chan":
            if not text.startswith("@"):
                await event.reply("❌ **Invalid Syntax!** Username hamesha `@` se shuru hona chahiye. Dobara dalo:")
                return
            if text not in current_db[user_id]["channels"]:
                current_db[user_id]["channels"].append(text)
                save_db(current_db)
            del user_states[user_id]
            await event.reply(f"✅ **Success!** Platform `{text}` successfully secure hash se link ho gaya hai.\n\n⚠️ **Note:** Bot ko is channel mein *Admin* rights zaroor de dena.")
            return

        elif state == "w_text":
            user_states[user_id]["data"]["text"] = text
            user_states[user_id]["step"] = "w_btn_text"
            await event.reply("🔘 Ab **Button par dikhne wala Naam** bhejo:\n(e.g., `⚡ JOIN PREMIUM`)")
            return
            
        elif state == "w_btn_text":
            user_states[user_id]["data"]["btn_text"] = text
            user_states[user_id]["step"] = "w_btn_url"
            await event.reply("🔗 Ab **Button click hone par khulne wali Destination URL** bhejo:")
            return
            
        elif state == "w_btn_url":
            if not text.startswith("http"):
                await event.reply("❌ **Invalid Protocol!** Hyperlink `https://` ya `http://` se shuru honi chahiye. Dobara bhejo:")
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
            
            del user_states[user_id]
            await event.reply(f"📈 **Campaign Saved!** Aapka custom ad secure node mein register ho gaya hai.\n🏷️ **Assigned Campaign ID:** `{next_id}`")
            return

        elif state == "w_del":
            try:
                ad_id = int(text)
                user_ads = current_db[user_id]["ads"]
                updated_ads = [ad for ad in user_ads if ad["id"] != ad_id]
                
                for i, ad in enumerate(updated_ads):
                    ad["id"] = i + 1
                    
                current_db[user_id]["ads"] = updated_ads
                current_db[user_id]["current_index"] = 0
                save_db(current_db)
                del user_states[user_id]
                await event.reply(f"🗑️ **Deleted!** Campaign Hash ID `{ad_id}` ko database cluster se wipe kar diya gaya hai.")
            except:
                await event.reply("⚠️ **Technical Error!** Sahi numerical structural ID bhejo:")
            return

    # 2. SEAMLESS INTERFACE KEYBOARD MAPPING
    if text == "📋 List My Ads":
        user_ads = current_db[user_id].get("ads", [])
        if not user_ads:
            await event.reply("📁 **Database Empty!** Aapne abhi tak koi active campaign compile nahi kiya hai.")
            return
        res = "📊 **Aapke Active Ads Campaigns:**\n\n"
        for ad in user_ads:
            res += f"🔹 **Campaign Hash ID:** `{ad['id']}`\n📝 **Context Snippet:** {ad['text'][:35]}...\n🔘 **Button Text:** `{ad['btn_text']}`\n\n"
        await event.reply(res)

    elif text == "📊 Show My Channels":
        user_chans = current_db[user_id].get("channels", [])
        if not user_chans:
            await event.reply("❌ **No Targets Linked!** Aapka koi bhi endpoint platform link nahi hai.")
            return
        res = "📢 **Linked Target Networks:**\n\n"
        for ch in user_chans:
            res += f"• 🎯 `{ch}`\n"
        await event.reply(res)

    elif text == "🟢 Start My Ads Loop":
        if not current_db[user_id]["ads"]:
            await event.reply("⚠️ **Process Terminated!** Pehle `➕ Add My Ad` se ek static asset compile karo.")
            return
        if not current_db[user_id]["channels"]:
            await event.reply("⚠️ **Process Terminated!** Pehle `📢 Add My Channel` se target routing pipeline setup karo.")
            return
        current_db[user_id]["loop_active"] = True
        save_db(current_db)
        await event.reply("🟢 **Scheduler Activated!** Aapka automation execution engine start ho gaya hai. Rotational sync engine ab running phase mein hai.")

    elif text == "🔴 Stop My Ads Loop":
        current_db[user_id]["loop_active"] = False
        save_db(current_db)
        await event.reply("🔴 **Scheduler Paused!** Automations successfully freeze state mein bhej di gayi hain.")

    elif text == "➕ Add My Ad":
        user_states[user_id] = {"step": "w_text", "data": {}}
        await event.reply("📝 **Apne naye Campaign ka Caption (Text Context) send karein:**")

    elif text == "🗑️ Delete My Ad":
        user_states[user_id] = {"step": "w_del"}
        await event.reply("🔢 **Jis Campaign ID ko wipe out karna hai wo number bhejo:**")

    elif text == "📢 Add My Channel":
        user_states[user_id] = {"step": "w_chan"}
        await event.reply("📣 **Target network ka explicit Username dalo (with @):**\nExample: `@my_network_channel`")

# --- SERVER STARTUP ENTRY POINT ---
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("🚀 SaaS Premium Isolated Multi-User Ad Bot is Running Serverless!")
    client.loop.create_task(commercial_ad_loop())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
