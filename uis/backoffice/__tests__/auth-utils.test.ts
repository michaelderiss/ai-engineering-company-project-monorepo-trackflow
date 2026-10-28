/**
 * FE-019 — Jest tests for uis/backoffice/lib/auth.ts token storage helpers.
 *
 * Each helper gets a happy path (storage available) and a failure mode
 * (storage unavailable or blocked). No HTTP is involved; these test the pure
 * token persistence + authentication-flag logic.
 */

import {
  clearToken,
  getToken,
  isAuthenticated,
  setToken,
} from "../lib/auth";

const TOKEN_KEY = "trackflow_access_token";

/** Storage that keeps jest.fn mock methods so tests can stub/assert. */
type MockedStorage = Storage & {
  getItem: jest.Mock;
  setItem: jest.Mock;
  removeItem: jest.Mock;
  clear: jest.Mock;
  key: jest.Mock;
};

/** Minimal in-memory localStorage substitute. */
function installLocalStorage(): MockedStorage {
  const store = new Map<string, string>();
  const storage = {
    getItem: jest.fn((key: string) => (store.has(key) ? store.get(key) : null)),
    setItem: jest.fn((key: string, value: string) => {
      store.set(key, value);
    }),
    removeItem: jest.fn((key: string) => {
      store.delete(key);
    }),
    clear: jest.fn(() => store.clear()),
    key: jest.fn((index: number) => Array.from(store.keys())[index] ?? null),
    get length() {
      return store.size;
    },
  } as unknown as MockedStorage;
  (globalThis as Record<string, unknown>).localStorage = storage;
  return storage;
}

afterEach(() => {
  delete (globalThis as Record<string, unknown>).localStorage;
  jest.restoreAllMocks();
});

describe("setToken / getToken / clearToken", () => {
  it("round-trips a token through localStorage (happy path)", () => {
    const storage = installLocalStorage();
    setToken("abc.def.ghi");
    expect(storage.setItem).toHaveBeenCalledWith(TOKEN_KEY, "abc.def.ghi");
    expect(getToken()).toBe("abc.def.ghi");
    clearToken();
    expect(getToken()).toBeNull();
    expect(storage.removeItem).toHaveBeenCalledWith(TOKEN_KEY);
  });

  it("returns null when localStorage is unavailable (failure mode)", () => {
    // No localStorage installed: getToken must not throw.
    expect(getToken()).toBeNull();
    // clearToken must be a safe no-op.
    expect(() => clearToken()).not.toThrow();
  });

  it("throws a friendly error when storage is blocked (failure mode)", () => {
    const storage = installLocalStorage();
    storage.setItem.mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => setToken("x.y.z")).toThrow(
      "Your browser could not save the session"
    );
  });
});

describe("isAuthenticated", () => {
  it("is true when a token is stored (happy path)", () => {
    installLocalStorage();
    setToken("signed-token");
    expect(isAuthenticated()).toBe(true);
  });

  it("is false when storage is unavailable (failure mode)", () => {
    expect(isAuthenticated()).toBe(false);
  });
});