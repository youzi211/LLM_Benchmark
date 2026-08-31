import { onBeforeUnmount, onMounted } from "vue";
import { useRouter } from "vue-router";

/**
 * 全局键盘快捷键 (Phase 4.1)
 * - g b / g s / g i: 跳转 基础/压测/能力 评测
 * - g o: 跳转 概览
 * - g u: 跳转 一键评测
 * - g d: 跳转 定时任务
 * - ?: 显示帮助
 * - esc: 关闭抽屉/弹窗 (依赖 Element Plus 默认)
 */
export function useShortcuts() {
  const router = useRouter();
  let lastG = 0;

  function isTypingTarget(t: EventTarget | null): boolean {
    const el = t as HTMLElement | null;
    if (!el) return false;
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function onKey(e: KeyboardEvent) {
    if (isTypingTarget(e.target)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const key = e.key.toLowerCase();
    const now = Date.now();

    if (key === "g" && now - lastG > 800) {
      lastG = now;
      return;
    }
    if (lastG > 0 && now - lastG < 800) {
      const map: Record<string, string> = {
        b: "/basic",
        s: "/stress",
        i: "/intelligence",
        o: "/overview",
        u: "/suites",
        d: "/schedules",
      };
      const path = map[key];
      if (path) {
        router.push(path);
        lastG = 0;
        e.preventDefault();
        return;
      }
    }

    if (key === "?") {
      window.dispatchEvent(new CustomEvent("lb:shortcuts-help"));
    }
  }

  onMounted(() => window.addEventListener("keydown", onKey));
  onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
}
