# ConfigPilot: Local LLM Configuration Manager

An AI-powered, natural language interface for managing application configurations using local LLMs (Llama 3.1).

> **Stop editing JSON files manually. Just tell the bot what you want.**

---

## What is this?

ConfigPilot allows DevOps engineers to modify complex JSON configurations using natural language commands. It runs entirely locally using Docker and Ollama, ensuring privacy and zero cloud costs.

**Example Usage:**

```
User: "Set tournament memory to 1024mb"
Bot: Updates tournament.value.json -> resources.memory.limitMiB to 1024.
```

---

## Architecture & Engineering Decisions

This isn't just a wrapper around an API. It's a system designed for reliability and minimal footprint.

### 1. "No Frameworks" Approach

Instead of using heavy frameworks like Flask or Django for a service that handles a single POST request, I used Python's native `http.server`.

- **Result:** Lighter container images (`python:3.11-slim`), faster startup, zero `pip install` overhead.

### 2. The "Navigator" Logic (JSON Patch)

Using LLMs to rewrite entire configuration files leads to hallucinations and token limit truncation.

- **Solution:** Implemented a JSON Patch (RFC 6902) style logic.
- **How it works:** The LLM doesn't write the file. It outputs a "Change Spec" (e.g., `{"path": ["workloads", "memory"], "value": 1024}`), and Python code surgically applies the update.
- **Outcome:** 100% deterministic updates, significantly lower token usage.

### 3. Infrastructure Resilience

- **Self-Healing:** The system uses a dedicated `ollama-pull` container to ensure the Llama 3.1 model is fully downloaded and ready before the bot service starts, preventing "Model Not Found" crashes.
- **Resource Management:** Optimized for running on local hardware (tested on Arch Linux & macOS M-Series).

---

## Installation & Usage

### Prerequisites

- Docker & Docker Compose
- 8GB+ RAM recommended (for Llama 3.1)

### 1. Clone & Run

```bash
git clone https://github.com/YOUR_USERNAME/config-pilot.git
cd config-pilot

# Start the stack (This will pull the 4GB model automatically)
docker compose up --build
```

### 2. Send a Request

Once the containers are up, you can talk to the bot:

```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "Set tournament memory to 2048mb"}'
```

---

## Project Structure

| Directory | Description |
|---|---|
| `bot-server/` | Core logic (no frameworks, pure Python) |
| `schema-server/` | Serves JSON schemas |
| `values-server/` | Serves current config values |
| `data/` | Shared volume for JSON files |
| `docker-compose.yml` | Orchestration |


---

## License

MIT License. Feel free to fork and learn!
