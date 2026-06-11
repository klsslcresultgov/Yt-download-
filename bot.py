import os
import re
import json
import time
import subprocess
import requests
from yt_dlp import YoutubeDL

# Telegram Bot configuration
BOT_TOKEN = '8864810691:AAHo1s3tnT_8xfd2FjzWKxALuQcE3EeKOvs'
BASE_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'

# File to temporarily store video links for users
USER_DATA_FILE = 'user_sessions.json'

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f)

def clean_filename(title):
    return re.sub(r"[^a-zA-Z0-9 ]", "", title).strip()

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

def send_action(chat_id, action):
    # Action can be 'upload_video' or 'upload_audio'
    url = f"{BASE_URL}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action})
    except:
        pass

def send_media(chat_id, file_path, media_type):
    url = f"{BASE_URL}/sendAudio" if media_type == 'audio' else f"{BASE_URL}/sendVideo"
    try:
        with open(file_path, 'rb') as media_file:
            files = {media_type: media_file}
            data = {"chat_id": chat_id}
            requests.post(url, data=data, files=files)
    except Exception as e:
        print(f"Error sending media: {e}")
        send_message(chat_id, "❌ ഫയൽ അയക്കാൻ സാധിച്ചില്ല. വീണ്ടും ശ്രമിക്കുക.")

def process_youtube_link(chat_id, url):
    send_message(chat_id, "⏳ വീഡിയോ വിവരങ്ങൾ ശേഖരിക്കുന്നു...")
    
    ydl_opts = {}
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Video')
            
            # Save the link for this user session
            user_sessions = load_user_data()
            user_sessions[str(chat_id)] = {"url": url, "title": title}
            save_user_data(user_sessions)
            
            # Standard quality options keyboard
            keyboard = {
                "keyboard": [
                    [{"text": "🎵 Audio (MP3)"}],
                    [{"text": "📺 360p"}, {"text": "📺 480p"}],
                    [{"text": "📺 720p"}, {"text": "📺 1080p"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            
            send_message(chat_id, f"🎬 *{title}*\n\nഏത് ഫോർമാറ്റിലാണ് ഡൗൺലോഡ് ചെയ്യേണ്ടത്?", reply_markup=keyboard)
            
    except Exception as e:
        print(e)
        send_message(chat_id, "❌ ക്ഷമിക്കണം, ഈ ലിങ്ക് പ്രോസസ്സ് ചെയ്യാൻ സാധിച്ചില്ല. ലിങ്ക് ശരിയാണോ എന്ന് പരിശോധിക്കുക.")

def download_and_send(chat_id, choice):
    user_sessions = load_user_data()
    user_info = user_sessions.get(str(chat_id))
    
    if not user_info:
        send_message(chat_id, "❌ ദയവായി ആദ്യം ഒരു യൂട്യൂബ് ലിങ്ക് അയക്കുക.")
        return

    url = user_info["url"]
    title = clean_filename(user_info["title"])
    output_dir = f"downloads/{chat_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    send_message(chat_id, f"📥 ഡൗൺലോഡിംഗ് ആരംഭിച്ചു: {choice}...")

    if choice == "🎵 Audio (MP3)":
        send_action(chat_id, "upload_audio")
        output_file = f"{output_dir}/{title}.mp3"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{output_dir}/{title}.%(ext)s",
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        media_type = 'audio'
    else:
        send_action(chat_id, "upload_video")
        res = choice.replace("📺 ", "").replace("p", "")
        output_file = f"{output_dir}/{title}_{res}.mp4"
        
        # Downloads best video of specific height + best audio and merges them
        ydl_opts = {
            'format': f'bestvideo[height<={res}]+bestaudio/best',
            'outtmpl': f"{output_dir}/{title}_{res}.%(ext)s",
            'merge_output_format': 'mp4',
        }
        media_type = 'video'

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Find the actual downloaded file (handling potential extension differences)
        actual_file = output_file
        if not os.path.exists(actual_file):
            # Fallback to check if it merged into mp4 directly
            if media_type == 'video' and os.path.exists(output_file):
                actual_file = output_file
            else:
                files = os.listdir(output_dir)
                if files:
                    actual_file = os.path.join(output_dir, files[0])
                else:
                    raise FileNotFoundError

        # Check File Size (Telegram bot API limit is 50MB)
        file_size_mb = os.path.getsize(actual_file) / (1024 * 1024)
        
        if file_size_mb > 50:
            send_message(chat_id, f"⚠️ ഫയൽ സൈസ് {round(file_size_mb, 2)}MB ആണ്. ടെലിഗ്രാം ബോട്ട് വഴി 50MB-യിൽ കൂടുതൽ സൈസുള്ള ഫയലുകൾ അയക്കാൻ കഴിയില്ല.")
        else:
            send_message(chat_id, "📤 ഫയൽ ടെലിഗ്രാമിലേക്ക് അപ്‌ലോഡ് ചെയ്യുന്നു...")
            send_media(chat_id, actual_file, media_type)
            
        # Clean up files
        if os.path.exists(actual_file):
            os.remove(actual_file)
            
    except Exception as e:
        print(e)
        send_message(chat_id, "❌ ഡൗൺലോഡ് ചെയ്യുന്നതിനിടയിൽ ഒരു തകരാർ സംഭവിച്ചു.")

def handle_updates(offset):
    url = f"{BASE_URL}/getUpdates"
    payload = {"offset": offset, "timeout": 30}
    
    try:
        resp = requests.get(url, json=payload).json()
        if not resp.get("ok"):
            return offset

        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "").strip()
            
            if not chat_id or not text:
                continue

            if text == "/start":
                send_message(chat_id, "👋 ഹലോ! ഞാൻ ഒരു YouTube ഡൗൺലോഡർ ബോട്ട് ആണ്.\n\nനിങ്ങൾക്ക് ആവശ്യമുള്ള യൂട്യൂബ് വീഡിയോയുടെ ലിങ്ക് എനിക്ക് അയച്ചു തരൂ.")
            elif "youtube.com/" in text or "youtu.be/" in text:
                process_youtube_link(chat_id, text)
            elif text in ["🎵 Audio (MP3)", "📺 360p", "📺 480p", "📺 720p", "📺 1080p"]:
                download_and_send(chat_id, text)
            else:
                send_message(chat_id, "❓ ദയവായി ഒരു ശരിയായ YouTube ലിങ്ക് അയക്കുക അല്ലെങ്കിൽ നൽകിയിരിക്കുന്ന ബട്ടണുകൾ ഉപയോഗിക്കുക.")
                
    except Exception as e:
        print(f"Error in update loop: {e}")
        
    return offset

def main():
    print("🤖 Bot is running smoothly...")
    offset = 0
    while True:
        offset = handle_updates(offset)
        time.sleep(1)

if __name__ == '__main__':
    main()
