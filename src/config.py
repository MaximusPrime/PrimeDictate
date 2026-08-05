import os
import json
import logging

logger = logging.getLogger("PrimeDictate.Config")

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PrimeDictate")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
HISTORY_PATH = os.path.join(APP_DIR, "history.json")

DEFAULT_CONFIG = {
    "hotkey": "ctrl+alt+d",
    "hotkey_mode": "toggle",  # "toggle" or "hold"
    "stt_backend": "directml",  # "cuda", "directml", "vulkan", "cpu", "cloud"
    "model_size": "base",  # "tiny", "base", "small", "medium", "turbo"
    "language": "tr",  # "tr", "en", "auto"
    "ai_cleanup_enabled": True,
    "ai_cleanup_provider": "rule_based",  # "rule_based", "groq", "openai", "gemini", "grok"
    "api_key_groq": "",
    "api_key_openai": "",
    "api_key_gemini": "",
    "api_key_grok": "",
    "custom_prompt": "Aşağıdaki dikte edilmiş metni Türkçe olarak imla ve dilbilgisi kurallarına uygun hale getir. 'eee', 'yani', 'hmmm', 'şey' gibi duraksama seslerini sil. Yalnızca düzeltilmiş nihai metni yanıt olarak döndür, açıklama veya tırnak ekleme.",
    "audio_device_index": None,
    "auto_paste": True,
    "play_sound": True,
    "start_with_windows": False,
    "overlay_enabled": True,
    "overlay_position": {"x": 100, "y": 100}
}

class ConfigManager:
    def __init__(self):
        os.makedirs(APP_DIR, exist_ok=True)
        self.config = self.load_config()

    def load_config(self) -> dict:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(data)
                    return merged
            except Exception as e:
                logger.error(f"Error loading config, using defaults: {e}")
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("Configuration saved.")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

    def load_history(self) -> list:
        if os.path.exists(HISTORY_PATH):
            try:
                with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_history(self, history: list):
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(history[:100], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving history: {e}")

config_manager = ConfigManager()
