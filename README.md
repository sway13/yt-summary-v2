# YouTube to Apple Notes CLI Pipeline

A modular and decoupled Python CLI utility designed to capture YouTube video transcripts, classify them, summarize them using the modern Gemini GenAI SDK, and automatically save the structured summaries directly to Apple Notes.

This project is built to run on-demand (e.g., triggered via a macOS Shortcut or CLI invocation), rather than running as an always-on server.

## Architecture

The project has a strictly modular and decoupled structure to avoid vendor lock-in and make it easy to modify specific behaviors independently:

```
yt-summary-v2/
├── themes_config.json      # Central business logic (Leisure filter keywords & Theme-based styling rules)
├── llm_gateway.py          # LLM abstraction layer using the Google GenAI SDK (easy to swap for other SDKs)
├── notes_integration.py    # macOS Bridge communicating with Apple Notes via subprocess and AppleScript
├── process_video.py        # Central pipeline controller and orchestrator
├── shortcut_wrapper.sh     # macOS Shortcut wrapper script that handles virtual environments & logging
├── requirements.txt        # Package dependencies
└── .gitignore              # Files ignored by git
```

### Module Descriptions
*   **[themes_config.json](themes_config.json)**: Stores configure variables like `ignore_keywords` (which immediately terminates execution if matched) and `themes` (which maps categories to specific formatting instructions).
*   **[llm_gateway.py](llm_gateway.py)**: Provider-agnostic gateway. Communicates with Gemini (`gemini-2.5-flash` by default) utilizing `google-genai` and reads the API key from a `.env` file.
*   **[notes_integration.py](notes_integration.py)**: Creates folders and notes in Apple Notes via safe `osascript` calls, handling string escaping to prevent syntax injection.
*   **[process_video.py](process_video.py)**: Central runtime controller. Fetches video metadata (`yt-dlp`), retrieves video transcripts (`youtube-transcript-api`), triggers local and LLM rejection filters, and routes results to the Notes integration.
*   **[shortcut_wrapper.sh](shortcut_wrapper.sh)**: Executable bash script that sets up and activates the virtual environment, pulls inputs from either clipboard or parameters, executes the controller, and appends outputs to `yt_pipeline.log`.

---

## Setup & Installation

### 1. Set Up Environment Variables
Create a `.env` file in the project root directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here

# Optional overrides
# GEMINI_MODEL_NAME=gemini-2.5-flash
```

### 2. Install Dependencies
Initialize your virtual environment and install the required modules:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Run from Command Line
Pass the YouTube URL directly:
```bash
./shortcut_wrapper.sh "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### Run using Clipboard
If you call `./shortcut_wrapper.sh` without arguments, it will automatically pull the YouTube URL from your macOS system clipboard (using `pbpaste`).

### Hook to macOS Shortcuts
To create an on-demand shortcut:
1. Open the macOS **Shortcuts** app and create a new Shortcut.
2. Add a **Run Shell Script** action.
3. Select shell: `/bin/bash`.
4. Configure the command:
   ```bash
   /Users/shreypadhi/Software/yt-summary-v2/shortcut_wrapper.sh "$1"
   ```
5. You can trigger this shortcut via Quick Actions, Services menu, or a custom keyboard shortcut.
