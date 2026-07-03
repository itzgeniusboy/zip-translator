import asyncio
import os
from telethon import TelegramClient, events, Button

# ================= CONFIGURATION =================
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'
BOT_TOKEN = '8945309348:AAGx6zub-rpCH22cnNJzOrvwmQrbqp1hiSU'

ADMIN_ID = 1969067694  
AD_INTERVAL = 3600  

# Target Channels List
CONNECTED_CHANNELS = set()

ad_loop_active = True
last_ad_messages = {} 
current_ad_index = 0
ad_id_counter = 0
user_states = {}

# Agar list khali ho, toh default backup ad (GIF) jo pehle se chalega
ADS_DATABASE = [
    {
        "id": 1,
        "text": "**🔥 FEATURESTIC LEAKS - BGMI BYPASS MAKING 🔥**\n\nReal premium tools, bypasses, and structures directly from the core! ❤️",
        "btn_text": "⚡ JOIN NOW",
        "btn_url": "https://t.me/your_channel_link",
        "img_url": "ad_banner.gif"  # Apni repo mein ad_banner.gif naam ki file daal dena, ye wahan se utha lega!
    }
]
# =================================================

client = TelegramClient('ad_scheduler_session', API_ID, API_HASH)

# --- SMART MEDIA SENDING LOGIC (SUPPORT GIF/VIDEO/PHOTO/TEXT) ---
async def send_smart_ad(event_to_reply=None):
    global current_ad_index
    
    if not ad_loop_active or not ADS_DATABASE or not CONNECTED_CHANNELS:
        msg = "⚠️ Ad loop skipped: Database khali hai, loop pause hai, ya channels add nahi hain."
        if event_to_reply: await event_to_reply.reply(msg)
        return

    try:
        if current_ad_index >= len(ADS_DATABASE):
            current_ad_index = 0
        ad = ADS_DATABASE[current_ad_index]

        for channel in list(CONNECTED_CHANNELS):
            # 1. Purana ad delete karo
            if channel in last_ad_messages:
                try: await client.delete_messages(channel, last_ad_messages[channel])
                except: pass

            # 2. Check karo media file local repository mein hai ya URL hai
            media_file = ad["img_url"]
            if media_file != "none" and not media_file.startswith("http"):
                if not os.path.exists(media_file):
                    print(f"⚠️ Local File {media_file} nahi mili, text-only mode automatic triggered.")
                    media_file = "none"

            # 3. Dynamic Posting
            new_msg = None
            try:
                # Local File ya URL ke sath try karo (GIF/Video/Photo sab chalega)
                new_msg = await client.send_message(
                    channel,
                    ad["text"],
                    file=media_file if media_file != "none" else None,
                    buttons=Button.url(ad["btn_text"], url=ad["btn_url"])
                )
            except Exception as media_err:
                print(f"⚠️ Media crash, bypass to text-only: {media_err}")
                try:
                    new_msg = await client.send_message(
                        channel,
                        ad["text"],
                        buttons=Button.url(ad["btn_text"], url=ad["btn_url"])
                    )
                except Exception as text_err:
                    print(f"❌ Pure text fail: {text_err}")

            if new_msg:
                last_ad_messages[channel] = new_msg.id
                print(f"✅ Successfully Posted on {channel}")
                
        if event_to_reply: await event_to_reply.reply(f"🚀 Ad successfully updated on all connected platforms!")
        current_ad_index += 1

    except Exception as e:
        print(f"Global Ad loop error: {e}")
        if event_to_reply: await event_to_reply.reply(f"❌ Global Error: {e}")

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
        [Button.text("📢 Add Channel Username"), Button.text("📢 Connected Channels")],
        [Button.text("🟢 Turn ON Loop"), Button.text("🔴 Turn OFF Loop")]
    ]
    await event.reply("🕹️ **Ad Management Control Panel!**", buttons=admin_buttons)

# --- INTERACTIVE USER INPUTS ---
@client.on(events.NewMessage())
async def handle_admin_inputs(event):
    global ad_loop_active, ADS_DATABASE, ad_id_counter, CONNECTED_CHANNELS, current_ad_index
    if event.sender_id != ADMIN_ID: return
    
    text = event.text.strip()
    user_id = event.sender_id

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
            await event.reply("🔘 **Button Name** bhejo (e.g. `⚡ JOIN NOW`):")
            return
            
        elif state == "w_btn_text":
            user_states[user_id]["data"]["btn_text"] = text
            user_states[user_id]["step"] = "w_btn_url"
            await event.reply("🔗 **Button Link** (URL) bhejo:")
            return
            
        elif state == "w_btn_url":
            if not text.startswith("http"):
                await event.reply("❌ Sahi URL bhejo:")
                return
            user_states[user_id]["data"]["btn_url"] = text
            user_states[user_id]["step"] = "w_img"
            await event.reply("🖼️ **GIF ya Video ka naam ya link bhejo:**\n\n💡 **Pro-Tip:** Agar repo mein upload ki hai, toh file ka naam dalo (e.g., `banner.gif`). Agar media nahi chahiye, toh `none` likho.")
            return
            
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
            current_ad_index = len(ADS_DATABASE) - 1
            del user_states[user_id]
            await event.reply(f"✅ **Aapka naya Media Ad save ho gaya! Ad ID:** `{ad_id_counter}`")
            return

        elif state == "w_del":
            try:
                ad_id = int(text)
                ADS_DATABASE = [ad for ad in ADS_DATABASE if ad["id"] != ad_id]
                del user_states[user_id]
                current_ad_index = 0
                await event.reply(f"🗑️ Ad ID {ad_id} deleted!")
            except:
                await event.reply("⚠️ Sahi ID bhejo:")
            return

    if text == "📋 List Ads":
        if not ADS_DATABASE:
            await event.reply("📁 List empty hai.")
            return
        res = "📂 **Saved Ads:**\n\n"
        for ad in ADS_DATABASE:
            res += f"🆔 `Ad ID {ad['id']}`\n📝 Text: {ad['text'][:30]}...\n🖼️ Media: `{ad['img_url']}`\n\n"
        await event.reply(res)

    elif text == "📢 Connected Channels":
        if not CONNECTED_CHANNELS:
            await event.reply("❌ Channels list khali hai.")
            return
        res = "📢 **Target Channels List:**\n\n"
        for ch in CONNECTED_CHANNELS:
            res += f"• `{ch}`\n"
        await event.reply(res)

    elif text == "🟢 Turn ON Loop":
        if not ADS_DATABASE or not CONNECTED_CHANNELS:
            await event.reply("⚠️ Ad ya Channel check karein, data missing hai!")
            return
        ad_loop_active = True
        await send_smart_ad(event_to_reply=event)

    elif text == "🔴 Turn OFF Loop":
        ad_loop_active = False
        await event.reply("🔴 **Scheduler PAUSE!**")

    elif text == "➕ Add Ad":
        user_states[user_id] = {"step": "w_text", "data": {}}
        await event.reply("📝 **Ad ka Caption (Text) bhejo:**")

    elif text == "🗑️ Delete Ad":
        user_states[user_id] = {"step": "w_del"}
        await event.reply("🔢 **Ad ki ID bhejo jise delete karna hai:**")

    elif text == "📢 Add Channel Username":
        user_states[user_id] = {"step": "w_chan"}
        await event.reply("📣 **Channel Username (with @):**")

# --- MAIN START ---
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Premium Media Ad Bot is running 24x7!")
    client.loop.create_task(ad_scheduler_loop())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
