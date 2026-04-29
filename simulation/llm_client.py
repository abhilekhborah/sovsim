import logging
import os
import re
import time

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    # Configure via environment variables:
    # OPENAI_API_KEY      - Your API key (required)
    # OPENAI_BASE_URL     - API base URL (default: https://api.openai.com/v1)
    # OPENAI_API_VERSION  - API version for Azure (optional)
    # For Azure OpenAI, use:
    # AZURE_OPENAI_ENDPOINT - Azure endpoint URL
    # AZURE_OPENAI_API_KEY  - Azure API key

    def __init__(self, model: str, temperature: float | None = 0.0,
                 max_retries: int = 3, retry_delay: float = 2.0):
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Set it to your OpenAI API key, or configure a compatible endpoint "
                "via OPENAI_BASE_URL."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    # ------------------------------------------------------------------ #
    #  Core query                                                         #
    # ------------------------------------------------------------------ #
    def query(self, system_prompt: str, user_prompt: str) -> str:
        # Send system + user messages and return the assistant reply.
        max_attempts = 8
        for attempt in range(1, max_attempts + 1):
            try:
                kwargs = dict(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                if self.temperature is not None:
                    kwargs["temperature"] = self.temperature
                response = self.client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content or ""
                logger.debug("LLM [%s] response: %s", self.model, text.strip())
                return text.strip()
            except Exception as exc:
                is_rate_limit = "429" in str(exc)
                if is_rate_limit:
                    wait = 65
                    print(f"        [RATE-LIMITED] attempt {attempt}/{max_attempts}, waiting {wait}s ...")
                    time.sleep(wait)
                elif attempt < max_attempts:
                    wait = self.retry_delay * attempt
                    logger.warning(
                        "LLM call attempt %d/%d failed: %s — retrying in %.0fs",
                        attempt, max_attempts, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    raise

    # ------------------------------------------------------------------ #
    #  Response parsing                                                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def parse_int(response: str, low: int, high: int) -> int:
        # Extract the first integer from response and clamp to [low, high].
        match = re.search(r"\d+", response)
        if match:
            return max(low, min(high, int(match.group())))
        logger.warning("Could not parse integer from: %r → defaulting to 0", response)
        return 0

    def parse_response(self, response: str, low: int, high: int) -> tuple:
        # Extract reasoning and integer from structured REASONING/ANSWER response.
        # Returns (reasoning: str, value: int).
        reasoning = ""
        r_match = re.search(r'REASONING:\s*(.*?)(?=\nANSWER:|$)', response, re.DOTALL)
        if r_match:
            reasoning = r_match.group(1).strip()

        a_match = re.search(r'ANSWER:\s*\$?(\d+)', response)
        if a_match:
            val = max(low, min(high, int(a_match.group(1))))
            return reasoning, val

        logger.warning("No ANSWER tag found, falling back to parse_int: %r", response[:100])
        val = self.parse_int(response, low, high)
        return reasoning or response.strip(), val
