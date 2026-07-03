import asyncio
from telethon import TelegramClient, events, Button

# ================= CONFIGURATION =================
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'
BOT_TOKEN = '8945309348:AAGx6zub-rpCH22cnNJzOrvwmQrbqp1hiSU'

# Aapki Admin ID ✅
ADMIN_ID = 1969067694  

AD_INTERVAL = 3600  # Har 1 ghante mein ad badlega

# Default Pehla Ad Setup
ADS_DATABASE = [
    {
        "id": 1,
        "text": "**🔥 TOP DEALS EVERYDAY ONLY ON AMAZON 🔥**\n\nReal verified amazon flipkart loot deals only ❤️",
        "btn_text": "🌐 VIEW CHANNEL",
        "btn_url": "https://t.me/your_channel_link",
        "img_url": "https://i.imgur.com/your_banner_image.png"
    }
]

# 📢 YAHAN APNE CHANNELS KE USENAMES DAAL DO (Aap button se bhi add kar sakte ho baad mein)
# Example: {'@my_channel1', '@my_channel2'}
CONNECTED_CHANNELS = set()

ad_loop_active = True
last_ad_messages = {} # {channel: msg_id}
current_ad_index = 0
ad_id_counter = 1
user_states = {}
# =================================================

client = TelegramClient('ad_scheduler_session', API_ID, API_HASH)

# --- MULTI-CHANNEL AD SENDING LOGIC (VIA USERNAME) ---
async def send_smart_ad():
    global current_ad_index
    
    if not ad_loop_active or not ADS_DATABASE or not CONNECTED_CHANNELS:
        print("⚠️ Ad loop skipped: Loop pause hai ya channels list khali hai.")
        return

    try:
        if current_ad_index >= len(ADS_DATABASE):
            current_ad_index = 0
        ad = ADS_DATABASE[current_ad_index]

        for channel in list(CONNECTED_CHANNELS):
            # 1. Purana ad delete karo us channel se
            if channel in last_ad_messages:
                try:
                    await client.delete_messages(channel, last_ad_messages[channel])
                except Exception as e:
                    print(f"Purana message delete nahi hua: {e}")

            # 2. Direct Username par naya ad bhejdo
            try:
                new_msg = await client.send_message(
                    channel,
                    ad["text"],
                    file=ad["img_url"] if ad["img_url"] != "none" else None,
                    buttons=Button.url(ad["btn_text"], url=ad["btn_url"])
                )
                last_ad_messages[channel] = new_msg.id
                print(f"✅ Successful Posted on {channel}")
            except Exception as e:
                print(f"❌ {channel} par post nahi ho paya: {e}")
                
        current_ad_index += 1

    except Exception as e:
        print(f"Global Ad loop error: {e}")

async def ad_scheduler_loop():
    await asyncio.sleep(5)
    while True:
        if ad_loop_active:
            await send_smart_ad()
        await asyncio.sleep(AD_INTERVAL)

# --- ADMIN PANEL INTERFACE ---
@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if event.sender_id != ADMIN_ID: return
    
    admin_buttons = [
        [Button.text("➕ Add Ad"), Button.text("📋 List Ads")],
        [Button.text("🗑️ Delete Ad")],
        [Button.text("📢 Add Channel Username"), Button.text("📊 Show Channels")],
        [Button.text("🟢 Turn ON Loop"), Button.text("🔴 Turn OFF Loop")]
    ]
    await event.reply("🕹️ **Ad Management Control Panel!**\nNiche diye gaye buttons se control karein:", buttons=admin_buttons)

# --- INTERACTIVE USER INPUTS ---
@client.on(events.NewMessage())
async def handle_admin_inputs(event):
    global ad_loop_active, ADS_DATABASE, ad_id_counter, CONNECTED_CHANNELS
    if event.sender_id != ADMIN_ID: return
    
    text = event.text.strip()
    user_id = event.sender_id

    # MAIN KEYBOARD BUTTON CLICKS
    if text == "📋 List Ads":
        if not ADS_DATABASE:
            await event.reply("📁 Koi bhi ad saved nahi hai.")
            return
        res = "📂 **Saved Ads:**\n\n"
        for ad in ADS_DATABASE:
            res += f"🆔 `Ad ID {ad['id']}`\n📝 Text: {ad['text'][:30]}...\n\n"
        await event.reply(res)
        return

    elif text == "📊 Show Channels":
        if not CONNECTED_CHANNELS:
            await event.reply("❌ Koi bhi channel list mein add nahi hai.")
            return
        res = "📢 **Target Channels List:**\n\n"
        for ch in CONNECTED_CHANNELS:
            res += f"• `{ch}`\n"
        await event.reply(res)
        return

    elif text == "🟢 Turn ON Loop":
        ad_loop_active = True
        await event.reply("🟢 **Scheduler ON! Saare channels par INSTANT ad bheja ja raha hai...**")
        await send_smart_ad()
        return

    elif text == "🔴 Turn OFF Loop":
        ad_loop_active = False
        await event.reply("🔴 **Scheduler PAUSE ho gaya hai!**")
        return

    elif text == "➕ Add Ad":
        user_states[user_id] = {"step": "w_text", "data": {}}
        await event.reply("📝 **Ad ka Caption (Text) bhejo:**")
        return

    elif text == "🗑️ Delete Ad":
        user_states[user_id] = {"step": "w_del"}
        await event.reply("🔢 **Ad ki ID bhejo jise delete karna hai:**")
        return

    elif text == "📢 Add Channel Username":
        user_states[user_id] = {"step": "w_chan"}
        await event.reply("📣 **Apne channel ka Username bhejo (with @):**\nExample: `@Cockroach_Janta_Party`")
        return

    # STEP BY STEP CONVERSATION FLOW
    if user_id in user_states:
        state = user_states[user_id]["step"]
        
        if state == "w_chan":
            if not text.startswith("@"):
                await event.reply("❌ Username `@` se shuru hona chahiye. Dobara bhejo:")
                return
            CONNECTED_CHANNELS.add(text)
            del user_states[user_id]
            await event.reply(f"✅ `{text}` ko target list mein add kar diya gaya hai!")
            return

        elif state == "w_text":
            user_states[user_id]["data"]["text"] = text
            user_states[user_id]["step"] = "w_btn_text"
            await event.reply("🔘 **Button Name** bhejo (e.g. `🌐 JOIN NOW`):")
            
        elif state == "w_btn_text":
            user_states[user_id]["data"]["btn_text"] = text
            user_states[user_id]["step"] = "w_btn_url"
            await event.reply("🔗 **Button Link** (URL) bhejo:")
            
        elif state == "w_btn_url":
            if not text.startswith("http"):
                await event.reply("❌ Sahi URL bhejo (`https://...`):")
                return
            user_states[user_id]["data"]["btn_url"] = text
            user_states[user_id]["step"] = "w_img"
            await event.reply("🖼️ **Banner Image URL** bhejo (Ya bina image ke `none` likho):")
            
        elif state == "w_img":
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
            await event.reply(f"✅ **Smart Ad Save Ho Gaya! Ad ID:** `{ad_id_counter}`")

        elif state == "w_del":
            try:
                ad_id = int(text)
                global ADS_DATABASE
                ADS_DATABASE = [ad for ad in ADS_DATABASE if ad["id"] != ad_id]
                del user_states[user_id]
                await event.reply(f"🗑️ Ad ID {ad_id} deleted!")
            except:
                await event.reply("⚠️ Sahi ID bhejo:")

# --- MAIN START ---
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Username-Based Ad Bot is running 24x7!")
    client.loop.create_task(ad_scheduler_loop())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
