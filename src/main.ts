import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import { POSITION } from 'vue-toastification'
import 'vue-toastification/dist/index.css'
import { register as registerChat } from 'vue-advanced-chat'
// Note: vue-advanced-chat v2 ships CSS inside the JS bundle (no separate .css
// file in dist/), so no explicit stylesheet import is needed.
import { router } from './router'
import App from './App.vue'
import './assets/main.css'
import './assets/toast-theme.css'

// Register vue-advanced-chat as a web component (custom element).
// Paired with isCustomElement in vite.config.ts so the Vue compiler leaves
// <vue-advanced-chat> tags alone.
registerChat()

const app = createApp(App)
app.use(createPinia())
app.use(router)

app.use(Toast, {
  position: POSITION.TOP_RIGHT,
  timeout: 4000,
  closeOnClick: true,
  pauseOnHover: true,
  newestOnTop: true,
  maxToasts: 5,
})

app.mount('#app')
