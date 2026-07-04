# Data Directory
> **This is the single source of truth for all variable names, types, and data flows in the yt-summary-v2 pipeline.**
> Every prompt, bugfix, or feature request MUST be cross-checked against this document before any code is written.
> If a new variable is introduced, this document must be updated in the same change.

---

## Master Variable Registry

### Tier 1 — LLM JSON Keys (Locked Names)
These are the exact key names the LLM is instructed to produce. They must never be renamed, aliased, or accessed by a string other than what is listed here.

| Variable | JSON Key | Type | Source | Description |
|---|---|---|---|---|
| `category` | `"category"` | `str` | LLM JSON output | Lowercase track tag; must match a key in `themes_config.json > tracks`. Used internally as `track_tag` after validation. |
| `reporting_title` | `"reporting_title"` | `str` | LLM JSON output | Compressed, journalistic note title. Becomes the Apple Notes sidebar title and `<h1>`. |
| `summary_markdown` | `"summary_markdown"` | `str` | LLM JSON output | Raw markdown body content from Gemini. Fed into the cleaning and conversion pipeline. |

### Tier 2 — Pipeline-Derived Variables (Locked Names)
These are created by transforming Tier 1 variables. Their names must not be changed.

| Variable | Type | Derived From | Where Created | Description |
|---|---|---|---|---|
| `track_tag` | `str` | `category` | `parse_llm_response()` return | Validated category; falls back to `"Uncategorized"` if not in `valid_tracks`. |
| `html_summary` | `str` | `summary_markdown` | `main()` step 7 | **Final** HTML body. Created by: `markdown.markdown(...)`. Never use `summary_html`. |
| `folder_name` | `str` | `track_tag` + `themes_config.json` | `main()` step 9 | Resolved Apple Notes folder. Falls back to `"Uncategorized"`. |

### Tier 3 — Video Metadata Variables (Locked Names)
Extracted from YouTube via yt-dlp. Passed through to `create_note()` as-is.

| Variable | Dict Key | Type | Source | Maps to `create_note()` param |
|---|---|---|---|---|
| `yt_title` | `video_info['title']` | `str` | yt-dlp `info['title']` | `original_title` |
| `video_id` | `video_info['id']` | `str` | yt-dlp `info['id']` | (internal only) |
| `uploader` | `video_info['uploader']` | `str` | yt-dlp `info['uploader']` or `info['channel']` | `author` |
| `url` | `sys.argv[1]` | `str` | CLI argument | `video_url` |

---

## `create_note()` Parameter Contract
The function signature in `notes_integration.py` must always match this table exactly.

| Parameter Name | Maps From (in main) | Type | Notes |
|---|---|---|---|
| `reporting_title` | `reporting_title` | `str` | First element in note HTML; drives sidebar title |
| `folder` | `folder_name` | `str` | Target Apple Notes folder name |
| `video_url` | `url` | `str` | Used in anchor tag and thumbnail link |
| `original_title` | `yt_title` | `str` | Raw YouTube title; shown in subtitle line |
| `author` | `uploader` | `str` | Channel/creator name; shown in subtitle line |
| `html_summary` | `html_summary` | `str` | Cleaned, converted HTML body content |

---

## HTML Template — Vertical Assembly Order
The note body must always be assembled in this exact order inside `create_note()`.

```
Line 1:  <h1>{reporting_title}</h1>
Line 2:  <br><br>
Line 3:  <b>Source Link:</b> <a href="{video_url}">{video_url}</a>
Line 4:  <br><br>
Line 5:  <h3><i>Original Title: {original_title} | Source: {author}</i></h3>
Line 6:  <br><br>
Line 7:  {html_summary}
```

---

## Variable Lifecycle Flow

```
CLI url  (sys.argv[1])
    │
    ├─► extract_video_info()
    │       └─► yt_title, video_id, uploader
    │
    ├─► get_transcript(video_id) ──► transcript
    │
    ├─► llm_gateway.generate_summary(transcript, system_prompt) ──► raw JSON string
    │       └─► parse_llm_response()
    │               ├─► category   (→ track_tag after validation)
    │               ├─► reporting_title
    │               └─► summary_markdown
    │
    ├─► markdown.markdown(summary_markdown) ──► html_summary   ← LOCKED NAME
    │
    └─► notes_integration.create_note(
            reporting_title=reporting_title,
            folder=folder_name,
            video_url=url,
            original_title=yt_title,
            author=uploader,
            html_summary=html_summary,
        )
```

---

## Forbidden Aliases
The following names have appeared in previous versions and caused crashes or silent bugs. They are permanently retired.

| Retired Name | Correct Name | Reason Retired |
|---|---|---|
| `summary_html` | `html_summary` | Caused `TypeError` in `create_note()` call |
| `title` (in main) | `yt_title` | Ambiguous; confused with `reporting_title` |
| `url` (in create_note param) | `video_url` | Parameter renamed for clarity in notes_integration |
| `yt_title` (in create_note param) | `original_title` | Parameter renamed for clarity in notes_integration |
| `uploader` (in create_note param) | `author` | Parameter renamed for clarity in notes_integration |
| `summary_body` (in create_note param) | `html_summary` | Old name before lifecycle standardization |

---

## Guard Checklist
Run through this mentally before implementing any future change:

- [ ] Does the LLM JSON key string exactly match the Tier 1 table?
- [ ] Is the final HTML variable named `html_summary` (never `summary_html`)?
- [ ] Does every `create_note()` call use the exact parameter names in the contract table?
- [ ] Does the HTML assembly follow the 7-line template order exactly?
- [ ] If a new variable is added, has this document been updated in the same change?
