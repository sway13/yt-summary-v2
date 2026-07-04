import sys
import json
import os
import re
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

def extract_video_info(url: str) -> dict:
    """Extracts video title and ID using yt-dlp."""
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title'),
                'id': info.get('id'),
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

def build_system_prompt(config: dict) -> str:
    """Constructs the system prompt instructing the LLM on classification, filtering, and theme styling."""
    ignore_keywords = config.get("ignore_keywords", [])
    themes = config.get("themes", {})
    default_theme_instructions = config.get("default_theme", "Provide a standard structured summary.")
    
    themes_str = ""
    for category, instruction in themes.items():
        themes_str += f"- Theme: {category}\n  Instructions: {instruction}\n"
        
    system_prompt = f"""You are an expert video content classifier and summarizer.

1. CRITICAL FILTERING STEP:
Check if the transcript discusses leisure/entertainment topics, including: {', '.join(ignore_keywords)}.
If the video matches any of these ignore categories, you MUST reply with EXACTLY the single word: IGNORE
Do not add any explanations, markdown, or punctuation. Just reply 'IGNORE'.

2. SUMMARIZATION & FORMATTING:
If the video is NOT a leisure video, classify it into one of these themes and follow the specific instructions:
{themes_str}
If the video does not fit any specific theme listed above, summarize it according to these instructions:
{default_theme_instructions}

Rules for Summarization:
- Start directly with the summary content. Do NOT prefix with "Here is the summary" or other introductory text.
- Use standard HTML tags (such as <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <br>) for formatting.
- Do NOT use markdown syntax (like #, ##, **, -, *) in the summary text. Write only clean HTML so it displays properly in Apple Notes.
"""
    return system_prompt

def convert_markdown_to_html(text: str) -> str:
    """
    Fallback converter to turn basic markdown patterns into HTML
    in case the LLM neglects the prompt instruction to write HTML.
    """
    # Check if text already has HTML headings/paragraphs; if so, skip conversion.
    if "<h" in text or "<p>" in text or "<li>" in text:
        return text
        
    # Convert bold **text** to <strong>text</strong>
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    # Convert italic *text* to <em>text</em>
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    # Convert headers
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    # Convert bullet points
    text = re.sub(r'^[-*] (.*?)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    
    # Process lines to structure paragraphs and list wrappers
    lines = text.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                formatted_lines.append("</ul>")
                in_list = False
            continue
            
        if line.startswith("<li>"):
            if not in_list:
                formatted_lines.append("<ul>")
                in_list = True
            formatted_lines.append(line)
        elif line.startswith("<h"):
            if in_list:
                formatted_lines.append("</ul>")
                in_list = False
            formatted_lines.append(line)
        else:
            if in_list:
                formatted_lines.append("</ul>")
                in_list = False
            formatted_lines.append(f"<p>{line}</p>")
            
    if in_list:
        formatted_lines.append("</ul>")
        
    return "\n".join(formatted_lines)

def main():
    if len(sys.argv) < 2:
        print("Error: Missing YouTube URL argument.", file=sys.stderr)
        print("Usage: python process_video.py <youtube_url>", file=sys.stderr)
        sys.exit(1)
        
    url = sys.argv[1]
    
    try:
        # 1. Load config
        config = load_config()
        ignore_keywords = config.get("ignore_keywords", [])
        
        # 2. Extract metadata
        print(f"Fetching video info for: {url}")
        video_info = extract_video_info(url)
        title = video_info['title']
        video_id = video_info['id']
        print(f"Video Title: {title}")
        
        # 3. Local Title Keyword Check
        if check_title_for_ignore(title, ignore_keywords):
            print("TERMINATION: Video title matches leisure keyword. Ignoring.")
            sys.exit(0)
            
        # 4. Fetch transcript
        print("Retrieving video transcript...")
        transcript = get_transcript(video_id)
        
        # 5. Get summary from LLM
        print("Sending to LLM Gateway for categorization and summarization...")
        system_prompt = build_system_prompt(config)
        summary_result = llm_gateway.generate_summary(transcript, system_prompt)
        
        # 6. LLM Ignore Check
        if summary_result.strip().upper() == "IGNORE":
            print("TERMINATION: LLM categorized this video as a leisure topic. Ignoring.")
            sys.exit(0)
            
        # 7. Convert formatting if LLM generated markdown
        summary_html = convert_markdown_to_html(summary_result)
        
        # 8. Apple Notes Integration
        folder_name = config.get("apple_notes_folder", "YouTube Summaries")
        print(f"Ensuring folder '{folder_name}' exists in Apple Notes...")
        notes_integration.ensure_folder(folder_name)
        
        print("Creating note in Apple Notes...")
        notes_integration.create_note(title, folder_name, url, summary_html)
        
        print(f"SUCCESS: Note '{title}' successfully added to folder '{folder_name}'.")
        
    except Exception as e:
        print(f"ERROR: Pipeline execution failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
