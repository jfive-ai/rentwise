import React from "react";
import { Pressable, Text } from "react-native";
import { render, fireEvent, renderHook, act } from "@testing-library/react-native";
import { QueryProvider, useQuery } from "@/src/state/QueryProvider";

function Probe() {
  const { query, set, reset, toggleNeighborhood, toggleKeyword } = useQuery();
  return (
    <>
      <Text testID="bedrooms">{String(query.bedrooms_min ?? "")}</Text>
      <Text testID="hoods">{query.neighborhoods.join(",")}</Text>
      <Text testID="kw">{query.free_text_keywords.join(",")}</Text>
      <Pressable testID="set-bed" onPress={() => set({ bedrooms_min: 2 })}>
        <Text>set</Text>
      </Pressable>
      <Pressable testID="add-kits" onPress={() => toggleNeighborhood("Kitsilano")}>
        <Text>kits</Text>
      </Pressable>
      <Pressable testID="reset" onPress={reset}>
        <Text>reset</Text>
      </Pressable>
      <Pressable testID="add-balcony" onPress={() => toggleKeyword("balcony")}>
        <Text>balcony</Text>
      </Pressable>
      <Pressable testID="add-parking-padded" onPress={() => toggleKeyword("  parking  ")}>
        <Text>parking</Text>
      </Pressable>
      <Pressable testID="add-whitespace-only" onPress={() => toggleKeyword("   ")}>
        <Text>noop</Text>
      </Pressable>
    </>
  );
}

describe("QueryProvider", () => {
  it("starts with the empty query", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    expect(getByTestId("bedrooms").props.children).toBe("");
    expect(getByTestId("hoods").props.children).toBe("");
  });

  it("merges fields via set()", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    fireEvent.press(getByTestId("set-bed"));
    expect(getByTestId("bedrooms").props.children).toBe("2");
  });

  it("toggleNeighborhood adds then removes", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    fireEvent.press(getByTestId("add-kits"));
    expect(getByTestId("hoods").props.children).toBe("Kitsilano");
    fireEvent.press(getByTestId("add-kits"));
    expect(getByTestId("hoods").props.children).toBe("");
  });

  it("reset() returns to empty", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );
    fireEvent.press(getByTestId("set-bed"));
    fireEvent.press(getByTestId("add-kits"));
    fireEvent.press(getByTestId("reset"));
    expect(getByTestId("bedrooms").props.children).toBe("");
    expect(getByTestId("hoods").props.children).toBe("");
  });

  it("toggleKeyword adds, removes, trims, and ignores whitespace-only input", () => {
    const { getByTestId } = render(
      <QueryProvider>
        <Probe />
      </QueryProvider>
    );

    // starts empty
    expect(getByTestId("kw").props.children).toBe("");

    // adds "balcony"
    fireEvent.press(getByTestId("add-balcony"));
    expect(getByTestId("kw").props.children).toBe("balcony");

    // removes "balcony" on second press
    fireEvent.press(getByTestId("add-balcony"));
    expect(getByTestId("kw").props.children).toBe("");

    // trimming: "  parking  " → stored as "parking"
    fireEvent.press(getByTestId("add-parking-padded"));
    expect(getByTestId("kw").props.children).toBe("parking");

    // whitespace-only input is a no-op — "parking" remains
    fireEvent.press(getByTestId("add-whitespace-only"));
    expect(getByTestId("kw").props.children).toBe("parking");
  });

  it("useQuery throws when called outside provider", () => {
    const Bad = () => {
      useQuery();
      return null;
    };
    expect(() => render(<Bad />)).toThrow(/QueryProvider/);
  });
});

describe("mode + nlText", () => {
  it("defaults to filters mode and empty nlText", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    expect(result.current.mode).toBe("filters");
    expect(result.current.nlText).toBe("");
  });

  it("setMode updates mode", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    act(() => result.current.setMode("nl"));
    expect(result.current.mode).toBe("nl");
  });

  it("filters→nl clears nlText (no fake sentence)", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    act(() => result.current.setMode("nl"));
    act(() => result.current.setNlText("키츠 2베드"));
    act(() => result.current.setMode("filters"));
    act(() => result.current.setMode("nl"));
    // re-entered NL mode after filter mode → nlText cleared per spec
    expect(result.current.nlText).toBe("");
  });

  it("nl→filters preserves structured query", () => {
    const { result } = renderHook(() => useQuery(), { wrapper: QueryProvider });
    act(() => result.current.setMode("nl"));
    act(() => result.current.set({ bedrooms_min: 2, neighborhoods: ["Kitsilano"] }));
    act(() => result.current.setMode("filters"));
    expect(result.current.query.bedrooms_min).toBe(2);
    expect(result.current.query.neighborhoods).toEqual(["Kitsilano"]);
  });
});
