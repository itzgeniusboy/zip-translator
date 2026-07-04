import asyncio
import os
import time
import zipfile
from telethon import TelegramClient, events, Button
import pyzipper
from FastTelethonhelper import fast_upload, fast_download

# ================= CONFIGURATION (from environment / GitHub Secrets) =================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

MAX_SIZE = 200 * 1024 * 1024  # 200 MB
WORK_DIR = "zip_jobs"
os.makedirs(WORK_DIR, exist_ok=True)

CHANNEL_TAG = "@FeaturesticLeaks"
OUTPUT_NAME = "@FeaturesticLeaks JOIN CHANNEL.zip"

user_states = {}  # {user_id: {"step": "await_password", "path": str}}

client = TelegramClient('zip_unlock_session', API_ID, API_HASH)


# ================= HELPERS =================
def human(n):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def make_progress_fn(label, start_time):
    def progress_str(done, total):
        pct = (done / total * 100) if total else 0
        elapsed = max(time.time() - start_time, 0.01)
        speed = done / elapsed
        eta = (total - done) / speed if speed > 0 else 0
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        return (f"{label}\n[{bar}] {pct:.1f}%\n"
                f"{human(done)} / {human(total)}\n"
                f"⚡ {human(speed)}/s · ⏳ ETA {int(eta)}s")
    return progress_str


async def unlock_zip(in_path, out_path, password, status_msg):
    """Reads an encrypted zip and rewrites it without a password, reporting live progress."""
    def open_source():
        zf = pyzipper.AESZipFile(in_path)
        zf.pwd = password.encode()
        return zf

    loop = asyncio.get_event_loop()
    try:
        zf = await loop.run_in_executor(None, open_source)
        infos = zf.infolist()
    except Exception as e:
        raise RuntimeError(f"Could not open zip: {e}")

    total_bytes = sum(i.file_size for i in infos) or 1
    start_time = time.time()
    progress_fn = make_progress_fn("🔓 Removing password", start_time)
    processed = 0
    last_edit = 0

    out = None
    try:
        out = zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED)
        for info in infos:
            try:
                data = await loop.run_in_executor(None, zf.read, info.filename)
            except RuntimeError:
                raise RuntimeError("Wrong password.")
            except Exception as e:
                raise RuntimeError(f"Failed to read '{info.filename}': {e}")

            await loop.run_in_executor(None, out.writestr, info.filename, data)
            processed += info.file_size

            now = time.time()
            if now - last_edit >= 2 or processed >= total_bytes:
                last_edit = now
                try:
                    await status_msg.edit(progress_fn(processed, total_bytes))
                except Exception:
                    pass

        out.close()
        zf.close()
    except Exception:
        if out:
            out.close()
        cleanup(out_path)
        raise


# ================= HANDLERS =================
@client.on(events.NewMessage(pattern=r'/start'))
async def start(event):
    user_states.pop(str(event.sender_id), None)
    await event.reply(
        "🔓 **Zip Password Remover**\n\n"
        "1️⃣ Send me a password-protected `.zip` file (up to 200MB)\n"
        "2️⃣ Send the password when I ask\n"
        "3️⃣ Get back the same zip — unlocked, no password needed\n\n"
        "Send /cancel anytime to stop the current job.",
        buttons=Button.clear(),  # removes any leftover keyboard from another bot/session
    )


@client.on(events.NewMessage(pattern=r'/cancel'))
async def cancel(event):
    uid = str(event.sender_id)
    state = user_states.pop(uid, None)
    if state:
        cleanup(state.get("path"))
        await event.reply("❌ Cancelled. Temporary files cleared.", buttons=Button.clear())
    else:
        await event.reply("ℹ️ Nothing in progress.", buttons=Button.clear())


@client.on(events.NewMessage())
async def handle_message(event):
    uid = str(event.sender_id)

    # ---- Step 1: receiving the zip file ----
    if event.document:
        fname = (event.file.name or "file.zip")
        if not fname.lower().endswith(".zip"):
            await event.reply("⚠️ Please send a `.zip` file.", buttons=Button.clear())
            return
        if event.file.size > MAX_SIZE:
            await event.reply(f"⚠️ **Too large.** Max supported size is {human(MAX_SIZE)}.", buttons=Button.clear())
            return

        status = await event.reply("📥 Starting download...", buttons=Button.clear())
        start_time = time.time()
        progress_fn = make_progress_fn("📥 Downloading", start_time)

        try:
            path = await fast_download(
                client, event.message,
                reply=status,
                download_folder=WORK_DIR,
                progress_bar_function=progress_fn,
            )
        except Exception as e:
            await status.edit(f"❌ Download failed: {e}")
            return

        user_states[uid] = {"step": "await_password", "path": path}
        await status.edit("✅ **Download complete.**\n🔑 Now send the password for this zip:")
        return

    # ---- Step 2: receiving the password ----
    text = (event.raw_text or "").strip()
    if uid in user_states and user_states[uid]["step"] == "await_password" and text:
        in_path = user_states[uid]["path"]
        out_path = os.path.join(WORK_DIR, f"{uid}_{int(time.time())}_unlocked.zip")

        status = await event.reply("🔓 Removing password...")
        try:
            await unlock_zip(in_path, out_path, text, status)
        except RuntimeError as e:
            await status.edit(f"❌ **Failed.** {e}\n\nSend the correct password, or /cancel to stop.")
            return
        except Exception as e:
            await status.edit(f"❌ **Unexpected error:** {e}")
            cleanup(in_path, out_path)
            user_states.pop(uid, None)
            return

        # ---- Step 3: fast, parallel upload with live progress ----
        upload_status = await event.reply("📤 Starting upload...")
        upload_start = time.time()
        progress_fn = make_progress_fn("📤 Uploading", upload_start)

        try:
            file_obj = await fast_upload(
                client, out_path,
                reply=upload_status,
                name=OUTPUT_NAME,
                progress_bar_function=progress_fn,
            )
            await client.send_file(
                event.chat_id, file_obj,
                caption=f"✅ **Password removed!**\n\n📢 Join {CHANNEL_TAG} for more.",
                force_document=True,
            )
        except Exception as e:
            await upload_status.edit(f"❌ Upload failed: {e}")
        finally:
            cleanup(in_path, out_path)
            user_states.pop(uid, None)
        return


# ================= STARTUP =================
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("🚀 Zip password remover bot is running.")
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
