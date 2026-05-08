# LLM Providers

RentWise is designed to be **LLM-agnostic**. Users choose their own provider — free, paid, hosted, or local — without RentWise locking them into any specific vendor.

## Architecture

We use **[LiteLLM](https://docs.litellm.ai/)** as the abstraction layer. LiteLLM provides a single OpenAI-compatible interface to 100+ providers including OpenRouter, Anthropic, OpenAI, Google, Ollama, and more.

```
┌─────────────────┐
│ RentWise        │
│ query_translator│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LiteLLM         │  ← single unified interface
└────────┬────────┘
         │
   ┌─────┼─────┬──────┬───────┬──────┐
   ▼     ▼     ▼      ▼       ▼      ▼
OpenRouter Anthropic OpenAI Google Ollama  ...
(free +    (Claude)  (GPT)  (Gemini)(local)
 paid)
```

## Why LiteLLM + OpenRouter (not just one)

| Concern | Solution |
|---|---|
| Want free models for development | OpenRouter has 29+ free models (Llama 3.3, Qwen, Mistral, Gemma, etc.) |
| Want best quality for production | Switch to Claude/GPT-4 with one config change |
| Want privacy / no third-party | Use Ollama for local inference |
| Want to swap providers later | LiteLLM uses OpenAI-compatible format — no rewrites needed |
| Want to support Korean well | Qwen3 Next 80B (free) handles Korean excellently; Claude/GPT for highest quality |

## Configuration Priority

Settings are read in this order (last wins):

1. **`.env` file** — defaults, set by developer/sysadmin
2. **App Settings UI** — user can override at runtime
3. **First-run wizard** — if no config exists, user is walked through setup

## First-Run Setup Wizard

When a user opens RentWise for the first time without an LLM configured, the app shows a wizard:

```
┌─────────────────────────────────────────────────┐
│ Welcome to RentWise! Pick an AI model:         │
│                                                 │
│ ⦿ Free (recommended for trying it out)         │
│   - Qwen3 Next 80B (great at Korean) [DEFAULT]  │
│   - Llama 3.3 70B                               │
│   - Gemma 4 26B                                 │
│   → Uses OpenRouter free tier (signup required) │
│                                                 │
│ ⦾ Bring my own API key                          │
│   - Anthropic Claude                            │
│   - OpenAI GPT                                  │
│   - Google Gemini                               │
│   - OpenRouter (paid tier)                      │
│   - Ollama (local, no API key needed)           │
│                                                 │
│ [ Continue → ]                                  │
└─────────────────────────────────────────────────┘
```

If they pick a free OpenRouter model:
- Wizard guides them to sign up at openrouter.ai (no credit card)
- They paste their API key
- Done

If they bring their own:
- Show provider-specific instructions and example model strings
- Validate the key with a tiny test call before saving

## Environment Variables

```bash
# .env

# LLM provider configuration
RENTWISE_LLM_MODEL=openrouter/qwen/qwen3-next-80b-a3b-instruct:free
OPENROUTER_API_KEY=sk-or-v1-...

# OR — bring your own
# RENTWISE_LLM_MODEL=anthropic/claude-sonnet-4
# ANTHROPIC_API_KEY=sk-ant-...

# OR — local (no API key needed)
# RENTWISE_LLM_MODEL=ollama/llama3
# OLLAMA_BASE_URL=http://localhost:11434

# Optional: secondary fallback model (used if primary fails)
RENTWISE_LLM_FALLBACK_MODEL=openrouter/meta-llama/llama-3.3-70b-instruct:free
```

## Settings UI Schema

The app settings store this in SQLite (encrypted at rest):

```python
class LLMSettings(BaseModel):
    primary_model: str            # e.g. "openrouter/qwen/qwen3-next-80b-a3b-instruct:free"
    primary_api_key: SecretStr    # encrypted
    fallback_model: str | None
    fallback_api_key: SecretStr | None
    custom_base_url: str | None   # for self-hosted/Ollama
    max_retries: int = 2
    timeout_seconds: int = 30
```

UI in the app:
- **Provider** dropdown: OpenRouter / Anthropic / OpenAI / Google / Ollama / Custom
- **Model** dropdown (filtered by provider, with free models tagged 🆓)
- **API Key** input (masked, with "test connection" button)
- **Fallback** section (collapsed by default)

## Recommended Free Models for Korean + English

Tested for RentWise's specific use case (NL → structured rental query):

| Model | Korean Quality | English Quality | Tool Use | Notes |
|---|---|---|---|---|
| `qwen/qwen3-next-80b-a3b-instruct:free` | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Solid | **Default recommendation** |
| `meta-llama/llama-3.3-70b-instruct:free` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Solid | Strong fallback |
| `google/gemma-4-26b-a4b-it:free` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⚠️ Limited | Good for explanations, weaker tool use |
| `deepseek/deepseek-r1:free` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⚠️ No native | Reasoning model — slower but accurate |

## Recommended Paid Models (for production / hosted use)

| Model | Quality | Cost (approx) | Why |
|---|---|---|---|
| `anthropic/claude-sonnet-4` | ⭐⭐⭐⭐⭐ | ~$0.003 / query | Best Korean + tool use |
| `openai/gpt-4o-mini` | ⭐⭐⭐⭐ | ~$0.0005 / query | Cheapest decent option |
| `google/gemini-2.5-flash` | ⭐⭐⭐⭐ | ~$0.0008 / query | Fast, multilingual |

A "query" here = one user search input → one structured-query JSON output (~500 input + 200 output tokens).

## Free Tier Rate Limits

OpenRouter's free tier: **20 requests/minute, 200 requests/day** per user account.

For RentWise:
- 1 user query = 1 LLM call
- 200 searches/day = plenty for personal use
- If a user runs many saved-search auto-refreshes, they may hit the limit
- The app warns when approaching the limit and suggests upgrading or switching providers

## Why Not Just OpenRouter?

OpenRouter is great, but:
- It's SaaS-only — your prompts always transit their servers
- It adds 5% on top of base provider prices for paid models
- You're locked in to their service if you don't abstract

LiteLLM avoids this lock-in: today you use OpenRouter through LiteLLM; tomorrow if OpenRouter shuts down or raises prices, you switch the model string to `anthropic/...` and nothing else changes.

## Why Not Just LiteLLM (Without OpenRouter)?

LiteLLM is just a library — it doesn't give you free models. Without OpenRouter (or another aggregator), users would need to sign up directly with each provider, manage multiple keys, and handle billing separately. OpenRouter solves the "free tier + unified billing" problem.

## Implementation Notes

```python
# apps/api/llm/client.py
import litellm
from litellm import acompletion

class LLMClient:
    def __init__(self, settings: LLMSettings):
        self.settings = settings
        # LiteLLM picks up keys from env vars automatically,
        # but we can override per-call too
        litellm.api_key = settings.primary_api_key.get_secret_value()

    async def translate_query(self, user_input: str, lang: str = "auto") -> NormalizedQuery:
        try:
            response = await acompletion(
                model=self.settings.primary_model,
                messages=[
                    {"role": "system", "content": self._system_prompt(lang)},
                    {"role": "user", "content": user_input},
                ],
                tools=[QUERY_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "submit_query"},
                timeout=self.settings.timeout_seconds,
            )
            return self._parse_tool_call(response)
        except Exception as e:
            if self.settings.fallback_model:
                return await self._retry_with_fallback(user_input, lang)
            raise
```

LiteLLM handles all the provider-specific quirks (different tool-use formats for different providers, response parsing, etc.) for us.
