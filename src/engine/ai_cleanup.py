import re
import logging
import requests
from src.config import config_manager
from src.engine.provider_transport import (
    ProviderRequestCancelled, failure_from_exception, failure_from_response, run_cancellable,
)
from src.engine.stt_base import TranscriptionCancelled

logger = logging.getLogger("PrimeDictate.AICleanup")


class TextProcessingError(RuntimeError):
    pass


def _log_provider_failure(provider: str, error: Exception):
    status_code = getattr(error, "status_code", None)
    details = [f"error_type={type(error).__name__}"]
    if status_code is not None:
        details.append(f"http_status={status_code}")
    logger.error("%s text-processing request failed (%s).", provider, ", ".join(details))

FILLER_PATTERNS = [
    (r'(?i)\b(e{2,}|ı{2,}|a{2,})\b', ''),
    (r'(?i)\b(h+m+)+(\b|\s)', ''),
    (r'(?i)\b(ı+h+m+)+(\b|\s)', ''),
    (r'(?i)^\s*(?:(?:u+h+|u+m+|e+r+m+)\b[,\s]*)+', ''),
    (r'(?i)^\s*(?:(?:yani|şey|işte|hani|falan|böyle|ya)\b[,\s]*)+', ''),
    (r'(?i)^\s*(yani|şey|ee|ıı)\s*,\s*', ''),
    (r'(?i)\s+,\s*(yani|şey|ee|ıı)\s*,', ','),
]

class AICleanupEngine:
    def __init__(self):
        self.last_processing_info = {}

    def clean_text(self, raw_text: str, cancel_check=None) -> str:
        self.last_processing_info = {
            "enabled": False,
            "provider": None,
            "fallback_used": False,
            "fallback_policy": None,
            "failure": None,
        }
        if not raw_text or not raw_text.strip():
            return ""

        text = raw_text.strip()
        enabled = config_manager.get("ai_cleanup_enabled", True)

        if not enabled:
            return text

        provider = config_manager.get("ai_cleanup_provider", "rule_based")
        self.last_processing_info.update({"enabled": True, "provider": provider})
        prompt = config_manager.get_effective_prompt()

        if provider == "rule_based":
            return self._clean_rule_based(text)

        # Provider Dispatching
        if provider == "custom_ollama":
            custom_url = config_manager.get("custom_api_base_url", "http://localhost:11434/v1")
            custom_model = config_manager.get("custom_model_name", "llama3.2")
            result = self._clean_with_openai_compatible(text, custom_url, "", custom_model, prompt, cancel_check)
            if result:
                return result

        elif provider == "groq":
            api_key = config_manager.get("api_key_groq", "")
            if api_key:
                model = config_manager.get("ai_model_groq", "llama-3.3-70b-versatile")
                result = self._clean_with_openai_compatible(text, "https://api.groq.com/openai/v1", api_key, model, prompt, cancel_check)
                if result:
                    return result

        elif provider == "openai":
            api_key = config_manager.get("api_key_openai", "")
            if api_key:
                model = config_manager.get("ai_model_openai", "gpt-4o-mini")
                result = self._clean_with_openai_compatible(text, "https://api.openai.com/v1", api_key, model, prompt, cancel_check)
                if result:
                    return result

        elif provider == "gemini":
            api_key = config_manager.get("api_key_gemini", "")
            if api_key:
                model = config_manager.get("ai_model_gemini", "gemini-3.6-flash")
                result = self._clean_with_gemini(text, api_key, model, prompt, cancel_check)
                if result:
                    return result

        elif provider == "grok":
            api_key = config_manager.get("api_key_grok", "")
            if api_key:
                model = config_manager.get("ai_model_grok", "grok-4.5")
                result = self._clean_with_openai_compatible(text, "https://api.x.ai/v1", api_key, model, prompt, cancel_check)
                if result:
                    return result

        return self._apply_failure_policy(text)

    def _apply_failure_policy(self, text: str) -> str:
        policy = config_manager.get("cleanup_failure_policy", "rule_based")
        if policy not in {"rule_based", "raw", "fail"}:
            policy = "rule_based"
        self.last_processing_info.update({
            "fallback_used": True,
            "fallback_policy": policy,
        })
        logger.warning("Text processing failed; applying configured '%s' policy.", policy)
        if policy == "raw":
            return text
        if policy == "fail":
            raise TextProcessingError("Seçilen metin işleme hizmeti yanıt vermedi.")
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

    def _clean_with_openai_compatible(self, text: str, base_url: str, api_key: str, model_name: str, prompt: str, cancel_check=None) -> str:
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
            resp = run_cancellable(lambda: requests.post(url, headers=headers, json=body, timeout=(5, 45)), cancel_check)
            if resp.status_code == 200:
                result = resp.json()['choices'][0]['message']['content'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info("LLM cleanup completed with model '%s' (%d characters).", model_name, len(result))
                return result
            else:
                failure = failure_from_response("openai_compatible", resp)
                self.last_processing_info["failure"] = failure.as_dict()
                request_id = resp.headers.get("x-request-id") or resp.headers.get("request-id")
                suffix = f" request_id={request_id}" if request_id else ""
                logger.warning("LLM text-processing API returned HTTP %s.%s", resp.status_code, suffix)
        except ProviderRequestCancelled:
            raise TranscriptionCancelled()
        except Exception as e:
            self.last_processing_info["failure"] = failure_from_exception("openai_compatible", e).as_dict()
            _log_provider_failure("OpenAI-compatible", e)
        return None

    def _clean_with_gemini(self, text: str, api_key: str, model_name: str, prompt: str, cancel_check=None) -> str:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": f"{prompt}\n\nGirdi Metni:\n{text}"}]
                }]
            }
            resp = run_cancellable(lambda: requests.post(url, headers=headers, json=payload, timeout=(5, 45)), cancel_check)
            if resp.status_code == 200:
                data = resp.json()
                result = data['candidates'][0]['content']['parts'][0]['text'].strip()
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info("Gemini cleanup completed (%d characters).", len(result))
                return result

            failure = failure_from_response("gemini", resp)
            self.last_processing_info["failure"] = failure.as_dict()
            request_id = resp.headers.get("x-request-id") or resp.headers.get("request-id")
            suffix = f" request_id={request_id}" if request_id else ""
            logger.warning("Gemini text-processing API returned HTTP %s.%s", resp.status_code, suffix)
        except ProviderRequestCancelled:
            raise TranscriptionCancelled()
        except Exception as e:
            self.last_processing_info["failure"] = failure_from_exception("gemini", e).as_dict()
            _log_provider_failure("Gemini", e)
        return None

ai_cleanup_engine = AICleanupEngine()
