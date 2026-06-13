const memory = new Map<string, string>();

function browserStorage(): Storage | null {
  try {
    const storage = window.localStorage;
    return typeof storage?.getItem === "function" ? storage : null;
  } catch {
    return null;
  }
}

export const preferenceStorage = {
  get(key: string) {
    return browserStorage()?.getItem(key) ?? memory.get(key) ?? null;
  },
  set(key: string, value: string) {
    const storage = browserStorage();
    if (storage) storage.setItem(key, value);
    else memory.set(key, value);
  },
  clear() {
    const storage = browserStorage();
    if (storage) storage.clear();
    memory.clear();
  },
};
