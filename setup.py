"""First-run interactive setup: writes a local .env file so the app doesn't
require hand-editing config. Run once with: python setup.py
"""
import os

ENV_PATH = ".env"
REQUIRED_MODELS = ["moondream", "nomic-embed-text", "llama3.2"]


def ask(prompt: str, default: str = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default


def check_ollama_models(ollama_url: str) -> None:
    import httpx

    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=3)
        resp.raise_for_status()
        installed = {m["name"].split(":")[0] for m in resp.json().get("models", [])}
    except Exception:
        print(f"\nCouldn't reach Ollama at {ollama_url} to verify models -- make sure it's running.")
        return

    missing = [m for m in REQUIRED_MODELS if m not in installed]
    if missing:
        print("\nOllama is reachable, but these models aren't pulled yet:")
        for m in missing:
            print(f"  ollama pull {m}")
    else:
        print("\nAll required Ollama models are already installed.")


def main():
    if os.path.exists(ENV_PATH):
        overwrite = input(".env already exists — overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Keeping existing .env. Exiting.")
            return

    print("\n--- Media folder ---")
    while True:
        ssd_path = ask("Enter the full path to the folder you want to index (e.g. C:\\Users\\You\\Pictures)")
        if os.path.isdir(ssd_path):
            break
        proceed = input(f"'{ssd_path}' doesn't exist right now (e.g. drive not plugged in). Save it anyway? [y/N]: ").strip().lower()
        if proceed == "y":
            break
    if not ssd_path.endswith(("\\", "/")):
        ssd_path += "\\"

    print("\n--- Ollama location ---")
    print("[1] This computer (default)")
    print("[2] Another computer on my network")
    choice = ask("Is Ollama running on this computer or another one?", default="1")

    if choice == "2":
        ollama_host = ask("Enter the IP address (or hostname) of the computer running Ollama (e.g. 192.168.1.50)")
        ollama_ssh_user = ask("Enter the SSH username for that computer")
        ollama_remote = "true"
    else:
        ollama_host = ""
        ollama_ssh_user = ""
        ollama_remote = "false"

    env_lines = [
        f"SSD_PATH={ssd_path}",
        "",
        "OLLAMA_URL=http://localhost:11434",
        f"OLLAMA_REMOTE={ollama_remote}",
        "VISION_MODEL=moondream",
        "EMBED_MODEL=nomic-embed-text",
        "QUERY_MODEL=llama3.2",
        "",
        f"OLLAMA_SSH_USER={ollama_ssh_user}",
        f"OLLAMA_HOST={ollama_host}",
        "",
        "QDRANT_MODE=embedded",
        "QDRANT_PATH=./qdrant_data",
        "QDRANT_HOST=localhost",
        "QDRANT_PORT=6333",
        "QDRANT_COLLECTION=media_index",
        "",
    ]
    with open(ENV_PATH, "w") as f:
        f.write("\n".join(env_lines))

    print("\nSaved .env (Qdrant runs embedded -- no Docker/database install needed).")

    if ollama_remote == "true":
        print(f"\nMake sure these models are pulled on the Ollama machine ({ollama_host}):")
        for m in REQUIRED_MODELS:
            print(f"  ollama pull {m}")
        print("\nNext: run start_tunnel.bat to connect to it, then run_all.bat to start the app.")
    else:
        check_ollama_models("http://localhost:11434")
        print("\nNext: run run_all.bat to start the app.")


if __name__ == "__main__":
    main()
