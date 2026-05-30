import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import App from './App.vue'
import './assets/main.css'

const app = createApp(App)
app.use(createPinia())

const auth = useAuthStore()
auth.fetchMe()

app.use(router)
app.mount('#app')
