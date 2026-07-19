import os

GROUP_TOKEN = os.environ.get("GROUP_TOKEN", "").strip()
CHAT_READ = int(os.environ.get("CHAT_READ", "2000000008"))
CHAT_WRITE = int(os.environ.get("CHAT_WRITE", "2000000007"))
CONFIRM_CODE = os.environ.get("CONFIRM_CODE", "746458b7")
ROLE_CHECKER_ID = int(os.environ.get("ROLE_CHECKER_ID", "-218136766"))
