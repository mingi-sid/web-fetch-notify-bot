import json
import re
from typing import Any, Dict
from loguru import logger

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMClient:
    """
    Thin wrapper so the digest pipeline can switch between Claude and Gemini via config.

    Config example:
        llm:
          provider: "anthropic"        # or "gemini"
          anthropic:
            api_key: "..."             # optional; falls back to ANTHROPIC_API_KEY
            screening_model: "claude-haiku-4-5"
            digest_model: "claude-sonnet-5-5"
          gemini:
            api_key: "..."             # optional; falls back to GEMINI_API_KEY
            screening_model: "..."
            digest_model: "..."
    """

    def __init__(self, llm_conf: Dict[str, Any]):
        self.provider = llm_conf.get("provider", "anthropic")
        conf = llm_conf.get(self.provider, {})
        self.screening_model = conf["screening_model"]
        self.digest_model = conf["digest_model"]

        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=conf.get("api_key") or None)
        elif self.provider == "gemini":
            from google import genai
            self._client = genai.Client(api_key=conf.get("api_key") or None)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

        logger.info(f"LLM provider: {self.provider} (screening={self.screening_model}, digest={self.digest_model})")

    def complete(self, model: str, system: str, prompt: str, max_tokens: int = 16000,
                 json_mode: bool = False) -> str:
        """Sends a single-turn request and returns the text response."""
        if self.provider == "anthropic":
            return self._complete_anthropic(model, system, prompt, max_tokens)
        return self._complete_gemini(model, system, prompt, max_tokens, json_mode)

    def complete_json(self, model: str, system: str, prompt: str, max_tokens: int = 16000) -> Any:
        """Like complete(), but parses the response as JSON (tolerating ```json fences)."""
        text = self.complete(model, system, prompt, max_tokens, json_mode=True)
        if not text.strip():
            raise ValueError(f"Empty response from {model}")
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if match:
            text = match.group(1)
        return json.loads(text.strip())

    def _complete_anthropic(self, model: str, system: str, prompt: str, max_tokens: int) -> str:
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if model in FALLBACK_MODELS:
            response = self._client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks="default", **kwargs
            )
        else:
            response = self._client.messages.create(**kwargs)

        if response.stop_reason == "refusal":
            raise RuntimeError(f"Model refused the request: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            logger.warning(f"Response from {model} hit max_tokens ({max_tokens}) and may be truncated.")
        return "".join(block.text for block in response.content if block.type == "text")

    def _complete_gemini(self, model: str, system: str, prompt: str, max_tokens: int, json_mode: bool) -> str:
        from google.genai import types
        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else None,
            ),
        )
        if not response.text:
            candidate = response.candidates[0] if response.candidates else None
            logger.warning(f"Gemini returned no text (finish_reason={getattr(candidate, 'finish_reason', None)}, "
                           f"usage={response.usage_metadata})")
        return response.text or ""
