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

    response = client.models.generate_content(
        model=model_name,
        contents=transcript,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            # NOTE: response_mime_type="application/json" is intentionally NOT set.
            # When it is set, Gemini embeds literal newline characters (not \n escape
            # sequences) inside JSON string values, producing invalid JSON that
            # json.loads() rejects. Without it, Gemini properly escapes its output
            # and the brace-extraction in parse_llm_response() handles any wrapping.
        ),
    )

    raw = response.text.strip()
    print(f"[llm_gateway] Raw API response (first 300 chars): {raw[:300]}")
    return raw

