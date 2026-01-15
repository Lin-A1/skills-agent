<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  BookOpen, Plus, Search, X, MessageSquare, Trash2, Brain
} from 'lucide-vue-next'
import type { SessionInfo } from '@/composables/useChat'

const props = defineProps<{
  isOpen: boolean
  isCollapsed: boolean
  sessions: SessionInfo[]
  currentSessionId: string | null
  searchQuery: string
  showSearch: boolean
}>()

const emit = defineEmits<{
  (e: 'update:searchQuery', value: string): void
  (e: 'toggle'): void
  (e: 'newSession'): void
  (e: 'loadSession', id: string): void
  (e: 'deleteSession', id: string): void
}>()

const scrollToActive = (el: HTMLElement) => {
    // Use nearest to avoid scrolling too much if visible
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

// Filtered sessions based on search query
const filteredSessions = computed(() => {
  if (!props.searchQuery) return props.sessions
  const query = props.searchQuery.toLowerCase()
  return props.sessions.filter(session => 
    session.title?.toLowerCase().includes(query)
  )
})

// Format date for session list
const formatSessionDate = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
  
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return date.toLocaleDateString()
}

// Group sessions by date
const groupedSessions = computed(() => {
  const groups: { [key: string]: any[] } = {}
  
  for (const session of filteredSessions.value) {
    const dateLabel = formatSessionDate(session.updated_at)
    if (!groups[dateLabel]) {
      groups[dateLabel] = []
    }
    groups[dateLabel].push(session)
  }
  return groups
})

// Clean title from any remaining markdown
const cleanTitle = (title: string | null) => {
  if (!title) return 'New Chat'
  return title
    .replace(/\*{1,2}/g, '')  // 移除 * 和 **
    .replace(/_{1,2}/g, '')   // 移除 _ 和 __
    .replace(/`+/g, '')       // 移除 `
    .replace(/^#+\s*/g, '')   // 移除标题标记
    .replace(/[\[\]<>|~#]/g, '') // 移除其他符号
    .trim() || 'New Chat'
}
</script>

<template>
  <div>
       <!-- Mobile Sidebar Overlay -->
    <div v-if="isOpen" class="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 md:hidden cursor-pointer" @click="emit('toggle')"></div>
    
    <!-- Sidebar -->
    <aside :class="[
      'flex flex-col border-r border-black/5 dark:border-white/5 bg-background/95 backdrop-blur-xl fixed left-0 top-0 bottom-0 z-50 transition-all duration-300 ease-in-out',
      isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      isCollapsed ? 'md:w-[0px] md:opacity-0 md:overflow-hidden' : 'md:w-[280px] md:opacity-100'
    ]">
      <!-- Header (Fixed) -->
      <div class="flex-shrink-0 h-16 flex items-center px-6 gap-3 border-b border-black/5 dark:border-white/5">
        <div class="w-8 h-8 rounded-lg bg-black dark:bg-white flex items-center justify-center shadow-lg">
          <BookOpen class="w-4 h-4 text-white dark:text-black" />
        </div>
        <span class="font-semibold text-lg tracking-tight">Sage</span>
      </div>
      
      <!-- New Chat Button (Fixed) -->
      <div class="flex-shrink-0 px-4 py-4 space-y-3">
        <Button @click="emit('newSession')" variant="outline" class="w-full justify-start gap-2 h-10 border-black/5 dark:border-white/10 bg-white/50 dark:bg-white/5 hover:bg-white dark:hover:bg-white/10 text-foreground transition-all duration-300 font-medium shadow-sm hover:shadow-md rounded-lg group">
           <Plus class="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
           <span>New Chat</span>
        </Button>
        
        <div class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input 
            :value="searchQuery"
            @input="emit('update:searchQuery', ($event.target as HTMLInputElement).value)"
            placeholder="Search chats..."
            class="w-full h-9 pl-9 pr-3 rounded-lg bg-secondary border border-transparent hover:bg-zinc-200 dark:hover:bg-zinc-700 focus:bg-background focus:border-primary/20 focus:shadow-sm transition-all text-sm text-foreground outline-none placeholder:text-muted-foreground/70"
          />
          <button 
            v-if="searchQuery"
            @click="emit('update:searchQuery', '')"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-muted rounded"
          >
            <X class="w-3 h-3 text-muted-foreground" />
          </button>
        </div>
      </div>

      <!-- Session List (Scrollable) -->
      <ScrollArea class="flex-1 px-3 pb-4">
        <div class="space-y-6">
          <template v-for="(sessionList, dateLabel) in groupedSessions" :key="dateLabel">
            <div>
              <h3 class="px-3 mb-2 text-xs font-semibold text-muted-foreground/70 uppercase tracking-wider">{{ dateLabel }}</h3>
              <div class="space-y-0.5">
                <div 
                  v-for="session in sessionList" 
                  :key="session.id"
                  :ref="(el) => { if (currentSessionId === session.id && el) scrollToActive(el as HTMLElement) }"
                  class="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all duration-200"
                  :class="currentSessionId === session.id ? 'bg-black/5 dark:bg-white/10 text-foreground font-medium' : 'text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5'"
                  @click="emit('loadSession', session.id)"
                >
                  <Brain v-if="session.mode === 'agent'" class="w-3.5 h-3.5 mr-2 shrink-0 text-primary/70" />
                  <MessageSquare v-else class="w-3.5 h-3.5 mr-2 shrink-0 text-muted-foreground/50" />
                  <span class="flex-1 text-sm truncate">
                    {{ cleanTitle(session.title) }}
                  </span>
                  <button 
                    @click.stop="emit('deleteSession', session.id)"
                    class="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 dark:hover:bg-red-900/30 hover:text-red-600 rounded transition-all"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </template>
          
          <!-- Empty state -->
          <div v-if="sessions.length === 0" class="px-3 py-10 text-center opacity-60">
            <MessageSquare class="w-8 h-8 text-muted mx-auto mb-3" />
            <p class="text-sm text-muted-foreground">No chats yet</p>
          </div>
        </div>
      </ScrollArea>
      
      <!-- Footer (Fixed at bottom) -->
      <div class="flex-shrink-0 p-3 border-t border-border bg-background/30 backdrop-blur-sm">
        <div class="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-background/60 cursor-pointer transition-all duration-200 group">
          <div class="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-serif text-sm shadow-md ring-2 ring-background/50 group-hover:ring-background">L</div>
          <div class="flex-1 min-w-0">
             <div class="text-sm font-semibold text-foreground">Lin</div>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>
