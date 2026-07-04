import { toast as vToast } from 'vue-toastification'

// Re-export with typed API. Config is registered in main.ts.
export const toast = {
  success: (msg: string) => vToast.success(msg),
  error: (msg: string) => vToast.error(msg),
  info: (msg: string) => vToast.info(msg),
  warning: (msg: string) => vToast.warning(msg),
}
