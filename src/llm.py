import json
import re
from typing import Any, Dict
from loguru import logger

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _parse_json(text: str) -> Any:
    """Parses the first JSON value in `text`, ignoring code fences and anything after it."""
    if not text.strip():
        raise ValueError("empty response")
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if match:
        text = match.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON value found")
    value, end = json.JSONDecoder().raw_decode(text, start)
    if text[end:].strip():
        logger.debug(f"Ignored {len(text[end:].strip())} chars after the JSON value.")
    return value


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

        self.usage: Dict[str, Dict[str, int]] = {}
        logger.info(f"LLM provider: {self.provider} (screening={self.screening_model}, digest={self.digest_model})")

    def reset_usage(self):
        self.usage = {}

    def log_usage(self, label: str):
        """Logs token totals per stage accumulated since the last reset_usage()."""
        for stage, u in self.usage.items():
            logger.info(f"Token usage [{label}] {stage}: calls={u['calls']} in={u['in']} "
                        f"out={u['out']} thinking={u['thinking']}")

    def _record(self, stage: str, model: str, tokens_in: int, tokens_out: int, tokens_thinking: int):
        logger.info(f"LLM usage [{stage} | {model}] in={tokens_in} out={tokens_out} thinking={tokens_thinking}")
        u = self.usage.setdefault(stage, {"calls": 0, "in": 0, "out": 0, "thinking": 0})
        u["calls"] += 1
        u["in"] += tokens_in
        u["out"] += tokens_out
        u["thinking"] += tokens_thinking

    def complete(self, model: str, system: str, prompt: str, max_tokens: int = 16000,
                 json_mode: bool = False, thinking: bool = True, stage: str = "other") -> str:
        """
        Sends a single-turn request and returns the text response.
        `thinking=False` turns Gemini's thinking down to the minimum for simple classification
        calls. Claude Haiku 4.5 (the default screening model) doesn't think unless asked, so it's
        ignored for Anthropic.
        """
        if self.provider == "anthropic":
            return self._complete_anthropic(model, system, prompt, max_tokens, stage)
        return self._complete_gemini(model, system, prompt, max_tokens, json_mode, thinking, stage)

    def complete_json(self, model: str, system: str, prompt: str, max_tokens: int = 16000,
                      thinking: bool = True, attempts: int = 2, stage: str = "other") -> Any:
        """
        Like complete(), but parses the response as JSON. Tolerates ```json fences and trailing
        text after the first JSON value; retries once if the response still can't be parsed.
        """
        for attempt in range(1, attempts + 1):
            text = self.complete(model, system, prompt, max_tokens, json_mode=True, thinking=thinking, stage=stage)
            try:
                return _parse_json(text)
            except ValueError as e:
                logger.warning(f"Unparseable JSON from {model} (attempt {attempt}/{attempts}): {e}\n"
                               f"--- raw response (first 2000 chars) ---\n{text[:2000]}")
                if attempt == attempts:
                    raise

    def _complete_anthropic(self, model: str, system: str, prompt: str, max_tokens: int, stage: str) -> str:
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

        self._record(stage, model, response.usage.input_tokens, response.usage.output_tokens, 0)
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Model refused the request: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            logger.warning(f"Response from {model} hit max_tokens ({max_tokens}) and may be truncated.")
        return "".join(block.text for block in response.content if block.type == "text")

    def _complete_gemini(self, model: str, system: str, prompt: str, max_tokens: int,
                         json_mode: bool, thinking: bool, stage: str) -> str:
        from google.genai import types, errors

        def generate(thinking_config):
            return self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json" if json_mode else None,
                    thinking_config=thinking_config,
                ),
            )

        if thinking:
            response = generate(None)
        else:
            # Gemini 3.5+ only accepts thinking_level; older models only accept thinking_budget.
            try:
                response = generate(types.ThinkingConfig(thinking_level="MINIMAL"))
            except errors.ClientError as e:
                logger.debug(f"thinking_level rejected by {model} ({e}); retrying with thinking_budget=0")
                response = generate(types.ThinkingConfig(thinking_budget=0))

        usage = response.usage_metadata
        if usage:
            self._record(stage, model, usage.prompt_token_count or 0, usage.candidates_token_count or 0,
                         usage.thoughts_token_count or 0)
        if not response.text:
            candidate = response.candidates[0] if response.candidates else None
            logger.warning(f"Gemini returned no text (finish_reason={getattr(candidate, 'finish_reason', None)}, "
                           f"usage={response.usage_metadata})")
        return response.text or ""
