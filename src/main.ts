import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import { POSITION } from 'vue-toastification'
import 'vue-toastification/dist/index.css'
import { router } from './router'
import App from './App.vue'
import './assets/main.css'
import './assets/toast-theme.css'

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
