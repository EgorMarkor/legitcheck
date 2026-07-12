import os
import sys
import time
import traceback
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR if (SCRIPT_DIR / "manage.py").exists() else Path(os.environ.get("LEGITCHECK_PROJECT_DIR", "/root/legitcheck"))


def load_env_file(path):
    path = Path(path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file("/etc/legitcheck/legitcheck.env")
load_env_file("/root/.env")
load_env_file(PROJECT_DIR / ".env")

sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legitcheck.settings")

import django

django.setup()

import vk_api
from django.conf import settings
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll

from webapp.vk_service import get_admin_ids, send_to_admin, upsert_incoming_message


TOKEN = settings.VK_GROUP_TOKEN
GROUP_ID = int(settings.VK_GROUP_ID or "0")
ADMIN_ROLES = {"creator", "administrator"}

if not TOKEN or not GROUP_ID:
    raise RuntimeError("Укажи VK_GROUP_TOKEN и VK_GROUP_ID в окружении")

vk_session = vk_api.VkApi(token=TOKEN)


def format_forwarded_message(message):
    user_id = message.get("from_id")
    text = message.get("text", "")
    msg_id = message.get("id")

    return (
        "📩 Новое сообщение в личку сообщества\n\n"
        f"От: https://vk.com/id{user_id}\n"
        f"ID сообщения: {msg_id}\n\n"
        f"Текст:\n{text if text else '[без текста]'}"
    )


print("VK bot started. Loading administrators...")
admin_ids = get_admin_ids(ADMIN_ROLES)
if admin_ids:
    print(f"Loaded administrators: {len(admin_ids)}")
else:
    print("Warning: administrators were not found or could not be loaded.")

print("Listening to community direct messages...")

while True:
    try:
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)

        for event in longpoll.listen():
            try:
                if event.type != VkBotEventType.MESSAGE_NEW:
                    continue

                message = event.obj.message
                peer_id = message.get("peer_id")
                from_id = message.get("from_id")

                if not peer_id or peer_id != from_id:
                    continue

                upsert_incoming_message(message, notify=True)

                if not admin_ids:
                    admin_ids = get_admin_ids(ADMIN_ROLES)
                    if not admin_ids:
                        print("Administrators are still empty. Message was saved, admin forward skipped.")
                        continue

                forward_text = format_forwarded_message(message)
                for admin_id in admin_ids:
                    try:
                        send_to_admin(admin_id, forward_text)
                        time.sleep(0.35)
                    except Exception as exc:
                        print(f"Failed to forward message to admin {admin_id}: {exc}")

            except Exception:
                print("Error while handling VK message:")
                traceback.print_exc()
                time.sleep(1)

    except (vk_api.exceptions.VkApiError, Exception) as exc:
        print(f"\n[VK/network] Long Poll failed: {exc}")
        print("Restarting Long Poll in 5 seconds...")
        time.sleep(5)
