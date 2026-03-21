import os


def debug(message, prefix="DEBUG"):
    if os.getenv("DEBUG", "false").lower() == "true":
        print(f"    \033[2m[{prefix}] {message}\033[0m")

