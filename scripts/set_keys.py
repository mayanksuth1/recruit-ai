"""Save API keys into backend/.env and supabase/.env.

Input is hidden and nothing is printed back, so keys stay out of the terminal
history and chat. Press Enter at any prompt to keep what is already there.

Run:  backend/.venv/bin/python scripts/set_keys.py
"""
import getpass
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BACKEND = os.path.join(ROOT, "backend", ".env")
SUPABASE = os.path.join(ROOT, "supabase", ".env")


def save(path: str, name: str, value: str) -> None:
    text = open(path).read() if os.path.exists(path) else ""
    line = f"{name}={value}"
    pattern = rf"^{re.escape(name)}=.*$"
    if re.search(pattern, text, flags=re.M):
        text = re.sub(pattern, lambda _: line, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def ask(label: str, prefix: str = "") -> str:
    while True:
        value = getpass.getpass(f"{label} (input hidden, Enter to skip): ").strip().strip("\"'")
        if not value or not prefix or value.startswith(prefix):
            return value
        print(f"  That doesn't start with {prefix}. Try again, or press Enter to skip.")


def main() -> None:
    nvidia = ask("NVIDIA API key", "nvapi-")
    if nvidia:
        save(BACKEND, "NVIDIA_API_KEY", nvidia)
        print("  saved")
    groq = ask("Groq API key", "gsk_")
    if groq:
        save(BACKEND, "BACKUP_AI_API_KEY", groq)
        print("  saved")
    google_id = ask("Google OAuth Client ID")
    if google_id:
        save(BACKEND, "GOOGLE_CLIENT_ID", google_id)
        save(SUPABASE, "SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID", google_id)
        print("  saved")
    google_secret = ask("Google OAuth Client Secret")
    if google_secret:
        save(BACKEND, "GOOGLE_CLIENT_SECRET", google_secret)
        save(SUPABASE, "SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET", google_secret)
        print("  saved")
    resend = ask("Resend API key", "re_")
    if resend:
        save(BACKEND, "RESEND_API_KEY", resend)
        print("  saved")
    print("Done.")


if __name__ == "__main__":
    main()
