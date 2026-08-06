import re
import logging
import requests
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.AICleanup")

FILLER_PATTERNS = [
    (r'(?i)\b(e{2,}|ı{2,}|a{2,})\b', ''),
    (r'(?i)\b(h+m+)+(\b|\s)', ''),
    (r'(?i)\b(ı+h+m+)+(\b|\s)', ''),
    (r'(?i)^\s*(?:(?:yani|şey|işte|hani|falan|böyle|ya)\b[,\s]*)+', ''),
    (r'(?i)^\s*(yani|şey|ee|ıı)\s*,\s*', ''),
    (r'(?i)\s+,\s*(yani|şey|ee|ıı)\s*,', ','),
]

class AICleanupEngine:
    def __init__(self):
        pass

    def clean_text(self, raw_text: str) -> str:
        if not raw_text or not raw_text.strip():
            return ""

        text = raw_text.strip()
        enabled = config_manager.get("ai_cleanup_enabled", True)
        op_mode = config_manager.get("operation_mode", "dictation")

        if not enabled and op_mode != "assistant":
            return text

        provider = config_manager.get("ai_cleanup_provider", "rule_based")
        prompt = config_manager.get_effective_prompt()

        if op_mode == "assistant":
            prompt = "Sen güçlü bir Yapay Zeka Komut Asistanısın. Kullanıcı mikrofona bir komut veya soru verdi. Kullanıcının söylediği görevi doğrudan yerine getir ve cevabı açık, anlaşılır metin olarak yaz."

        # Provider Dispatching
        if provider == "custom_ollama":
            custom_url = config_manager.get("custom_api_base_url", "http://localhost:11434/v1")
            custom_model = config_manager.get("custom_model_name", "llama3.2")
            result = self._clean_with_openai_compatible(text, custom_url, "", custom_model, prompt)
            if result:
                return result

        elif provider == "groq":
            api_key = config_manager.get("api_key_groq", "")
            if api_key:
                model = config_manager.get("ai_model_groq", "llama-3.3-70b-versatile")
                result = self._clean_with_openai_compatible(text, "https://api.groq.com/openai/v1", api_key, model, prompt)
                if result:
                    return result

        elif provider == "openai":
            api_key = config_manager.get("api_key_openai", "")
            if api_key:
                model = config_manager.get("ai_model_openai", "gpt-4o-mini")
                result = self._clean_with_openai_compatible(text, "https://api.openai.com/v1", api_key, model, prompt)
                if result:
                    return result

        elif provider == "gemini":
            api_key = config_manager.get("api_key_gemini", "")
            if api_key:
                model = config_manager.get("ai_model_gemini", "gemini-3.6-flash")
                result = self._clean_with_gemini(text, api_key, model, prompt)
                if result:
                    return result

        elif provider == "grok":
            api_key = config_manager.get("api_key_grok", "")
            if api_key:
                model = config_manager.get("ai_model_grok", "grok-beta")
                result = self._clean_with_openai_compatible(text, "https://api.x.ai/v1", api_key, model, prompt)
                if result:
                    return result

        # Fallback to Rule-Based
        return self._clean_rule_based(text)

    def _clean_rule_based(self, text: str) -> str:
        cleaned = text
        for pattern, replacement in FILLER_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned)

        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\s+([.,!?:;])', r'\1', cleaned)

        if cleaned and len(cleaned) > 0:
            cleaned = cleaned[0].upper() + cleaned[1:]

        if cleaned and not cleaned[-1] in ['.', '!', '?', ':', ';']:
            cleaned += '.'

        logger.info("Rule-based cleanup completed (%d -> %d characters).", len(text), len(cleaned))
        return cleaned

    def _clean_with_openai_compatible(self, text: str, base_url: str, api_key: str, model_name: str, prompt: str) -> str:
        try:
            url = base_url.rstrip('/') + "/chat/completions"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            body = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.1
            }
            resp = requests.post(url, headers=headers, json=body, timeout=8)
            if resp.status_code == 200:
                result = resp.json()['choices'][0]['message']['content'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info("LLM cleanup completed with model '%s' (%d characters).", model_name, len(result))
                return result
            else:
                logger.warning("LLM API returned HTTP %s.", resp.status_code)
        except Exception as e:
            logger.error(f"LLM API error ({base_url}): {e}")
        return None

    def _clean_with_gemini(self, text: str, api_key: str, model_name: str, prompt: str) -> str:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": f"{prompt}\n\nGirdi Metni:\n{text}"}]
                }]
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                result = data['candidates'][0]['content']['parts'][0]['text'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info("Gemini cleanup completed (%d characters).", len(result))
                return result
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
        return None

ai_cleanup_engine = AICleanupEngine()
