import subprocess
import sys

def escape_applescript_string(s: str) -> str:
    """
    Escapes double quotes and backslashes for use within AppleScript double-quoted string literals.
    """
    if not s:
        return ""
    # Escape backslashes first, then double quotes.
    return s.replace("\\", "\\\\").replace('"', '\\"')

def run_applescript(script: str) -> str:
    """
    Executes the given AppleScript using osascript via standard input.
    """
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        text=True,
        capture_output=True
    )
    if result.returncode != 0:
        error_msg = result.stderr.strip()
        print(f"AppleScript execution failed: {error_msg}", file=sys.stderr)
        raise RuntimeError(f"AppleScript Error: {error_msg}")
    return result.stdout

def ensure_folder(folder_name: str) -> None:
    """
    Creates the Apple Notes folder if it is missing.
    """
    escaped_folder = escape_applescript_string(folder_name)
    script = f'''
    tell application "Notes"
        if not (exists folder "{escaped_folder}") then
            make new folder with properties {{name:"{escaped_folder}"}}
        end if
    end tell
    '''
    run_applescript(script)

def create_note(
    reporting_title: str,
    folder: str,
    video_url: str,
    original_title: str,
    author: str,
    html_summary: str,
) -> None:
    """
    Creates a new note inside the specified folder in Apple Notes.

    Strict vertical HTML hierarchy:
      Line 1: <h1>{reporting_title}</h1>
      Line 2: <br><br>
      Line 3: <b>Source Link:</b> <a href="{video_url}">{video_url}</a>
      Line 4: <br><br>
      Line 5: <h3><i>Original Title: {original_title} | Source: {author}</i></h3>
      Line 6: <br><br>
      Line 7: {html_summary}

    IMPORTANT: AppleScript double-quoted string literals cannot contain real newline
    characters — they appear as literal '\\n' in the note.
    All newlines are converted to HTML <br> tags BEFORE escaping.
    """
    body_html = (
        # Line 1: reporting_title — MUST be first so Apple Notes uses it as the sidebar title
        f"<h1>{reporting_title}</h1>"
        # Line 2
        f"<br><br>"
        # Line 3: clickable raw text link
        f"<b>Source Link:</b> <a href=\"{video_url}\">{video_url}</a>"
        # Line 4
        f"<br><br>"
        # Line 5: metadata subtitle
        f"<h3><i>Original Title: {original_title} | Source: {author}</i></h3>"
        # Line 6
        f"<br><br>"
        # Line 7: cleaned HTML summary body
        f"{html_summary}"
    )

    # Sanitize real newlines → <br> BEFORE AppleScript escaping.
    # This prevents literal '\n' from appearing in the note body.
    body_html = body_html.replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")

    escaped_folder = escape_applescript_string(folder)
    escaped_body   = escape_applescript_string(body_html)

    script = f'''
    tell application "Notes"
        set targetFolder to folder "{escaped_folder}"
        tell targetFolder
            make new note with properties {{body:"{escaped_body}"}}
        end tell
    end tell
    '''
    run_applescript(script)

