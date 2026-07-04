import os
from google import genai
from google.genai import types
from dotenv import load_dotenv 

# Load environment variables from .env file
load_dotenv()

def generate_summary(transcript: str, system_prompt: str) -> str:
    """
    Generates a summary of the provided transcript using the LLM provider.
    Currently configured to use Google's Gemini API via the google-genai SDK.
    
    This function is provider-agnostic from the perspective of the main controller.
    To swap to Anthropic or another provider in the future, only the implementation 
    inside this function needs to be modified.
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
    
    # Strip any leading 'models/' prefix since the new SDK expects the raw model ID
    if model_name.startswith("models/"):
        model_name = model_name[len("models/"):]
        
    response = client.models.generate_content(
        model=model_name,
        contents=transcript,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
        ),
    )
    
    return response.text.strip()

