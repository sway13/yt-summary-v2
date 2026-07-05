import sys
import json
import os
import re
import markdown
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import llm_gateway
import notes_integration

def load_config(config_path="themes_config.json") -> dict:
    """Loads themes and keyword settings from the JSON config file."""
    if not os.path.exists(config_path):
        # Fallback to current script directory if run from another folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, config_path)
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found at themes_config.json")

    with open(config_path, "r") as f:
        return json.load(f)

def load_system_directions(path="system_directions") -> str:
    """Loads the master system directive from the system_directions file."""
    if not os.path.exists(path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"System directions file not found at: {path}")
    with open(path, "r") as f:
        return f.read()

def extract_video_info(url: str) -> dict:
    """Extracts video title, ID, uploader/channel name, and low-res thumbnail URL using yt-dlp."""
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            video_id = info.get('id')
            return {
                'title': info.get('title'),
                'id': video_id,
                # 'uploader' is the channel/creator name on YouTube
                'uploader': info.get('uploader') or info.get('channel') or '[DATA NOT PROVIDED]',
            }
        except Exception as e:
            raise RuntimeError(f"Failed to extract video details using yt-dlp: {e}")

def get_transcript(video_id: str) -> str:
    """Fetches the transcript text using youtube-transcript-api with language fallbacks."""
    api = YouTubeTranscriptApi()
    try:
        # Attempt default retrieval
        transcript_list = api.fetch(video_id)
        return " ".join([t.text for t in transcript_list])
    except Exception as e:
        # Fallback: List available transcripts and find English or fallback to first available
        try:
            transcript_list = api.list(video_id)
            try:
                transcript = transcript_list.find_transcript(['en'])
            except Exception:
                # Try finding auto-generated English
                try:
                    transcript = transcript_list.find_generated_transcript(['en'])
                except Exception:
                    # Return the first transcript regardless of language
                    transcript = next(iter(transcript_list))
            return " ".join([t.text for t in transcript.fetch()])
        except Exception as inner_e:
            raise RuntimeError(
                f"Could not retrieve transcript for video ID {video_id}.\n"
                f"Primary Error: {e}\nFallback Error: {inner_e}"
            )

def check_title_for_ignore(title: str, ignore_keywords: list) -> bool:
    """Performs a fast, case-insensitive keyword search on the video title."""
    title_lower = title.lower()
    for keyword in ignore_keywords:
        # Check if the keyword exists as a substring in the title
        if keyword.lower() in title_lower:
            return True
    return False

def build_system_prompt(config: dict, system_directions: str) -> str:
    """
    Constructs the master system prompt by embedding the system_directions file verbatim,
    then appending the valid category tags so the LLM knows exactly which keys to use.
    """
    tracks = config.get("tracks", {})
    valid_tags = list(tracks.keys())

    system_prompt = f"""{system_directions}

---
CATEGORY TAG CONSTRAINT:
The "category" field in your JSON output must be exactly one of the following lowercase keys
(these map directly to your target Apple Notes folders): {', '.join(valid_tags)}

If the content does not clearly match any single track, choose the closest one from the list above.
Do NOT invent new category names.
"""
    return system_prompt

def _repair_json_newlines(json_str: str) -> str:
    """
    Repairs JSON strings that contain unescaped control characters inside string
    values (the most common Gemini hallucination even with response_mime_type set).

    Uses a simple state machine to track whether the parser is inside a
    double-quoted string, and only escapes newlines/tabs/carriage-returns there.
    Structural whitespace between JSON tokens is left untouched so that
    json.loads() can still parse the key/value structure correctly.
    """
    result = []
    in_string = False
    escape_next = False

    for ch in json_str:
        if escape_next:
            # The previous character was a backslash — pass this char through as-is
            result.append(ch)
            escape_next = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')   # escape the bare newline
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)

    return ''.join(result)


