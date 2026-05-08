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
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic (Claude)",
    needsKey: true,
    models: [{ id: "anthropic/claude-sonnet-4", label: "Claude Sonnet 4" }],
  },
  {
    id: "openai",
    label: "OpenAI",
    needsKey: true,
    models: [
      { id: "openai/gpt-4o-mini", label: "GPT-4o mini" },
      { id: "openai/gpt-4o", label: "GPT-4o" },
    ],
  },
  {
    id: "google",
    label: "Google Gemini",
    needsKey: true,
    models: [{ id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" }],
  },
  {
    id: "ollama",
    label: "Ollama (local, no key)",
    needsKey: false,
    models: [
      { id: "ollama/llama3", label: "Llama 3 (local)" },
      { id: "ollama/qwen2", label: "Qwen 2 (local)" },
    ],
  },
];
