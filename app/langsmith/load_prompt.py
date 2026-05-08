# app/langsmith/load_prompt.py

import os
from langsmith import Client
from langchain_core.prompts import PromptTemplate

TEMPLATE_PROMPT_MAP = {
    "srs": "prompt_srs",
    "sprintreport": "prompt_sprint_report",
    "wbs": "prompt_wbs",
    "testcase": "prompt_testcase",
    "usermanual": "prompt_user_manual",
    "api": "prompt_api",
    "readme": "prompt_readme",
    "authenticate":"prompt_authen",
    "backend":"prompt_backend",
    "configuration":"prompt_configure",
    "database":"prompt_db",
    "risk":"prompt_risk",
    "deploy":"prompt_deploy",
    
}

DEFAULT_PROMPT = "doc_gen_prompt"


def load_prompt_from_langsmith(template_key: str = None):
    """
    Load prompt based on template key.
    Falls back to DEFAULT_PROMPT if key not found.
    Falls back to local prompt if LangSmith fails.
    """
    # Normalize key
    normalized = (template_key or "").lower().strip().replace(" ", "")
    
    # Select prompt name
    prompt_name = TEMPLATE_PROMPT_MAP.get(normalized, DEFAULT_PROMPT)
    
    print(f"📄 Template key: '{normalized}' → Prompt: '{prompt_name}'")

    try:
        LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
        if not LANGSMITH_API_KEY:
            raise EnvironmentError("Missing LANGSMITH_API_KEY")

        client = Client(api_key=LANGSMITH_API_KEY)
        prompt = client.pull_prompt(prompt_name, include_model=False)

        if not prompt:
            raise ValueError("LangSmith returned empty prompt")

        print(f"✅ Loaded prompt '{prompt_name}' from LangSmith.")
        return prompt

    except Exception as e:
        print(f"❌ Failed to load '{prompt_name}': {e}")

        # Try default if specific prompt failed
        if prompt_name != DEFAULT_PROMPT:
            print(f"⚠️ Retrying with default prompt '{DEFAULT_PROMPT}'")
            try:
                client = Client(api_key=os.getenv("LANGSMITH_API_KEY"))
                prompt = client.pull_prompt(DEFAULT_PROMPT, include_model=False)
                if prompt:
                    print(f"✅ Loaded default prompt '{DEFAULT_PROMPT}'")
                    return prompt
            except Exception as e2:
                print(f"❌ Default prompt also failed: {e2}")

        # Final fallback
        print("⚠️ Using hardcoded fallback prompt")
        return PromptTemplate.from_template(
            "You are a helpful document generator.\n\n{cleaned_pm_data}"
        )