def parse_llm_response(response: str, valid_tracks: list) -> tuple:
    """
    Parses the JSON LLM response into a (track_tag, reporting_title, summary_markdown) tuple.

    The system_directions mandate JSON with three keys:
      - "category"         : one of the valid track tags
      - "reporting_title"  : a compressed, journalistic note title
      - "summary_markdown" : the structured body content

    Extraction strategy: locate the first '{' and last '}' in the raw response and
    slice between them. This is immune to markdown fences, stray whitespace, the word
    'json', or any other wrapping a model might emit — regardless of response_mime_type.
    """
    raw = response.strip()

    # --- Bulletproof JSON extraction ---
    start = raw.find('{')
    end = raw.rfind('}')

    if start == -1 or end == -1 or end < start:
        print(f"WARNING: Could not locate a JSON object in the LLM response.")
        print(f"         Full raw response:\n{raw}")
        # Normalise literal \n sequences before returning so the fallback text
        # is still parseable by the markdown library downstream.
        return "Uncategorized", "Untitled Summary", raw.replace('\\n', '\n')

    json_str = raw[start:end + 1]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"WARNING: First JSON parse attempt failed ({e}). Attempting state-machine repair...")
        try:
            repaired = _repair_json_newlines(json_str)
            data = json.loads(repaired)
            print("JSON repair successful — unescaped control characters were fixed.")
        except json.JSONDecodeError as e2:
            print(f"WARNING: JSON repair also failed. Error: {e2}")
            print(f"         Extracted slice:\n{json_str[:500]}")
            print(f"         Full raw response:\n{raw}")
            return "Uncategorized", "Untitled Summary", raw.replace('\\n', '\n')

    # --- Strict variable mapping from the three mandated keys ---
    # Safe string extraction to prevent AttributeError if the LLM hallucinates nested objects
    raw_category = data.get("category", "")
    category = str(raw_category).strip().lower() if raw_category else ""

    raw_title = data.get("reporting_title", "Untitled Summary")
    reporting_title = str(raw_title).strip() if raw_title else "Untitled Summary"

    raw_summary = data.get("summary_markdown", "")

    # Type-Checking & Failsafe Flattening
    if isinstance(raw_summary, dict):
        # Flatten the dictionary hallucination by joining values
        summary_markdown = "\n\n".join(str(v) for v in raw_summary.values()).strip()
    elif isinstance(raw_summary, str):
        summary_markdown = raw_summary.strip()
    else:
        # Fallback for lists or other unexpected types
        summary_markdown = str(raw_summary).strip()

    # CRITICAL: Normalise any remaining literal '\n' two-character sequences into
    # real newlines. JSON encoding represents newlines as \n inside string values;
    # if the LLM embeds them as literals or the JSON parser leaves them as-is in
    # edge cases, the markdown library will see '### Header' on one giant line and
    # produce no HTML — causing raw markdown characters to appear in the note.
    summary_markdown = summary_markdown.replace('\\n', '\n')

    if not reporting_title:
        reporting_title = "Untitled Summary"
    if not summary_markdown:
        summary_markdown = "[DATA NOT PROVIDED]"

    if category not in valid_tracks:
        print(f"WARNING: LLM returned unrecognised category '{category}'.")
        print(f"         Routing note to 'Uncategorized' folder for manual review.")
        category = "Uncategorized"

    return category, reporting_title, summary_markdown


