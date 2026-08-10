from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from src.engine.provider_transport import failure_from_exception, failure_from_response


@dataclass(frozen=True)
class ProviderCatalogResult:
    ok: bool
    error_code: str = ""
    stt_models: tuple[str, ...] = field(default_factory=tuple)
    text_models: tuple[str, ...] = field(default_factory=tuple)
    failure: object = None


class ProviderCatalog:
    ENDPOINTS = {
        "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
        "groq": "https://api.groq.com/openai/v1/models",
        "openai": "https://api.openai.com/v1/models",
        "grok": "https://api.x.ai/v1/models",
    }

    def __init__(self, session=None):
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(
                total=2,
                connect=2,
                read=1,
                backoff_factor=0.35,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                respect_retry_after_header=True,
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def discover(self, provider: str, api_key: str) -> ProviderCatalogResult:
        if not api_key:
            return ProviderCatalogResult(False, "missing_key")
        url = self.ENDPOINTS.get(provider)
        if not url:
            return ProviderCatalogResult(False, "unsupported_provider")
        headers = {"Accept": "application/json"}
        if provider == "gemini":
            headers["x-goog-api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = self.session.get(url, headers=headers, timeout=(5, 15))
        except requests.RequestException as error:
            failure = failure_from_exception(provider, error)
            return ProviderCatalogResult(False, failure.code, failure=failure)
        if response.status_code != 200:
            failure = failure_from_response(provider, response)
            return ProviderCatalogResult(False, f"http_{response.status_code}", failure=failure)
        try:
            models = self._model_ids(provider, response.json())
        except (TypeError, ValueError, KeyError):
            return ProviderCatalogResult(False, "invalid_response")
        if not models:
            return ProviderCatalogResult(False, "no_models")
        stt_models = tuple(model for model in models if self._is_stt_model(provider, model))
        if provider == "openai":
            stt_models = tuple(sorted(stt_models, key=self._openai_stt_sort_key))
        text_models = tuple(model for model in models if model not in stt_models)
        if provider == "gemini":
            stt_models = text_models = tuple(models)
        return ProviderCatalogResult(True, stt_models=stt_models, text_models=text_models)

    @staticmethod
    def _model_ids(provider: str, payload: dict) -> tuple[str, ...]:
        items = payload.get("models" if provider == "gemini" else "data", [])
        key = "name" if provider == "gemini" else "id"
        ids = [item.get(key, "") for item in items]
        if provider == "gemini":
            ids = [model.removeprefix("models/") for model in ids if isinstance(model, str)]
        # Do not truncate before capability filtering. Large provider catalogs
        # can otherwise hide transcription models that sort near the end.
        return tuple(sorted({model for model in ids if isinstance(model, str) and model}))

    @staticmethod
    def _is_stt_model(provider: str, model: str) -> bool:
        model = model.casefold()
        if provider == "groq":
            return "whisper" in model
        if provider == "openai":
            return (
                model == "whisper-1"
                or model.startswith("whisper-1-")
                or model == "gpt-transcribe"
                or model.startswith("gpt-transcribe-")
                or model == "gpt-4o-transcribe"
                or model.startswith("gpt-4o-transcribe-")
                or model == "gpt-4o-mini-transcribe"
                or model.startswith("gpt-4o-mini-transcribe-")
            )
        return False

    @staticmethod
    def _openai_stt_sort_key(model: str):
        recommended = {
            "gpt-transcribe": 0,
            "gpt-4o-transcribe": 1,
            "gpt-4o-mini-transcribe": 2,
            "whisper-1": 3,
        }
        return recommended.get(model, 10), model


provider_catalog = ProviderCatalog()
