import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { SaveSearchForm } from "@/src/components/SaveSearchForm";
import type { ApiClient } from "@/src/api/client";
import { emptyQuery } from "@/src/api/types";

function makeClient(overrides: Partial<ApiClient>): ApiClient {
  const base: ApiClient = {
    search: jest.fn(),
    searchStream: jest.fn(),
    translateQuery: jest.fn(),
    getSettings: jest.fn(),
    putSettings: jest.fn(),
    testConnection: jest.fn(),
    saveSearch: jest.fn(),
    listSavedSearches: jest.fn(),
    deleteSavedSearch: jest.fn(),
    getWebPushPublicKey: jest.fn(),
    subscribeWebPush: jest.fn(),
    unsubscribeWebPush: jest.fn(),
  };
  return { ...base, ...overrides };
}

describe("SaveSearchForm", () => {
  it("submits the supplied query with the trimmed label", async () => {
    const saveSearch = jest.fn().mockResolvedValue({});
    const client = makeClient({ saveSearch });
    const onSaved = jest.fn();
    const { getByLabelText } = render(
      <SaveSearchForm
        client={client}
        query={emptyQuery()}
        onSaved={onSaved}
        onCancel={jest.fn()}
      />,
    );

    fireEvent.changeText(getByLabelText("Saved search label"), "  Kits 2br  ");
    await act(async () => {
      fireEvent.press(getByLabelText("Confirm save"));
    });

    expect(saveSearch).toHaveBeenCalledTimes(1);
    expect(saveSearch.mock.calls[0]![0]).toMatchObject({
      label: "Kits 2br",
      alert_enabled: false,
      alert_email: null,
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it("only sends alert_email when the alert toggle is on", async () => {
    const saveSearch = jest.fn().mockResolvedValue({});
    const client = makeClient({ saveSearch });
    const { getByLabelText } = render(
      <SaveSearchForm
        client={client}
        query={emptyQuery()}
        onSaved={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    fireEvent(getByLabelText("Email me when new listings match"), "valueChange", true);
    fireEvent.changeText(getByLabelText("Alert email"), "me@example.com");

    await act(async () => {
      fireEvent.press(getByLabelText("Confirm save"));
    });

    expect(saveSearch.mock.calls[0]![0]).toMatchObject({
      alert_enabled: true,
      alert_email: "me@example.com",
    });
  });

  it("renders an error message when the API rejects", async () => {
    const client = makeClient({
      saveSearch: jest.fn().mockRejectedValue(new Error("HTTP 404")),
    });
    const { getByLabelText, getByText } = render(
      <SaveSearchForm
        client={client}
        query={emptyQuery()}
        onSaved={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    await act(async () => {
      fireEvent.press(getByLabelText("Confirm save"));
    });

    expect(getByText(/Couldn.+t save: HTTP 404/)).toBeTruthy();
  });

  it("Cancel calls onCancel without hitting the API", () => {
    const saveSearch = jest.fn();
    const onCancel = jest.fn();
    const client = makeClient({ saveSearch });
    const { getByLabelText } = render(
      <SaveSearchForm
        client={client}
        query={emptyQuery()}
        onSaved={jest.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.press(getByLabelText("Cancel save"));
    expect(onCancel).toHaveBeenCalled();
    expect(saveSearch).not.toHaveBeenCalled();
  });
});
