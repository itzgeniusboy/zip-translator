import asyncio
import os
import time
import zipfile
from telethon import TelegramClient, events, Button
import pyzipper
from FastTelethonhelper import fast_upload

# ================= CONFIGURATION (from environment / GitHub Secrets) =================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

MAX_SIZE = 200 * 1024 * 1024  # 200 MB
WORK_DIR = "zip_jobs"
os.makedirs(WORK_DIR, exist_ok=True)

CHANNEL_TAG = "@FeaturesticLeaks"
OUTPUT_NAME = "@FeaturesticLeaks JOIN CHANNEL.zip"

STALL_TIMEOUT = 45     # seconds with zero progress before warning the user
HARD_TIMEOUT = 240     # seconds before giving up entirely

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
        f"**{step_label}**  ·  Step {step_no}/{total_steps}\n\n"
        f"`{bar}` {pct:.1f}%\n"
        f"{human(current)} / {human(total)}"
    )


class ProgressTracker:
    """Reliable, live-updating progress message with percentage, speed, and ETA."""

    def __init__(self, status_msg, step_label, step_no, total_steps=3, total_override=None):
        self.msg = status_msg
        self.step_label = step_label
        self.step_no = step_no
        self.total_steps = total_steps
        self.start = time.time()
        self.last_edit = 0
        self.total_override = total_override

    async def callback(self, current, total):
        total = self.total_override or total
        now = time.time()
        if now - self.last_edit < 1.5 and current < total:
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


async def download_with_watchdog(event, path, tracker, status_msg,
                                  stall_timeout=STALL_TIMEOUT, hard_timeout=HARD_TIMEOUT):
    """Downloads the file while watching for stalls, so the bot never looks silently frozen."""
    last_progress = {"bytes": 0, "time": time.time()}

    async def wrapped_callback(current, total):
        last_progress["bytes"] = current
        last_progress["time"] = time.time()
        await tracker.callback(current, total)

    download_task = asyncio.create_task(
        event.download_media(file=path, progress_callback=wrapped_callback)
    )

    start = time.time()
    warned = False
    try:
        while not download_task.done():
            await asyncio.sleep(5)
            idle = time.time() - last_progress["time"]
            elapsed = time.time() - start

            if elapsed > hard_timeout:
                download_task.cancel()
                raise RuntimeError(
                    "Download timed out — the connection to Telegram's servers is too slow right now. "
                    "Please try again in a bit, or send a smaller file."
                )

            if idle > stall_timeout and last_progress["bytes"] == 0 and not warned:
                warned = True
                try:
                    await status_msg.edit(
                        "🐢 **Network is slow right now.**\n"
                        "Still trying to connect to Telegram's servers — this can take a moment. "
                        "Hang tight, or /cancel to stop."
                    )
                except Exception:
                    pass

        return await download_task
    except asyncio.CancelledError:
        raise
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(str(e))


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
    tracker = ProgressTracker(status_msg, "🔐 Removing Password", 2, total_override=total_bytes)
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
        "1️⃣ Send the `.zip` file\n"
        "2️⃣ Send its password\n"
        "3️⃣ Get the unlocked file back — live progress shown at every step\n\n"
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

    # ---- Step 1: receiving the zip file ----
    if event.document:
        fname = (event.file.name or "file.zip")
        if not fname.lower().endswith(".zip"):
            await event.reply("⚠️ Please send a `.zip` file.", buttons=Button.clear())
            return
        if event.file.size > MAX_SIZE:
            await event.reply(f"⚠️ **File too large.** Max supported size is {human(MAX_SIZE)}.", buttons=Button.clear())
            return

        status = await event.reply(
            render_bar("📥 Downloading File", 1, 3, 0, event.file.size or 1),
            buttons=Button.clear(),
        )
        path = os.path.join(WORK_DIR, f"{uid}_{int(time.time())}.zip")
        tracker = ProgressTracker(status, "📥 Downloading File", 1)

        try:
            await download_with_watchdog(event, path, tracker, status)
        except RuntimeError as e:
            await status.edit(f"⏱️ **{e}**\n\nSend the file again to retry.")
            cleanup(path)
            return
        except Exception as e:
            await status.edit(f"❌ **Download failed:** {e}")
            cleanup(path)
            return

        user_states[uid] = {"step": "await_password", "path": path}
        await status.edit(
            "✅ **File received successfully.**\n\n"
            "🔑 Please send the **password** for this zip to continue:"
        )
        return

    # ---- Step 2: receiving the password ----
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

        # ---- Step 3: fast, parallel upload with live progress ----
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
