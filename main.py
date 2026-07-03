import os
import zipfile
import re
import shutil
import asyncio
from telethon import TelegramClient, events
from googletrans import Translator

# Telegram API Credentials
API_ID = 32569415
API_HASH = '4209968745cb99d37820d5ba7b4845bd'
BOT_TOKEN = '8945309348:AAGx6zub-rpCH22cnNJzOrvwmQrbqp1hiSU'

# Bot Initialization
client = TelegramClient('bot_session', API_ID, API_HASH)
translator = Translator()

def is_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def translate_content(content):
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if is_chinese(line):
            try:
                translated = translator.translate(line, src='zh-cn', dest='en')
                line = translated.text
            except: 
                pass
        new_lines.append(line)
    return '\n'.join(new_lines)

@client.on(events.NewMessage(incoming=True))
async def handle_new_message(event):
    if event.message.media and hasattr(event.message.media, 'document'):
        if event.message.file.ext == '.zip':
            await event.reply('⚡ Zip file detected! Downloading and translating...')
            input_path = await event.download_media(file='incoming_source.zip')
            extract_dir = 'bot_extracted_code'
            output_zip = 'english_source_code.zip'
            
            # Purana extraction clear karein
            if os.path.exists(extract_dir): 
                shutil.rmtree(extract_dir)
                
            with zipfile.ZipFile(input_path, 'r') as zip_ref: 
                zip_ref.extractall(extract_dir)
            
            # Saari programming files check karne ke liye extensions
            allowed_extensions = ('.java', '.kt', '.js', '.ts', '.dart', '.cpp', '.h', '.xml', '.json', '.html', '.txt')
            
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file.endswith(allowed_extensions):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: 
                                text = f.read()
                            if is_chinese(text):
                                translated_text = translate_content(text)
                                with open(file_path, 'w', encoding='utf-8') as f: 
                                    f.write(translated_text)
                        except: 
                            pass
            
            # Wapas ZIP mein pack karein
            with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, extract_dir)
                        zip_ref.write(file_path, arcname)
                        
            await event.reply('🎉 Translation Done!', file=output_zip)
            
            # Clean up temporary files
            try:
                os.remove(input_path)
                os.remove(output_zip)
                shutil.rmtree(extract_dir)
            except:
                pass

async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Bot is successfully running via GitHub Actions deployment!")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
