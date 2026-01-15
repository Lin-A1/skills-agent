<script setup lang="ts">
import { 
  Menu, X, PanelLeftOpen, PanelLeftClose
} from 'lucide-vue-next'

defineProps<{
  sessionId: string | null
  isSidebarCollapsed: boolean
  sidebarOpen: boolean
  isCanvasOpen?: boolean
  isAgentMode?: boolean
}>()

const emit = defineEmits<{
  (e: 'toggleSidebar'): void
  (e: 'toggleSidebarDesktop'): void
  (e: 'toggleAgentMode'): void
}>()
</script>

<template>
  <header :class="[
    'fixed top-0 z-30 flex items-center justify-between px-4 h-14 transition-all duration-300 ease-in-out',
    'bg-background/90 backdrop-blur-md border-b border-black/5 dark:border-white/5',
    sidebarOpen ? 'left-0' : (isSidebarCollapsed ? 'left-0' : 'md:left-[280px] left-0'),
    isCanvasOpen ? 'md:right-[45vw] right-0' : 'right-0'
  ]">
    <div class="flex items-center gap-3">
      <!-- Mobile Menu Button -->
       <button @click="emit('toggleSidebar')" class="md:hidden p-2 -ml-2 text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-lg transition-colors">
        <Menu v-if="!sidebarOpen" class="w-5 h-5" />
        <X v-else class="w-5 h-5" />
      </button>
      
      <!-- Desktop Sidebar Toggle -->
      <button @click="emit('toggleSidebarDesktop')" class="hidden md:flex p-2 -ml-2 text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-lg transition-colors">
        <PanelLeftOpen v-if="isSidebarCollapsed" class="w-4.5 h-4.5" />
        <PanelLeftClose v-else class="w-4.5 h-4.5" />
      </button>

      <div class="flex items-center gap-3 text-sm">
        <h1 class="font-semibold text-foreground tracking-tight opacity-90">Sage</h1>
        <div class="h-4 w-[1px] bg-black/10 dark:bg-white/10" aria-hidden="true"></div>
        <span v-if="sessionId" class="text-xs text-muted-foreground font-medium opacity-70">Session Active</span>
        <span v-else class="text-xs text-muted-foreground font-medium opacity-70">New Session</span>
      </div>
    </div>
    
    <!-- Right Side: Mode Toggle -->
    <div class="flex items-center gap-2">
      <div 
        :class="[
          'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border select-none cursor-default',
          isAgentMode 
            ? 'bg-indigo-50 dark:bg-indigo-500/10 text-primary border-primary/20' 
            : 'bg-muted/50 text-muted-foreground border-border'
        ]"
      >
        <span class="relative flex h-2 w-2 mr-0.5">
          <span :class="['relative inline-flex rounded-full h-2 w-2', isAgentMode ? 'bg-primary' : 'bg-muted-foreground']"></span>
        </span>
        <span>{{ isAgentMode ? 'Agent Mode' : 'Chat Mode' }}</span>
      </div>
    </div>
  </header>
</template>
