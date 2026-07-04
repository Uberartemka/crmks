import { ref } from 'vue'

export interface ConfirmOptions {
  title: string
  message?: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

const visible = ref(false)
const options = ref<ConfirmOptions>({ title: '' })
let resolver: ((v: boolean) => void) | null = null

export function useConfirm() {
  function confirm(opts: ConfirmOptions): Promise<boolean> {
    // If a confirm is already open, resolve previous as false (cancel)
    // — otherwise first await hangs forever on parallel calls.
    if (visible.value && resolver) {
      resolver(false)
      resolver = null
    }
    options.value = opts
    visible.value = true
    return new Promise<boolean>((resolve) => { resolver = resolve })
  }

  function resolve(value: boolean) {
    visible.value = false
    resolver?.(value)
    resolver = null
  }

  return { visible, options, confirm, resolve }
}
