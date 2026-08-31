import { ElMessage, ElNotification, type MessageOptions, type NotificationOptions } from "element-plus";

/**
 * 统一 toast / 通知入口.
 * 错误不再以红条横在 tab 顶部, 改用 toast(轻量) 或 Notification(重要).
 * 重要错误 (服务不可用) 进 Notification; 普通错误进 toast.
 */

let _lastErrorAt = 0;
const DEDUPE_MS = 1500;

export function useToast() {
  return {
    info: (msg: string, opts?: MessageOptions) => {
      ElMessage({ type: "info", message: msg, duration: 3000, ...opts });
    },
    success: (msg: string, opts?: MessageOptions) => {
      ElMessage({ type: "success", message: msg, duration: 3000, ...opts });
    },
    warning: (msg: string, opts?: MessageOptions) => {
      ElMessage({ type: "warning", message: msg, duration: 4000, ...opts });
    },
    error: (msg: string, opts?: MessageOptions) => {
      const now = Date.now();
      if (now - _lastErrorAt < DEDUPE_MS) return;
      _lastErrorAt = now;
      ElMessage({ type: "error", message: msg, duration: 5000, ...opts });
    },
    critical: (title: string, msg: string, opts?: NotificationOptions) => {
      ElNotification({
        type: "error",
        title,
        message: msg,
        duration: 0, // 不自动关闭, 用户必须手动关
        position: "top-right",
        ...opts,
      });
    },
  };
}
