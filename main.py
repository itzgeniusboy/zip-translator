import asyncio
from telethon import TelegramClient, events, Button

# ================= CONFIGURATION =================
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'
BOT_TOKEN = '8945309348:AAGx6zub-rpCH22cnNJzOrvwmQrbqp1hiSU'

# Aapki provide ki hui Admin ID set kar di hai ✅
ADMIN_ID = 1969067694  

AD_INTERVAL = 3600  # Har 1 ghante mein saare channels par ad badlega

ADS_DATABASE = [
    {
        "id": 1,
        "text": "**🔥 TOP DEALS EVERYDAY ONLY ON AMAZON 🔥**\n\nReal verified amazon flipkart loot deals only ❤️",
        "btn_text": "🌐 VIEW CHANNEL",
        "btn_url": "https://t.me/your_channel_link",
        "img_url": "https://i.imgur.com/your_banner_image.png"
    }
]

# Un saare channels ki list jahan bot admin hai (Automatic track hogi)
CONNECTED_CHANNELS = set()

ad_loop_active = True
# Saare channels ke last ad message IDs track karne ke liye dict {channel_id: message_id}
last_ad_messages = {}
current_ad_index = 0
ad_id_counter = 1
user_states = {}
# =================================================

client = TelegramClient('ad_scheduler_session', API_ID, API_HASH)

# --- AUTOMATIC CHANNEL TRACKING LOGIC ---
# Jaise hi bot ko kisi channel mein add kiya jayega ya wo pehla message dekhega, wo use track kar lega
@client.on(events.NewMessage())
async def track_channels(event):
    if event.is_channel:
        channel_id = event.chat_id
        if channel_id not in CONNECTED_CHANNELS:
            CONNECTED_CHANNELS.add(channel_id)
            print(f"➕ Naya Channel Detect Hua Aur Add Ho Gaya: {channel_id}")

# --- AUTO AD POSTING LOGIC (MULTI-CHANNEL) ---
async def send_smart_ad():
    global current_ad_index
    
    if not ad_loop_active or not ADS_DATABASE or not CONNECTED_CHANNELS:
        return

    try:
        # 1. Loop ke hisaab se agla ad select karo
        if current_ad_index >= len(ADS_DATABASE):
            current_ad_index = 0
        ad = ADS_DATABASE[current_ad_index]

        # 2. Jitne bhi tracked channels hain, sab par loop chalao
        for channel_id in list(CONNECTED_CHANNELS):
            # Purana ad agar us channel mein hai toh delete karo
            if channel_id in last_ad_messages:
                try:
                    await client.delete_messages(channel_id, last_ad_messages[channel_id])
                except:
                    pass

            # Naya ad post karo us particular channel mein
            try:
                new_msg = await client.send_message(
                    channel_id,
                    ad["text"],
                    file=ad["img_url"] if ad["img_url"] != "none" else None,
                    buttons=Button.url(ad["btn_text"], url=ad["btn_url"])
                )
                last_ad_messages[channel_id] = new_msg.id
            except Exception as e:
                print(f"Channel {channel_id} par post nahi ho paya (Admin rights check karein): {e}")
                
        print(f"🚀 Ad ID {ad['id']} saare channels par successfully post ho gaya!")
        current_ad_index += 1

    except Exception as e:
        print(f"Multi-channel Ad loop error: {e}")

async def ad_scheduler_loop():
    await asyncio.sleep(10)  # Bot start hone ke 10 sec baad pehla batch chalega
    while True:
        await send_smart_ad()
        await asyncio.sleep(AD_INTERVAL)

# --- ADMIN PANEL BUTTONS ---
@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID: return
    
    admin_buttons = [
        [Button.text("➕ Add Ad"), Button.text("📋 List Ads")],
        [Button.text("🗑️ Delete Ad"), Button.text("📢 Connected Channels")],
        [Button.text("🟢 Turn ON Loop"), Button.text("🔴 Turn OFF Loop")]
    ]
    await event.reply("🕹️ **Ad Management Control Panel!**\nNiche diye gaye buttons se control karein:", buttons=admin_buttons)

