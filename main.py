import asyncio
import os
import time
import zipfile
from telethon import TelegramClient, events
import pyzipper
from FastTelethonhelper import fast_upload

# ================= CONFIGURATION (from environment / GitHub Secrets) =================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

MAX_SIZE = 200 * 1024 * 1024  # 200 MB
WORK_DIR = "zip_jobs"
os.makedirs(WORK_DIR, exist_ok=True)

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


class ProgressTracker:
    """Live-updating progress message with percentage, speed, and ETA."""

    def __init__(self, status_msg, label, total_override=None):
        self.msg = status_msg
        self.label = label
        self.start = time.time()
        self.last_edit = 0
        self.total_override = total_override

    async def callback(self, current, total):
        total = self.total_override or total
        now = time.time()
        if now - self.last_edit < 2 and current < total:
            return
        self.last_edit = now

        pct = (current / total * 100) if total else 0
        elapsed = max(now - self.start, 0.01)
        speed = current / elapsed
        eta = (total - current) / speed if speed > 0 else 0

        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        text = (
            f"{self.label}\n"
            f"[{bar}] {pct:.1f}%\n"
            f"{human(current)} / {human(total)}\n"
            f"⚡ {human(speed)}/s · ⏳ ETA {int(eta)}s"
        )
        try:
            await self.msg.edit(text)
        except Exception:
            pass


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
    tracker = ProgressTracker(status_msg, "🔓 Removing password", total_override=total_bytes)
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
        "1️⃣ Send me a password-protected `.zip` file (up to 200MB)\n"
        "2️⃣ Send the password when I ask\n"
        "3️⃣ Get back the same zip — unlocked, no password needed\n\n"
        "Send /cancel anytime to stop the current job."
    )


@client.on(events.NewMessage(pattern=r'/cancel'))
async def cancel(event):
    uid = str(event.sender_id)
    state = user_states.pop(uid, None)
    if state:
        cleanup(state.get("path"))
        await event.reply("❌ Cancelled. Temporary files cleared.")
    else:
        await event.reply("ℹ️ Nothing in progress.")


@client.on(events.NewMessage())
async def handle_message(event):
    uid = str(event.sender_id)

    # ---- Step 1: receiving the zip file ----
    if event.document:
        fname = (event.file.name or "file.zip")
        if not fname.lower().endswith(".zip"):
            await event.reply("⚠️ Please send a `.zip` file.")
            return
        if event.file.size > MAX_SIZE:
            await event.reply(f"⚠️ **Too large.** Max supported size is {human(MAX_SIZE)}.")
            return

        status = await event.reply("📥 Starting download...")
        path = os.path.join(WORK_DIR, f"{uid}_{int(time.time())}.zip")
        tracker = ProgressTracker(status, "📥 Downloading")

        try:
            await event.download_media(file=path, progress_callback=tracker.callback)
        except Exception as e:
            await status.edit(f"❌ Download failed: {e}")
            cleanup(path)
            return

        user_states[uid] = {"step": "await_password", "path": path}
        await status.edit("✅ **Download complete.**\n🔑 Now send the password for this zip:")
        return

    # ---- Step 2: receiving the password ----
    text = (event.raw_text or "").strip()
    if uid in user_states and user_states[uid]["step"] == "await_password" and text:
        in_path = user_states[uid]["path"]
        out_path = in_path.replace(".zip", "_unlocked.zip")

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

        def progress_str(done, total):
            pct = (done / total * 100) if total else 0
            elapsed = max(time.time() - upload_start, 0.01)
            speed = done / elapsed
            eta = (total - done) / speed if speed > 0 else 0
            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            return (f"📤 Uploading\n[{bar}] {pct:.1f}%\n"
                    f"{human(done)} / {human(total)}\n"
                    f"⚡ {human(speed)}/s · ⏳ ETA {int(eta)}s")

        try:
            file_obj = await fast_upload(
                client, out_path,
                reply=upload_status,
                name=os.path.basename(out_path),
                progress_bar_function=progress_str,
            )
            await client.send_file(
                event.chat_id, file_obj,
                caption="✅ **Password removed!** Here's your unlocked zip.",
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
