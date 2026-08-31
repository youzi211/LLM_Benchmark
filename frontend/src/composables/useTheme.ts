import { ref, watch, onMounted, readonly } from "vue";

export type ThemeMode = "light" | "dark" | "auto";

const STORAGE_KEY = "lb-theme";
const DEFAULT_MODE: ThemeMode = "light";

const mode = ref<ThemeMode>(DEFAULT_MODE);
const resolved = ref<"light" | "dark">("light");

function readStoredMode(): ThemeMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "auto") return v;
  } catch {
    // localStorage 可能被阻止(隐私模式 / iframe). 回落到默认.
  }
  return DEFAULT_MODE;
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(next: "light" | "dark") {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-theme", next);
  root.style.colorScheme = next;
  resolved.value = next;
}

function commitMode(next: ThemeMode) {
  mode.value = next;
  const target: "light" | "dark" = next === "auto" ? (systemPrefersDark() ? "dark" : "light") : next;
  applyTheme(target);
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // 忽略持久化失败.
  }
}

let mediaQuery: MediaQueryList | null = null;
let mediaListener: ((e: MediaQueryListEvent) => void) | null = null;

function bindSystemListener() {
  if (typeof window === "undefined" || !window.matchMedia) return;
  if (mediaQuery) return;
  mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  mediaListener = () => {
    if (mode.value === "auto") applyTheme(mediaQuery?.matches ? "dark" : "light");
  };
  if (mediaListener && mediaQuery) {
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener("change", mediaListener);
    } else if ("addListener" in mediaQuery) {
      (mediaQuery as unknown as { addListener: (cb: (e: MediaQueryListEvent) => void) => void }).addListener(mediaListener);
    }
  }
}

export function useTheme() {
  onMounted(() => {
    mode.value = readStoredMode();
    bindSystemListener();
    commitMode(mode.value);
  });

  watch(mode, (next) => {
    commitMode(next);
  });

  return {
    mode: readonly(mode),
    resolved: readonly(resolved),
    setMode: (next: ThemeMode) => {
      mode.value = next;
    },
    toggle: () => {
      const cur = mode.value;
      const next: ThemeMode = cur === "light" ? "dark" : cur === "dark" ? "auto" : "light";
      mode.value = next;
    },
  };
}

export function initThemeEarly() {
  // 在 App 挂载前尽早应用主题,避免白底闪烁.
  if (typeof window === "undefined") return;
  const stored = readStoredMode();
  mode.value = stored;
  const target: "light" | "dark" = stored === "auto" ? (systemPrefersDark() ? "dark" : "light") : stored;
  applyTheme(target);
}