# --- BUTTON CLICK HANDLERS & INTERACTIVE FLOW ---
@client.on(events.NewMessage())
async def handle_admin_inputs(event):
    global ad_loop_active, ADS_DATABASE, ad_id_counter
    if event.sender_id != ADMIN_ID: return
    
    text = event.text.strip()
    user_id = event.sender_id

    if text == "📋 List Ads":
        if not ADS_DATABASE:
            await event.reply("📁 Koi bhi ad saved nahi hai abhi.")
            return
        response = "📂 **Aapke Saved Ads ki List:**\n\n"
        for ad in ADS_DATABASE:
            response += f"🆔 **Ad ID:** `{ad['id']}`\n📝 **Text:** {ad['text'][:40]}...\n🔘 **Button:** {ad['btn_text']}\n\n---\n"
        await event.reply(response)
        return

    elif text == "📢 Connected Channels":
        if not CONNECTED_CHANNELS:
            await event.reply("❌ Abhi tak koi channel detect nahi hua. Bot ko channel mein add karke ek baar admin banaein.")
            return
        await event.reply(f"📢 **Bot abhi total `{len(CONNECTED_CHANNELS)}` channels/groups ko sambhal raha hai!**")
        return

    elif text == "🟢 Turn ON Loop":
        ad_loop_active = True
        await event.reply("🟢 **Auto Ad Scheduler ON ho gaya hai saare channels ke liye!**")
        return

    elif text == "🔴 Turn OFF Loop":
        ad_loop_active = False
        await event.reply("🔴 **Auto Ad Scheduler PAUSE ho gaya hai!**")
        return

    elif text == "➕ Add Ad":
        user_states[user_id] = {"step": "waiting_text", "data": {}}
        await event.reply("📝 **Ad ka Caption (Text) bhejo:**")
        return

    elif text == "🗑️ Delete Ad":
        user_states[user_id] = {"step": "waiting_delete_id"}
        await event.reply("🔢 **Ad ki ID bhejo jise delete karna hai:**")
        return

    # Interactive flow handlers
    if user_id in user_states:
        state = user_states[user_id]["step"]
        
        if state == "waiting_text":
            user_states[user_id]["data"]["text"] = text
            user_states[user_id]["step"] = "waiting_btn_text"
            await event.reply("🔘 Ab **Button Name** bhejo (e.g. `🌐 JOIN NOW`):")
            
        elif state == "waiting_btn_text":
            user_states[user_id]["data"]["btn_text"] = text
            user_states[user_id]["step"] = "waiting_btn_url"
            await event.reply("🔗 Ab **Button Link** (URL) bhejo:")
            
        elif state == "waiting_btn_url":
            if not text.startswith("http"):
                await event.reply("❌ Sahi URL bhejo (`https://...`):")
                return
            user_states[user_id]["data"]["btn_url"] = text
            user_states[user_id]["step"] = "waiting_img_url"
            await event.reply("🖼️ Ab **Banner Image URL** bhejo (Ya bina image ke liye `none` likho):")
            
        elif state == "waiting_img_url":
            user_states[user_id]["data"]["img_url"] = text
            ad_id_counter += 1
            ADS_DATABASE.append({
                "id": ad_id_counter,
                "text": user_states[user_id]["data"]["text"],
                "btn_text": user_states[user_id]["data"]["btn_text"],
                "btn_url": user_states[user_id]["data"]["btn_url"],
                "img_url": user_states[user_id]["data"]["img_url"]
            })
            del user_states[user_id]
            await event.reply(f"✅ **Smart Ad successfully add ho gaya! Ad ID:** `{ad_id_counter}`")

        elif state == "waiting_delete_id":
            try:
                ad_id = int(text)
                initial_len = len(ADS_DATABASE)
                ADS_DATABASE = [ad for ad in ADS_DATABASE if ad["id"] != ad_id]
                del user_states[user_id]
                if len(ADS_DATABASE) < initial_len:
                    await event.reply(f"🗑️ **Ad ID {ad_id} ko remove kar diya gaya!**")
                else:
                    await event.reply("❌ ID nahi mili.")
            except:
                await event.reply("⚠️ Sahi numerical ID bhejo:")

# --- MAIN RUNNER ---
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Multi-Channel Ad Panel Bot is running 24x7!")
    client.loop.create_task(ad_scheduler_loop())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
