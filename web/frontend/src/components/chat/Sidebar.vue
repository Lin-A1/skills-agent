<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  BookOpen, Plus, Search, X, MessageSquare, Trash2
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
</script>

<template>
  <div>
       <!-- Mobile Sidebar Overlay -->
    <div v-if="isOpen" class="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 md:hidden cursor-pointer" @click="emit('toggle')"></div>
    
    <!-- Sidebar -->
    <aside :class="[
      'flex flex-col border-r border-border glass-panel fixed left-0 top-0 bottom-0 z-50 transition-all duration-300 ease-in-out',
      isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      isCollapsed ? 'md:w-[0px] md:opacity-0 md:overflow-hidden' : 'md:w-[280px] md:opacity-100'
    ]">
      <!-- Header (Fixed) -->
      <div class="flex-shrink-0 h-16 flex items-center px-6 gap-3 border-b border-border">
        <div class="w-8 h-8 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/10">
          <BookOpen class="w-4 h-4 text-primary-foreground" />
        </div>
        <span class="font-medium text-lg text-primary tracking-tight">Sage</span>
      </div>
      
      <!-- New Chat Button (Fixed) -->
      <div class="flex-shrink-0 px-4 py-4 space-y-3">
        <Button @click="emit('newSession')" variant="outline" class="w-full justify-start gap-2 h-11 border-border bg-background/50 hover:bg-muted hover:border-border text-foreground transition-all duration-300 font-medium shadow-sm hover:shadow-md hover:-translate-y-0.5 group">
           <Plus class="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
           <span>New Chat</span>
        </Button>
        
        <!-- Search Box -->
        <div v-if="showSearch" class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground"/>
          <input
            :value="searchQuery"
            @input="emit('update:searchQuery', ($event.target as HTMLInputElement).value)"
            type="text"
            placeholder="Search chats... (Ctrl+F)"
            class="w-full pl-9 pr-3 py-2 text-sm bg-background/50 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all text-foreground placeholder:text-muted-foreground"
            autofocus
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

      <!-- Recent Sessions (Scrollable) -->
      <ScrollArea class="flex-1 min-h-0 px-2">
        <div class="space-y-4 pb-4">
          <template v-for="(sessionList, dateLabel) in groupedSessions" :key="dateLabel">
            <div>
              <div class="px-4 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-wider opacity-80">
                {{ dateLabel }}
              </div>
              <div class="space-y-1 px-1">
                <div 
                  v-for="session in sessionList" 
                  :key="session.id"
                  class="group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200"
                  :class="currentSessionId === session.id ? 'bg-background shadow-sm ring-1 ring-border' : 'hover:bg-background/60 hover:shadow-sm'"
                  @click="emit('loadSession', session.id)"
                >
                  <MessageSquare class="w-4 h-4 text-muted-foreground flex-shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" />
                  <span class="flex-1 text-sm text-foreground truncate font-medium">
                    {{ session.title || 'New Chat' }}
                  </span>
                  <button 
                    @click.stop="emit('deleteSession', session.id)"
                    class="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-destructive/10 hover:text-destructive rounded-lg transition-all transform hover:scale-105"
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
