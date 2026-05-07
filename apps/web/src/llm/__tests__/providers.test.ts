import { PROVIDERS } from "@/src/llm/providers";

describe("PROVIDERS catalog", () => {
  it("includes 5 providers (openrouter, anthropic, openai, google, ollama)", () => {
    const ids = PROVIDERS.map((p) => p.id);
    expect(ids.sort()).toEqual(["anthropic", "google", "ollama", "openai", "openrouter"]);
  });

  it("only ollama has needsKey=false", () => {
    expect(PROVIDERS.filter((p) => !p.needsKey).map((p) => p.id)).toEqual(["ollama"]);
  });

  it("every provider has at least one model", () => {
    for (const p of PROVIDERS) {
      expect(p.models.length).toBeGreaterThan(0);
    }
  });
});
