export interface ModelOption {
  id: string; // litellm model string, e.g. "openrouter/qwen/qwen3-next-80b-a3b-instruct:free"
  label: string; // user-facing label
  free?: boolean;
}

export interface ProviderOption {
  id: "openrouter" | "anthropic" | "openai" | "google" | "ollama";
  label: string;
  needsKey: boolean;
  models: ModelOption[];
}

// Sentinel id for "let me type my own model string". Curated lists drift —
// OpenRouter rotates free models, OpenAI ships new variants — so every
// provider exposes this escape hatch. The wizard / settings screens reveal
// a TextInput when this is selected and use that value as primary_model.
export const CUSTOM_MODEL_ID = "__custom__";
export const CUSTOM_MODEL_LABEL = "Custom model ID…";
const customOption: ModelOption = { id: CUSTOM_MODEL_ID, label: CUSTOM_MODEL_LABEL };

export const PROVIDERS: ProviderOption[] = [
  {
    id: "openrouter",
    label: "OpenRouter (free + paid)",
    needsKey: true,
    models: [
      {
        id: "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
        label: "Qwen3 Next 80B (free, recommended for KO)",
        free: true,
      },
      {
        id: "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        label: "Llama 3.3 70B (free)",
        free: true,
      },
      {
        id: "openrouter/google/gemma-4-26b-a4b-it:free",
        label: "Gemma 4 26B (free)",
        free: true,
      },
      { id: "openrouter/anthropic/claude-sonnet-4", label: "Claude Sonnet 4 (paid)" },
      { id: "openrouter/openai/gpt-4o-mini", label: "GPT-4o mini (paid)" },
      customOption,
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic (Claude)",
    needsKey: true,
    models: [
      { id: "anthropic/claude-sonnet-4", label: "Claude Sonnet 4" },
      customOption,
    ],
  },
  {
    id: "openai",
    label: "OpenAI",
    needsKey: true,
    models: [
      { id: "openai/gpt-5.5", label: "GPT-5.5 (flagship)" },
      { id: "openai/gpt-5.4-mini", label: "GPT-5.4 mini" },
      { id: "openai/gpt-5.4-nano", label: "GPT-5.4 nano" },
      { id: "openai/gpt-4o", label: "GPT-4o" },
      { id: "openai/gpt-4o-mini", label: "GPT-4o mini" },
      customOption,
    ],
  },
  {
    id: "google",
    label: "Google Gemini",
    needsKey: true,
    models: [
      { id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      customOption,
    ],
  },
  {
    id: "ollama",
    label: "Ollama (local, no key)",
    needsKey: false,
    models: [
      { id: "ollama/llama3", label: "Llama 3 (local)" },
      { id: "ollama/qwen2", label: "Qwen 2 (local)" },
      customOption,
    ],
  },
];

// When the saved primary_model isn't in any curated list, infer the provider
// from the LiteLLM prefix (e.g. "openai/foo" → openai, "ollama/whatever" → ollama).
// Falls back to OpenRouter for unprefixed strings.
export function inferProviderFromModelId(modelId: string): ProviderOption {
  const prefix = modelId.split("/", 1)[0] as ProviderOption["id"];
  return PROVIDERS.find((p) => p.id === prefix) ?? PROVIDERS[0];
}
