import re
import logging
import requests
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.AICleanup")

# Context-aware hesitation sounds (matches isolated "eee", "hmmm", "ııı", etc.)
FILLER_PATTERNS = [
    (r'(?i)\b(e{2,}|ı{2,}|a{2,})\b', ''),            # isolated "eee", "ııı"
    (r'(?i)\b(h+m+)+(\b|\s)', ''),                  # isolated "hmmm", "hm"
    (r'(?i)\b(ı+h+m+)+(\b|\s)', ''),                # isolated "ıhm"
    (r'(?i)^\s*(yani|şey|ee|ıı)\s*,\s*', ''),       # hesitation at start of sentence
    (r'(?i)\s+,\s*(yani|şey|ee|ıı)\s*,', ','),      # hesitation inside pauses
]

class AICleanupEngine:
    def __init__(self):
        pass

    def clean_text(self, raw_text: str) -> str:
        if not raw_text or not raw_text.strip():
            return ""

        text = raw_text.strip()
        enabled = config_manager.get("ai_cleanup_enabled", True)
        if not enabled:
            return text

        provider = config_manager.get("ai_cleanup_provider", "rule_based")
        api_key_groq = config_manager.get("api_key_groq", "")
        api_key_openai = config_manager.get("api_key_openai", "")
        api_key_gemini = config_manager.get("api_key_gemini", "")
        api_key_grok = config_manager.get("api_key_grok", "")

        # Try LLM cleanup if configured
        if provider == "groq" and api_key_groq:
            llm_text = self._clean_with_groq(text, api_key_groq)
            if llm_text:
                return llm_text
        elif provider == "openai" and api_key_openai:
            llm_text = self._clean_with_openai(text, api_key_openai)
            if llm_text:
                return llm_text
        elif provider == "gemini" and api_key_gemini:
            llm_text = self._clean_with_gemini(text, api_key_gemini)
            if llm_text:
                return llm_text
        elif provider == "grok" and api_key_grok:
            llm_text = self._clean_with_grok(text, api_key_grok)
            if llm_text:
                return llm_text

        # Fallback to fast Rule-Based Cleanup
        return self._clean_rule_based(text)

    def _clean_rule_based(self, text: str) -> str:
        cleaned = text

        for pattern, replacement in FILLER_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned)

        # Fix multiple spaces and punctuation formatting
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\s+([.,!?:;])', r'\1', cleaned)

        # Ensure sentence starts with capital letter
        if cleaned and len(cleaned) > 0:
            cleaned = cleaned[0].upper() + cleaned[1:]

        # Ensure ending punctuation if sentence looks complete
        if cleaned and not cleaned[-1] in ['.', '!', '?', ':', ';']:
            cleaned += '.'

        logger.info(f"Rule-based cleaned: '{text}' -> '{cleaned}'")
        return cleaned

    def _clean_with_groq(self, text: str, api_key: str) -> str:
        try:
            prompt = config_manager.get("custom_prompt", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.1,
                "max_tokens": 512
            }
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body, timeout=5)
            if resp.status_code == 200:
                result = resp.json()['choices'][0]['message']['content'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info(f"Groq LLM cleaned: '{text}' -> '{result}'")
                return result
        except Exception as e:
            logger.error(f"Groq LLM cleanup failed: {e}")
        return None

    def _clean_with_openai(self, text: str, api_key: str) -> str:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            prompt = config_manager.get("custom_prompt", "")
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1
            )
            result = response.choices[0].message.content.strip()
            if result.startswith('"') and result.endswith('"'):
                result = result[1:-1]
            logger.info(f"OpenAI LLM cleaned: '{text}' -> '{result}'")
            return result
        except Exception as e:
            logger.error(f"OpenAI LLM cleanup failed: {e}")
        return None

    def _clean_with_gemini(self, text: str, api_key: str) -> str:
        try:
            prompt = config_manager.get("custom_prompt", "")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": f"{prompt}\n\nTemizlenecek Metin:\n{text}"}]
                }]
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                result = data['candidates'][0]['content']['parts'][0]['text'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info(f"Gemini LLM cleaned: '{text}' -> '{result}'")
                return result
        except Exception as e:
            logger.error(f"Gemini LLM cleanup failed: {e}")
        return None

    def _clean_with_grok(self, text: str, api_key: str) -> str:
        try:
            prompt = config_manager.get("custom_prompt", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": "grok-beta",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.1
            }
            resp = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=body, timeout=6)
            if resp.status_code == 200:
                result = resp.json()['choices'][0]['message']['content'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info(f"xAI Grok LLM cleaned: '{text}' -> '{result}'")
                return result
        except Exception as e:
            logger.error(f"xAI Grok LLM cleanup failed: {e}")
        return None

ai_cleanup_engine = AICleanupEngine()
