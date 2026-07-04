import { useToast } from 'vue-toastification'

// vue-toastification@2.0.0-rc.5 exposes `useToast` (Composition API), not a
// bare `toast` export. Calling useToast() outside a component falls back to
// the global event bus, which gives a working toast interface app-wide.
// We wrap it once into a simple { success/error/info/warning(msg) } API so
// call sites don't need to be inside setup().
const vToast = useToast()

export const toast = {
  success: (msg: string) => vToast.success(msg),
  error: (msg: string) => vToast.error(msg),
  info: (msg: string) => vToast.info(msg),
  warning: (msg: string) => vToast.warning(msg),
}
