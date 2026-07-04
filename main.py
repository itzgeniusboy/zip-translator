import asyncio
import os
import time
import zipfile
from telethon import TelegramClient, events, Button
import pyzipper
from FastTelethonhelper import fast_upload

# ================= CONFIGURATION (from environment / GitHub Actions) =================
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


def render_bar(step_label, step_no, total_steps, current, total):
    pct = (current / total * 100) if total else 0
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = "▰" * filled + "▱" * (bar_len - filled)
    return (
        f"**{step_label}** ·  Step {step_no}/{total_steps}\n\n"
        f"`{bar}` {pct:.1f}%\n"
        f"{human(current)} / {human(total)}"
    )


class ProgressTracker:
    def __init__(self, status_msg, step_label, step_no, total_steps=3):
        self.msg = status_msg
        self.step_label = step_label
        self.step_no = step_no
        self.total_steps = total_steps
        self.start = time.time()
        self.last_edit = 0

    async def callback(self, current, total):
        now = time.time()
        if now - self.last_edit < 2.0 and current < total:
            return
        self.last_edit = now

        elapsed = max(now - self.start, 0.01)
        speed = current / elapsed
        eta = (total - current) / speed if speed > 0 else 0

        text = (
            render_bar(self.step_label, self.step_no, self.total_steps, current, total)
            + f"\n⚡ {human(speed)}/s  ·  ⏳ ETA {int(eta)}s"
        )
        try:
            await self.msg.edit(text)
        except Exception:
            pass


async def unlock_zip(in_path, out_path, password, status_msg):
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
    tracker = ProgressTracker(status_msg, "🔐 Removing Password", 2)
    processed = 0

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
            await tracker.callback(processed, total_bytes)

        out.close()
        zf.close()
        await tracker.callback(total_bytes, total_bytes)
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
        "Send a password-protected `.zip` file (up to 200MB) and I'll strip the "
        "password and hand it right back to you — no software, no hassle.\n\n"
        "**How it works:**\n"
        "1️⃣ Send the `.zip` file (Direct or Forwarded)\n"
        "2️⃣ Send its password\n"
        "3️⃣ Get the unlocked file back\n\n"
        "Send /cancel anytime to stop.",
        buttons=Button.clear(),
    )


@client.on(events.NewMessage(pattern=r'/cancel'))
async def cancel(event):
    uid = str(event.sender_id)
    state = user_states.pop(uid, None)
    if state:
        cleanup(state.get("path"))
        await event.reply("❌ **Cancelled.** Temporary files cleared.", buttons=Button.clear())
    else:
        await event.reply("ℹ️ Nothing in progress right now.", buttons=Button.clear())


@client.on(events.NewMessage())
async def handle_message(event):
    uid = str(event.sender_id)

    # ---- Step 1: Receiving and Extracting Media (Direct & Forwarded) ----
    if event.message.media and hasattr(event.message.media, 'document'):
        document = event.message.media.document
        
        fname = "file.zip"
        if document.attributes:
            for attr in document.attributes:
                if hasattr(attr, 'file_name'):
                    fname = attr.file_name
                    break
                    
        if not fname.lower().endswith(".zip"):
            return  # Zip nahi hai toh bypass karo

        file_size = document.size
        if file_size > MAX_SIZE:
            await event.reply(f"⚠️ **File too large.** Max supported size is {human(MAX_SIZE)}.", buttons=Button.clear())
            return

        status = await event.reply(
            render_bar("📥 Downloading File", 1, 3, 0, file_size or 1),
            buttons=Button.clear(),
        )
        
        path = os.path.join(WORK_DIR, f"{uid}_{int(time.time())}.zip")
        tracker = ProgressTracker(status, "📥 Downloading File", 1)

        try:
            # Direct client integration using native client down-stream chunks to avoid silent stalls
            await client.download_media(event.message, file=path, progress_callback=tracker.callback)
        except Exception as e:
            await status.edit(f"❌ **Download failed:** {e}\nTry sending or forwarding again.")
            cleanup(path)
            return

        user_states[uid] = {"step": "await_password", "path": path}
        await status.edit(
            "✅ **File received successfully.**\n\n"
            "🔑 Please send the **password** for this zip to continue:"
        )
        return

    # ---- Step 2: Receiving the password ----
    text = (event.raw_text or "").strip()
    if uid in user_states and user_states[uid]["step"] == "await_password" and text:
        in_path = user_states[uid]["path"]
        out_path = os.path.join(WORK_DIR, f"{uid}_{int(time.time())}_unlocked.zip")

        status = await event.reply(render_bar("🔐 Removing Password", 2, 3, 0, 1))
        try:
            await unlock_zip(in_path, out_path, text, status)
        except RuntimeError as e:
            await status.edit(f"❌ **Incorrect password or unsupported format.**\n{e}\n\nSend the correct password, or /cancel to stop.")
            return
        except Exception as e:
            await status.edit(f"❌ **Unexpected error:** {e}")
            cleanup(in_path, out_path)
            user_states.pop(uid, None)
            return

        # ---- Step 3: Fast, parallel upload with live progress ----
        upload_status = await event.reply(render_bar("📤 Uploading Unlocked File", 3, 3, 0, 1))
        upload_start = time.time()

        def progress_str(done, total):
            elapsed = max(time.time() - upload_start, 0.01)
            speed = done / elapsed
            eta = (total - done) / speed if speed > 0 else 0
            return (
                render_bar("📤 Uploading Unlocked File", 3, 3, done, total)
                + f"\n⚡ {human(speed)}/s  ·  ⏳ ETA {int(eta)}s"
            )

        try:
            file_obj = await fast_upload(
                client, out_path,
                reply=upload_status,
                name=OUTPUT_NAME,
                progress_bar_function=progress_str,
            )
            await client.send_file(
                event.chat_id, file_obj,
                caption=f"✅ **Done! Password removed successfully.**\n\n📢 Join {CHANNEL_TAG} for more.",
                force_document=True,
            )
        except Exception as e:
            await upload_status.edit(f"❌ **Upload failed:** {e}")
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
