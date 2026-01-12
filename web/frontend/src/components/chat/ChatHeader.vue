<script setup lang="ts">
import { 
  Menu, X, PanelLeftOpen, PanelLeftClose 
} from 'lucide-vue-next'

defineProps<{
  sessionId: string | null
  isSidebarCollapsed: boolean
  sidebarOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'toggleSidebar'): void
  (e: 'toggleSidebarDesktop'): void
}>()
</script>

<template>
  <header :class="[
    'fixed top-0 right-0 z-30 flex items-center justify-between px-4 h-14 border-b border-border backdrop-blur-xl transition-all duration-300 ease-in-out',
    'bg-background/90',
    sidebarOpen ? 'left-0' : (isSidebarCollapsed ? 'left-0' : 'md:left-[280px] left-0')
  ]">
    <div class="flex items-center gap-3">
      <!-- Mobile Menu Button -->
       <button @click="emit('toggleSidebar')" class="md:hidden p-2 -ml-2 hover:bg-muted rounded-xl transition-colors">
        <Menu v-if="!sidebarOpen" class="w-5 h-5 text-muted-foreground" />
        <X v-else class="w-5 h-5 text-muted-foreground" />
      </button>
      
      <!-- Desktop Sidebar Toggle -->
      <button @click="emit('toggleSidebarDesktop')" class="hidden md:flex p-2 -ml-2 hover:bg-muted rounded-xl transition-colors text-muted-foreground">
        <PanelLeftOpen v-if="isSidebarCollapsed" class="w-5 h-5" />
        <PanelLeftClose v-else class="w-5 h-5" />
      </button>

      <div class="flex items-center gap-2.5 text-sm">
        <h1 class="font-semibold text-foreground tracking-tight">Sage</h1>
        <span class="text-muted-foreground/20" aria-hidden="true">•</span>
        <span v-if="sessionId" class="text-muted-foreground font-medium bg-background/50 px-2 py-0.5 rounded-md text-xs border border-transparent">Session Active</span>
        <span v-else class="text-muted-foreground font-medium bg-background/50 px-2 py-0.5 rounded-md text-xs border border-transparent">New Session</span>
      </div>
    </div>
  </header>
</template>
