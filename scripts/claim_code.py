"""Display the private-chat owner claim code derived from BOT_TOKEN."""
import os

from app.bot import claim_code


def main():
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        raise SystemExit("BOT_TOKEN is not set")
    print("Send privately to @kucunxbot: /claim " + claim_code(token))


if __name__ == "__main__":
    main()
