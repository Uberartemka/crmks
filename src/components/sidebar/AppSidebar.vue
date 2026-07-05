<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  LayoutDashboard, ListChecks, Users, FileText, LogOut,
  BarChart3, Search, Briefcase, Phone, PersonStanding, ShoppingCart,
  Calculator, Cog, ClipboardList, History, Send, CalendarDays, MessagesSquare
} from 'lucide-vue-next'
import Avatar from '@/components/ui/Avatar.vue'
import { useChatPanel } from '@/composables/useChatPanel'

const auth = useAuthStore()
const router = useRouter()
const { isOpen: chatOpen, open: openChat, close: closeChat } = useChatPanel()

interface MenuItem {
  to?: string // если задано — рендерится как <RouterLink>
  label: string
  icon: any
  action?: () => void // если задано — рендерится как <button> (например, открыть панель чата)
  active?: () => boolean // для action-элементов: подсветка
}

const menu = computed<MenuItem[]>(() => {
  const base = `/${auth.role}`
  // Воркспейс — для всех ролей (включая client).
  const common: MenuItem[] = [{ to: `${base}/dashboard`, label: 'Воркспейс', icon: LayoutDashboard }]
  // Чат — только для staff (clients не видят чат). Ставим сразу после Воркспейса.
  // Это action-кнопка (открывает slide-out панель), а не роут — поэтому .action, без .to.
  const commonStaff: MenuItem[] = [
    { to: `${base}/dashboard`, label: 'Воркспейс', icon: LayoutDashboard },
    {
      label: 'Чат',
      icon: MessagesSquare,
      action: () => (chatOpen.value ? closeChat() : openChat()),
      active: () => chatOpen.value,
    },
  ]
  if (auth.role === 'admin') return [
    ...commonStaff,
    { to: `${base}/proposals`, label: 'Умное КП', icon: FileText },
    { to: `${base}/reports`, label: 'Отчеты', icon: BarChart3 },
    { to: `${base}/parser`, label: 'Парсер лидов', icon: Search },
    { to: `${base}/leads`, label: 'Лиды', icon: Search },
    { to: `${base}/audit`, label: 'Чемоданчик', icon: Briefcase },
    { to: `${base}/clients`, label: 'База клиентов', icon: Users },
    { to: `${base}/catalog`, label: 'Каталог товаров', icon: ShoppingCart },
    { to: `${base}/plans`, label: 'Планы', icon: ListChecks },
    { to: `${base}/calls`, label: 'Звонки', icon: Phone },
    { to: `${base}/calendar`, label: 'Календарь', icon: CalendarDays },
    { to: `${base}/personnel`, label: 'Персонал', icon: PersonStanding },
    { to: `${base}/orders`, label: 'Заказы', icon: ShoppingCart },
    { to: `${base}/machinery`, label: 'Оборудование', icon: Cog },
    { to: `${base}/calculator`, label: 'ISO 281', icon: Calculator },
    { to: `${base}/defects`, label: 'Дефектовка', icon: ClipboardList },
  ]
  if (auth.role === 'manager') return [
    ...commonStaff,
    { to: `${base}/plan`, label: 'Мой план', icon: ListChecks },
    { to: `${base}/leads`, label: 'Мои лиды', icon: Users },
    { to: `${base}/calls`, label: 'Звонки', icon: Phone },
    { to: `${base}/proposals`, label: 'Отправить КП', icon: Send },
    { to: `${base}/calendar`, label: 'Календарь', icon: CalendarDays },
    { to: `${base}/proposal-history`, label: 'История КП', icon: History },
  ]

  if (auth.role === 'employee') return [
    ...commonStaff,
    { to: `${base}/plan`, label: 'Мой план', icon: ListChecks },
  ]

  return [
    ...common,
    { to: `${base}/orders`, label: 'Мои заказы', icon: ShoppingCart },
    { to: `${base}/calculator`, label: 'ISO 281', icon: Calculator },
    { to: `${base}/machinery`, label: 'Оборудование', icon: Cog },
    { to: `${base}/calendar`, label: 'Календарь', icon: CalendarDays },
    { to: `${base}/defects`, label: 'Дефектовка', icon: ClipboardList },
  ]
})
</script>

<template>
  <aside class="w-56 shrink-0 bg-white border-r border-slate-200 flex flex-col">
    <div class="px-4 py-3 border-b border-slate-200">
      <div class="font-bold text-brand-700">HHB</div>
      <div class="text-xs text-slate-500 capitalize">{{ auth.role }}</div>
    </div>

    <nav class="flex-1 p-2 space-y-0.5">
      <template v-for="item in menu" :key="item.label">
        <!-- Action-кнопка (например, открыть чат-панель) -->
        <button
          v-if="item.action"
          type="button"
          class="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-slate-700 hover:bg-slate-100 transition-colors"
          :class="{ '!bg-brand-50 !text-brand-700 font-medium': item.active?.() }"
          @click="item.action"
        >
          <component :is="item.icon" :size="16" />
          {{ item.label }}
        </button>
        <!-- Обычный роут-линк -->
        <RouterLink
          v-else
          :to="item.to!"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm text-slate-700 hover:bg-slate-100"
          active-class="!bg-brand-50 !text-brand-700 font-medium"
        >
          <component :is="item.icon" :size="16" />
          {{ item.label }}
        </RouterLink>
      </template>
    </nav>

    <div class="p-2 border-t border-slate-200">
      <RouterLink to="/profile" class="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-slate-100">
        <Avatar :name="auth.user?.name ?? '?'" :src="auth.avatarUrl" :size="32" class="shrink-0" />
        <div class="min-w-0 flex-1">
          <div class="text-xs font-medium truncate">{{ auth.user?.username }}</div>
          <div class="text-xs text-slate-500">Профиль</div>
        </div>
      </RouterLink>
      <button class="btn-ghost w-full justify-start text-sm" @click="auth.logout(); router.push('/login')">
        <LogOut :size="14" /> Выйти
      </button>
    </div>
  </aside>
</template>
