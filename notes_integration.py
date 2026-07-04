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

def create_note(title: str, folder: str, url: str, summary_body: str) -> None:
    """
    Creates a new note inside the specified folder in Apple Notes.
    The body is formatted strictly as:
    <a href='[url]'>[url]</a><br><br><h1>[title]</h1><br>[summary_body]
    """
    # Build HTML body according to specification
    body_html = f"<a href='{url}'>{url}</a><br><br><h1>{title}</h1><br>{summary_body}"
    
    # In AppleScript, newlines in the body parameter can sometimes cause formatting issues, 
    # but Apple Notes HTML parser handles standard HTML tag <br> and <p> for paragraphs.
    # To be safe, we preserve the line breaks by replacing them with HTML <br> or paragraphs
    # if they are not already HTML.
    
    escaped_folder = escape_applescript_string(folder)
    escaped_body = escape_applescript_string(body_html)
    
    script = f'''
    tell application "Notes"
        set targetFolder to folder "{escaped_folder}"
        tell targetFolder
            make new note with properties {{body:"{escaped_body}"}}
        end tell
    end tell
    '''
    run_applescript(script)