def main():
    if len(sys.argv) < 2:
        print("Error: Missing YouTube URL argument.", file=sys.stderr)
        print("Usage: python process_video.py <youtube_url>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]

    try:
        # 1. Load config and master system directive
        config = load_config()
        system_directions = load_system_directions()
        tracks = config.get("tracks", {})
        global_exclusions = config.get("global_exclusions", [])
        valid_tracks = list(tracks.keys())

        # 2. Extract metadata — title, video ID, creator, and thumbnail URL
        print(f"Fetching video info for: {url}")
        video_info = extract_video_info(url)
        yt_title       = video_info['title']
        video_id       = video_info['id']
        uploader       = video_info['uploader']
        print(f"Video Title: {yt_title}")
        print(f"Creator:     {uploader}")

        # 3. PRE-FILTER: Kill execution immediately if title matches a global exclusion
        if check_title_for_ignore(yt_title, global_exclusions):
            print("TERMINATION: Video title matches a global exclusion keyword. Ignoring.")
            sys.exit(0)

        # 4. Fetch transcript
        print("Retrieving video transcript...")
        transcript = get_transcript(video_id)

        # 5. LLM CLASSIFICATION: Gemini follows system_directions and returns JSON
        #    with keys: category, reporting_title, summary_markdown
        print("Sending to LLM Gateway for classification and summarization...")
        system_prompt = build_system_prompt(config, system_directions)
        llm_response = llm_gateway.generate_summary(transcript, system_prompt)

        # 6. Parse JSON response — strict variable mapping from the three mandated keys
        #    Output variables: category (as track_tag), reporting_title, summary_markdown
        track_tag, reporting_title, summary_markdown = parse_llm_response(llm_response, valid_tracks)
        print(f"LLM classified video under track: '{track_tag}'")
        print(f"Reporting title: {reporting_title}")

        # --- DATA DICTIONARY GUARDS: fail loudly if a master variable is missing ---
        if not isinstance(reporting_title, str) or not reporting_title:
            raise ValueError("ERROR: reporting_title variable is missing or not a string")
        if not isinstance(track_tag, str) or not track_tag:
            raise ValueError("ERROR: category (track_tag) variable is missing or not a string")
        if not isinstance(summary_markdown, str) or not summary_markdown:
            raise ValueError("ERROR: summary_markdown variable is missing or not a string")

        # 7. VARIABLE LIFECYCLE — Extract → Convert → strict name: html_summary
        #    Uses the standard 'markdown' library: handles ###, **, *, bullet points natively.
        #    No custom regex scrubbing — the library produces clean, correct HTML.
        html_summary = markdown.markdown(
            summary_markdown,
            extensions=['extra'],   # enables tables, fenced code, definition lists, etc.
        )

        if not isinstance(html_summary, str) or not html_summary:
            raise ValueError("ERROR: html_summary variable is missing or not a string after conversion")

        # 9. APPLESCRIPT HANDOFF: Resolve folder from track config.
        #    Falls back to 'Uncategorized' if the LLM returned an unknown category.
        if track_tag in tracks:
            folder_name = tracks[track_tag]["target_apple_notes_folder"]
        else:
            folder_name = "Uncategorized"
            print(f"Note: No folder mapping found for '{track_tag}'. Routing to '{folder_name}'.")
        print(f"Ensuring folder '{folder_name}' exists in Apple Notes...")
        notes_integration.ensure_folder(folder_name)

        # 10. Final assembly and note creation — each variable is named and guarded
        print("Creating note in Apple Notes...")
        try:
            notes_integration.create_note(
                reporting_title=reporting_title,
                folder=folder_name,
                video_url=url,
                original_title=yt_title,
                author=uploader,
                html_summary=html_summary,
            )
        except TypeError as te:
            # A TypeError here means a keyword argument name mismatch — name it explicitly
            missing = str(te)
            if "reporting_title" in missing:
                print("ERROR: reporting_title variable not found in create_note call", file=sys.stderr)
            elif "html_summary" in missing:
                print("ERROR: html_summary variable not found in create_note call", file=sys.stderr)
            elif "original_title" in missing:
                print("ERROR: original_title variable not found in create_note call", file=sys.stderr)
            elif "author" in missing:
                print("ERROR: author variable not found in create_note call", file=sys.stderr)
            else:
                print(f"ERROR: create_note call failed with argument error: {te}", file=sys.stderr)
            raise

        print(f"SUCCESS: Note '{reporting_title}' successfully added to folder '{folder_name}'.")

    except Exception as e:
        print(f"ERROR: Pipeline execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
