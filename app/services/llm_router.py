from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
import os

# -----------------------
# ✅ GEMINI (working models)
# -----------------------
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",   #  SAFE + AVAILABLE
    api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3
)

# -----------------------
# ✅ GROQ (UPDATED MODEL)
# -----------------------
groq_llm = ChatGroq(
    model="llama-3.1-70b-versatile",   # ✅ REPLACE 70B (deprecated)
    api_key=os.getenv("GROQ_API_KEY")
)

# -----------------------
# 🧠 SMART ROUTER
# -----------------------
def call_llm(prompt, mode="auto"):
    try:
        if mode == "groq":
            return groq_llm.invoke(prompt)

        if mode == "gemini":
            return gemini_llm.invoke(prompt)

        # AUTO → try Gemini first
        return gemini_llm.invoke(prompt)

    except Exception as e:
        print("⚠️ Gemini failed → fallback to Groq:", e)

        try:
            return groq_llm.invoke(prompt)
        except Exception as e2:
            print("❌ Groq also failed:", e2)

            # 🚨 FINAL SAFETY FALLBACK (VERY IMPORTANT)
            return type("Fallback", (), {
                "content": "⚠️ AI service temporarily unavailable. Please try again."
            })()
