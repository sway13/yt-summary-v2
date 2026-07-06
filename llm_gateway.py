import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def generate_summary(transcript: str, system_prompt: str) -> str:
    """
    Generates a structured JSON summary of the provided transcript using the Gemini API.

    response_mime_type="application/json" instructs the API to return raw JSON
    with no markdown code fences, eliminating the need for fence-stripping.

    This function is provider-agnostic from the perspective of the main controller.
    To swap providers in the future, only the implementation inside this function
    needs to be modified.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please create a .env file in the project root containing:\n"
            "GEMINI_API_KEY=your_api_key_here"
        )

    # Initialize the Google GenAI client
    client = genai.Client(api_key=api_key)

    # Read model name from env or default to gemini-2.5-flash
    model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    # Strip any leading 'models/' prefix — the SDK expects the raw model ID
    if model_name.startswith("models/"):
        model_name = model_name[len("models/"):]

    # Inject strict formatting constraints exactly as written per audit requirements
    rules_path = os.path.join(os.path.dirname(__file__), "formatting_rules", "FORMATTING_RULES.md")
    with open(rules_path, "r") as f:
        formatting_rules = f.read()
    
    final_system_prompt = f"{system_prompt}\n\n---\n{formatting_rules}"

    response = client.models.generate_content(
        model=model_name,
        contents=transcript,
        config=types.GenerateContentConfig(
            system_instruction=final_system_prompt,
            # NOTE: response_mime_type="application/json" is intentionally NOT set.
            # When it is set, Gemini embeds literal newline characters (not \n escape
            # sequences) inside JSON string values, producing invalid JSON that
            # json.loads() rejects. Without it, Gemini properly escapes its output
            # and json-repair in parse_llm_response() handles any wrapping.
            safety_settings=[
                # BLOCK_ONLY_HIGH: only block content rated HIGH severity.
                # The server-side foundational safety layer (CSAM, terrorism, etc.)
                # cannot be overridden and will still apply regardless of these settings.
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                    threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
                ),
            ],
        ),
    )

    # Guard against a None text payload before calling .strip().
    # response.text is None when the backend severs the response (e.g. server-side
    # hardcoded safety layer for extreme content). With BLOCK_ONLY_HIGH configured,
    # this is unlikely to be a standard content-policy block — the actual cause
    # will be surfaced by finish_reason for debugging.
    if response.text is None:
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise RuntimeError(
            f"Gemini returned no text. Likely cause: safety filter block "
            f"(finish_reason={finish_reason}). Check pipeline logs for debugging."
        )

    raw = response.text.strip()
    print(f"[llm_gateway] Raw API response (first 300 chars): {raw[:300]}") 

    # Return the raw string as-is. json-repair in parse_llm_response() handles all
    # malformed JSON cleanup: markdown fences, bare newlines, unescaped quotes, etc.
    return raw
