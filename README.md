# Media Search

Search your own photos and videos with plain-language queries — "birthday parties," "receipts from last year," "that hike we did in the fall" — instead of scrolling through folders. Everything runs on your own machine (or your own home network): your files are never uploaded anywhere, and no cloud AI service ever sees them.

It works by having a local AI model look at each photo/video and write a description of what's in it, then turning that description into a vector so you can search by meaning rather than exact filenames or tags.

## How it works, in plain terms

1. **Indexing**: the app walks through a folder you choose, and for each photo or video, asks a local vision model ([Ollama](https://ollama.com), running on your computer) to describe what's in it.
2. Those descriptions get turned into embeddings (numeric representations of meaning) and stored in [Qdrant](https://qdrant.tech), a small local vector database.
3. **Searching**: when you type a query, it gets expanded into more specific terms, turned into an embedding the same way, and compared against everything you've indexed — so "things from the beach" can match a caption that says "sand, waves, sunset" even though you never typed those words.
4. A results page shows thumbnails, captions, and a relevance score, right in your browser.

Nothing here calls out to the internet during search or indexing — the only network traffic is between your own machine(s).

## What you'll need before starting

| Requirement | Why | Notes |
|---|---|---|
| **Python 3.11+** | Runs the app | [python.org/downloads](https://python.org/downloads) |
| **[Ollama](https://ollama.com/download)** | Runs the AI models locally | Can be on this computer, or another one on your network |
| **ffmpeg** | Extracts frames from videos | Windows: `winget install ffmpeg` |
| **Git** | To clone this repo | Or just download the ZIP from GitHub |

You do **not** need Docker or a separate database install — the app manages its own local database automatically (more on this below).

## Quick start

1. **Clone the repo** (or download and unzip it):
   ```
   git clone <this-repo-url>
   cd img-searcher
   ```

2. **Pull the AI models** Ollama will use. On whichever machine will run Ollama:
   ```
   ollama pull moondream
   ollama pull nomic-embed-text
   ollama pull llama3.2
   ```
   (See [Choosing models for your hardware](#choosing-models-for-your-hardware) below — these are good defaults, but you may want something stronger or lighter.)

3. **Run `run_all.bat`.** The first time you run it, it will:
   - Create a Python virtual environment and install dependencies (takes a minute or two — only happens once).
   - Walk you through a short setup wizard asking:
     - Where's the folder you want to index? (e.g. `C:\Users\You\Pictures`)
     - Is Ollama running on this computer, or another one on your network?
   - Check that your Ollama models are pulled, and tell you if anything's missing.
   - Start the web server and open `http://localhost:8000` in your browser.

4. **Index your files.** In the browser, go to the "Index Status" tab and click **Index new files**. This is the slow part — expect roughly a few seconds per photo and longer per video, depending on your hardware (see below). It's fully resumable: closing the app and coming back later will pick up where it left off.

5. **Search.** Once some files are indexed, switch to the **Search** tab and type what you're looking for.

Every time after the first, running `run_all.bat` just starts the app — setup only happens once.

## Choosing models for your hardware

The default models (`moondream` for captioning, `nomic-embed-text` for embeddings, `llama3.2` for query expansion/reranking) are chosen to run comfortably on modest hardware — around 8GB of free RAM. If you have more RAM or a good GPU, swapping in larger models will noticeably improve caption quality and search relevance.

| Your hardware | Vision model (captioning) | Query/reranking model | Notes |
|---|---|---|---|
| **Light** (~8GB RAM, CPU only, or an older machine) | `moondream` (default) | `llama3.2` (default, ~2GB) | Slower per-file, but works everywhere |
| **Mid-range** (16GB RAM, or a modern laptop GPU) | `moondream` (default) | `llama3.2` (default) | This is the sweet spot the defaults are tuned for |
| **Strong** (24GB+ RAM, or a dedicated GPU with 8GB+ VRAM, or Apple Silicon with 24GB+ unified memory) | `llava:7b` or `llava:13b` — noticeably better, more detailed captions | `llama3.1:8b` or similar | More RAM/VRAM headroom means you can run better models without them fighting for memory |

To switch models: `ollama pull <model-name>` on the machine running Ollama, then update `VISION_MODEL` / `QUERY_MODEL` in your `.env` file and restart the app. You don't need to re-run `setup.py` — just edit `.env` directly.

A rule of thumb: captioning quality matters more than reranking quality for search results, since the caption is what actually gets searched. If you can only upgrade one model, upgrade the vision model first.

## Running Ollama on a separate machine

If your main computer doesn't have much spare RAM, you can run Ollama on another machine on your network (e.g. a spare Mac Mini, an old gaming PC, anything with more memory) and point this app at it over SSH. The setup wizard asks about this directly — just answer "another computer" and give it that machine's IP address and your SSH username. Set up passwordless SSH login first with `ssh-keygen` and `ssh-copy-id` so you're not typing a password every time (see comments in `start_tunnel.bat` for the exact commands).

## Configuration reference (`.env`)

`setup.py` writes this file for you, but you can hand-edit it any time — just restart the app afterward for changes to take effect. See `.env.example` for the full template.

| Variable | What it controls |
|---|---|
| `SSD_PATH` | The folder that gets indexed |
| `OLLAMA_URL` | Where the app looks for Ollama (almost always `http://localhost:11434`, even for a remote machine — the SSH tunnel maps it there) |
| `OLLAMA_REMOTE` | `true` if Ollama runs on another machine (controls whether the SSH tunnel starts automatically) |
| `VISION_MODEL`, `EMBED_MODEL`, `QUERY_MODEL` | Which Ollama models to use for captioning, embeddings, and query expansion/reranking |
| `OLLAMA_SSH_USER`, `OLLAMA_HOST` | SSH details for a remote Ollama machine |
| `QDRANT_MODE` | `embedded` (default, no install needed) or `server` (connects to a Qdrant instance you run separately, e.g. via `docker-compose.yml` — useful for advanced setups) |
| `QDRANT_PATH` | Where the embedded database stores its files |
| `RERANK_RESULTS` *(in `config.py`, not `.env`)* | Whether an LLM re-ranks search results for better relevance on vague queries — costs a bit of extra time per search |

## Troubleshooting

- **"Cannot reach Ollama"** — make sure `ollama serve` is running (or check your SSH tunnel if Ollama is remote — the tunnel window should stay open).
- **Indexing is very slow** — this is expected for large libraries; captioning is the bottleneck. Let it run in the background, or try a lighter vision model if it's too slow to be usable.
- **A video/photo shows "failed" status** — the app retries failed files automatically on the next indexing run, so you usually don't need to do anything.
- **Search returns nothing** — check the Index Status tab to confirm files have actually been indexed yet.
- **Weird characters in a filename break indexing** — please open an issue with the file type/extension so it can be reproduced.

## A note on privacy

Search queries and image descriptions can include sensitive content, since a big use case here is finding scanned documents, IDs, or anything else you'd rather locate quickly than lose track of. Everything — models, captions, the database — stays on hardware you control. Nothing is sent to any third-party service.

## Project structure

```
img-searcher/
├── main.py              # FastAPI app -- serves the UI and search API
├── indexer.py           # Scans your folder, captions files, stores them in Qdrant
├── setup.py             # First-run interactive setup wizard
├── config.py            # Loads all settings from .env
├── qdrant_db.py         # Chooses embedded vs. server Qdrant connection
├── run_all.bat          # One script to bootstrap and start everything
├── start_tunnel.bat     # SSH tunnel helper, only used with a remote Ollama
├── static/index.html    # The search UI (single file, no build step)
├── .env.example         # Template for your own .env
└── docker-compose.yml   # Optional: only needed for QDRANT_MODE=server
```

## License

_No license has been chosen yet for this project — until one is added, all rights are reserved by default. If you're planning to make this public, consider adding an [MIT](https://choosealicense.com/licenses/mit/) or similar permissive license so others know how they're allowed to use it._
