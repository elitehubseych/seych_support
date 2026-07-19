import os

USER_TOKEN = os.environ.get("USER_TOKEN", "")
CHAT_READ = int(os.environ.get("CHAT_READ", "2000000020"))
CHAT_WRITE = int(os.environ.get("CHAT_WRITE", "2000000206"))
ROLE_CHECKER_ID = int(os.environ.get("ROLE_CHECKER_ID", "-218136766"))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "30"))
