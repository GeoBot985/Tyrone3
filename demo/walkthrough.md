# Demo Walkthrough

This walkthrough assumes a fresh shell in the repo root.

## 1. Seed The Demo Corpus

```bash
python demo/seed.py
```

What this does:

- rebuilds the synthetic eval corpus under `eval/corpus/`
- rebuilds the isolated `eval/eval.db`
- copies that database into `rag_v2.db` so the web UI has content

## 2. Start The App

```bash
$env:OLLAMA_FAKE="1"
python main.py
```

Open `http://127.0.0.1:8000`.

## 3. Capture The Portfolio Screenshots

Use a wide desktop viewport so the three panels are visible.

### Screenshot 1: Overview

- Keep the app on the landing page.
- Show the pinned knowledge base, the main chat panel, and the debug panel.
- Save as `docs/img/01-overview.png`.

### Screenshot 2: Document Mode

- Set mode to `document`.
- Ask: `What is the lunch stipend cap?`
- Capture the answer, evidence panel, and confidence badge.
- Save as `docs/img/02-document-mode.png`.

### Screenshot 3: Chat Mode

- Switch to `chat`.
- Select `alpha_policy.txt` in the corpus sidebar.
- Ask: `What extension reaches the security desk?`
- Capture the chat grounding banner and the selected document state.
- Save as `docs/img/03-chat-mode.png`.

### Screenshot 4: Personal Mode

- Switch to `personal`.
- Ask: `Remember that my demo token is Atlas-47.`
- Then ask: `What is my demo token?`
- Capture the personal mode state, debug trace, and mode switch.
- Save as `docs/img/04-personal-mode.png`.

## 4. Run The Gate

```bash
python -m eval.scorecard
```

The release gate should print all measured metrics as passing.
