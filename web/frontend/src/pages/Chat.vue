<script setup lang="ts">
import { ref, computed } from 'vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { 
  SendIcon, Plus, BookOpen, Copy, Check, Square, Pencil,
  MessageSquare, Trash2, Menu, X, Bot, Brain, CornerUpLeft, Search,
  Wrench, ChevronDown, PanelLeftClose, PanelLeftOpen, Timer,
  ImageIcon, PenLine, Wand2, RefreshCcw
} from 'lucide-vue-next'
import { useChat } from '@/composables/useChat'
import { renderMarkdown } from '@/lib/markdown'

// Mobile sidebar state
const sidebarOpen = ref(false)
const toggleSidebar = () => { sidebarOpen.value = !sidebarOpen.value }

// Desktop sidebar collapse state
const isSidebarCollapsed = ref(false)
const toggleSidebarDesktop = () => { isSidebarCollapsed.value = !isSidebarCollapsed.value }

const { 
  messages, input, handleSubmit, status, sessionId, sessions,
  startNewSession, loadSession: internalLoadSession, deleteSession,
  adjustHeight, textareaRef, scrollContainerRef, bottomRef,
  copyMessage, copiedMessageId, editingMessageId, editingContent,
  startEdit, cancelEdit, saveEditAndRegenerate, stopGeneration,
  rollbackToMessage, isLoadingSession,
  toastMessage, toastType, regenerateFromMessage,
  isAgentMode, searchQuery, showSearch,
  uploadedImages, fileInputRef, MAX_IMAGES, triggerImageUpload,
  handleImageSelect, removeImage, thinkingSeconds
} = useChat()

// Wrapper for loadSession to handle sidebar closing
const loadSession = async (id: string) => {
  const success = await internalLoadSession(id)
  if (success) {
    sidebarOpen.value = false
  }
}

// Filtered sessions based on search query
const filteredSessions = computed(() => {
  if (!searchQuery.value) return sessions.value
  const query = searchQuery.value.toLowerCase()
  return sessions.value.filter(session => 
    session.title?.toLowerCase().includes(query)
  )
})

// Format date for session list
const formatSessionDate = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
  
  if (diffDays === 0) return '今天'
  if (diffDays === 1) return '昨天'
  if (diffDays < 7) return `${diffDays} 天前`
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
  <div :class="['flex h-[100dvh] text-[#1C1917] font-sans selection:bg-[#E7E5E4]', isAgentMode ? 'bg-[#F0F4FF]' : 'bg-[#FAFAF9]']">
    <!-- Toast Notification -->
    <Transition name="toast">
      <div v-if="toastMessage" 
        :class="[
          'fixed top-4 right-4 z-[100] px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all',
          toastType === 'error' ? 'bg-red-500 text-white' : 'bg-[#334155] text-white'
        ]"
      >
        {{ toastMessage }}
      </div>
    </Transition>
    
    <!-- Loading Overlay -->
    <div v-if="isLoadingSession" class="fixed inset-0 bg-white/50 z-[90] flex items-center justify-center md:ml-[280px]">
      <div class="w-8 h-8 border-2 border-[#334155] border-t-transparent rounded-full animate-spin"></div>
    </div>
    
    <!-- Mobile Sidebar Overlay -->
    <div v-if="sidebarOpen" class="fixed inset-0 bg-black/50 z-40 md:hidden cursor-pointer backdrop-blur-sm" @click="sidebarOpen = false"></div>
    
    <!-- Sidebar -->
    <aside :class="[
      'flex flex-col border-r border-white/50 glass-panel fixed left-0 top-0 bottom-0 z-50 transition-all duration-300 ease-in-out',
      sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      isSidebarCollapsed ? 'md:w-[0px] md:opacity-0 md:overflow-hidden' : 'md:w-[280px] md:opacity-100'
    ]">
      <!-- Header (Fixed) -->
      <div class="flex-shrink-0 h-16 flex items-center px-6 gap-3 border-b border-black/5">
        <div class="w-8 h-8 rounded-xl bg-gradient-to-br from-[#334155] to-[#1e293b] flex items-center justify-center shadow-lg shadow-indigo-500/10">
          <BookOpen class="w-4 h-4 text-white" />
        </div>
        <span class="font-medium text-lg text-[#334155] tracking-tight">Sage</span>
        <div class="ml-auto flex items-center gap-2">
           <!-- Agent Toggle Removed from Header -->
        </div>
      </div>
      
      <!-- New Chat Button (Fixed) -->
      <div class="flex-shrink-0 px-4 py-4 space-y-3">
        <Button @click="startNewSession" variant="outline" class="w-full justify-start gap-2 h-11 border-white/60 bg-white/50 hover:bg-white/80 hover:border-black/5 text-[#44403C] transition-all duration-300 font-medium shadow-sm hover:shadow-md hover:-translate-y-0.5 group">
           <Plus class="w-4 h-4 text-[#78716C] group-hover:text-[#334155] transition-colors" />
           <span>新对话</span>
        </Button>
        
        <!-- Search Box -->
        <div v-if="showSearch" class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#A8A29E]"/>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索对话... (Ctrl+F)"
            class="w-full pl-9 pr-3 py-2 text-sm bg-white/50 border border-white/60 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#334155]/20 focus:border-[#334155]/40 transition-all text-[#44403C] placeholder:text-[#A8A29E]"
            autofocus
          />
          <button 
            v-if="searchQuery"
            @click="searchQuery = ''"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-black/5 rounded"
          >
            <X class="w-3 h-3 text-[#A8A29E]" />
          </button>
        </div>
      </div>

      <!-- Recent Sessions (Scrollable) -->
      <ScrollArea class="flex-1 min-h-0 px-2">
        <div class="space-y-4 pb-4">
          <template v-for="(sessionList, dateLabel) in groupedSessions" :key="dateLabel">
            <div>
              <div class="px-4 py-2 text-[10px] font-bold text-[#A8A29E] uppercase tracking-wider opacity-80">
                {{ dateLabel }}
              </div>
              <div class="space-y-1 px-1">
                <div 
                  v-for="session in sessionList" 
                  :key="session.id"
                  class="group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200"
                  :class="sessionId === session.id ? 'bg-white shadow-sm ring-1 ring-black/5' : 'hover:bg-white/60 hover:shadow-sm'"
                  @click="loadSession(session.id)"
                >
                  <MessageSquare class="w-4 h-4 text-[#78716C] flex-shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" />
                  <span class="flex-1 text-sm text-[#44403C] truncate font-medium">
                    {{ session.title || '新对话' }}
                  </span>
                  <button 
                    @click.stop="deleteSession(session.id)"
                    class="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-50 hover:text-red-500 rounded-lg transition-all transform hover:scale-105"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </template>
          
          <!-- Empty state -->
          <div v-if="sessions.length === 0" class="px-3 py-10 text-center opacity-60">
            <MessageSquare class="w-8 h-8 text-[#D6D3D1] mx-auto mb-3" />
            <p class="text-sm text-[#78716C]">暂无对话</p>
          </div>
        </div>
      </ScrollArea>
      
      <!-- Footer (Fixed at bottom) -->
      <div class="flex-shrink-0 p-3 border-t border-black/5 bg-white/30 backdrop-blur-sm">
        <div class="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/60 cursor-pointer transition-all duration-200 group">
          <div class="w-8 h-8 rounded-full bg-gradient-to-br from-[#334155] to-[#1e293b] text-white flex items-center justify-center font-serif text-sm shadow-md ring-2 ring-white/50 group-hover:ring-white">L</div>
          <div class="flex-1 min-w-0">
             <div class="text-sm font-semibold text-[#1C1917]">Lin</div>
          </div>
        </div>
      </div>
    </aside>
    
    <!-- Collapsed Sidebar floating toggle (Visible only when sidebar is closed on desktop) -->
    <div v-if="isSidebarCollapsed" class="hidden md:block fixed left-4 top-3 z-50">
        <!-- This is handled by the header toggle button now, but having a floating trigger area can be nice. 
             For now, relying on the header button inside Main is enough as header is sticky. -->
    </div>

    <!-- Main -->
    <main :class="[
        'flex-1 flex flex-col min-w-0 relative transition-all duration-500 ease-in-out',
        isSidebarCollapsed ? 'md:ml-0' : 'md:ml-[280px]',
        isAgentMode ? 'bg-[#F0F4FF]' : 'bg-[#F8F7F5]'
    ]">
      <!-- Background Decor (Hidden on mobile for performance) -->
      <div class="hidden md:block fixed inset-0 pointer-events-none z-0">
          <div class="absolute top-0 right-0 w-[500px] h-[500px] bg-indigo-50/50 rounded-full blur-3xl opacity-60 mix-blend-multiply"></div>
          <div class="absolute bottom-0 left-0 w-[500px] h-[500px] bg-orange-50/50 rounded-full blur-3xl opacity-60 mix-blend-multiply"></div>
      </div>

      <!-- Top Bar -->
      <header :class="[
        'sticky top-0 z-30 flex items-center justify-between px-4 py-3 border-b border-black/5 backdrop-blur-xl transition-all duration-300',
        isAgentMode ? 'bg-[#F0F4FF]/90' : 'bg-[#FAFAF9]/90'
      ]">
        <div class="flex items-center gap-3">
          <!-- Mobile Menu Button -->
           <button @click="toggleSidebar" class="md:hidden p-2 -ml-2 hover:bg-black/5 rounded-xl transition-colors">
            <Menu v-if="!sidebarOpen" class="w-5 h-5 text-[#57534E]" />
            <X v-else class="w-5 h-5 text-[#57534E]" />
          </button>
          
          <!-- Desktop Sidebar Toggle -->
          <button @click="toggleSidebarDesktop" class="hidden md:flex p-2 -ml-2 hover:bg-black/5 rounded-xl transition-colors text-[#57534E]">
            <PanelLeftOpen v-if="isSidebarCollapsed" class="w-5 h-5" />
            <PanelLeftClose v-else class="w-5 h-5" />
          </button>

          <div class="flex items-center gap-2.5 text-sm">
            <h1 class="font-semibold text-[#1C1917] tracking-tight">Sage</h1>
            <span class="text-black/10" aria-hidden="true">•</span>
            <span v-if="sessionId" class="text-[#57534E] font-medium bg-white/50 px-2 py-0.5 rounded-md text-xs border border-transparent">会话进行中</span>
            <span v-else class="text-[#78716C] font-medium bg-white/50 px-2 py-0.5 rounded-md text-xs border border-transparent">新对话</span>
          </div>
        </div>
        <!-- Knowledge Panel Toggle -->

      </header>

      <ScrollArea ref="scrollContainerRef" class="flex-1">
        <div class="max-w-3xl mx-auto px-6 py-8 w-full pb-40">
          
          <!-- Empty State (New Design) -->
          <div v-if="messages.length === 0" class="flex flex-col items-center justify-center min-h-[70vh] relative z-20 animate-in fade-in zoom-in-95 duration-500">
             
             <!-- Title -->
             <h2 class="text-3xl font-medium text-[#1C1917] mb-12 tracking-tight">有什么可以帮忙的？</h2>

             <!-- Agent Toggle (Prominent) -->
             <div class="flex items-center gap-3 mb-6 bg-white/50 backdrop-blur-sm px-4 py-2 rounded-full border border-black/5 shadow-sm hover:shadow-md transition-all duration-300 cursor-pointer" @click="isAgentMode = !isAgentMode">
                 <div class="flex items-center gap-2">
                     <span class="text-xs font-semibold uppercase tracking-wider transition-colors duration-300" :class="isAgentMode ? 'text-indigo-600' : 'text-[#78716C]'">Agent Mode</span>
                     <div class="w-8 h-5 rounded-full relative transition-colors duration-300" :class="isAgentMode ? 'bg-indigo-600' : 'bg-[#E7E5E4]'">
                         <div class="absolute top-1 left-1 w-3 h-3 rounded-full bg-white shadow-sm transition-transform duration-300" :class="isAgentMode ? 'translate-x-3' : 'translate-x-0'"></div>
                     </div>
                 </div>
                 <Bot class="w-4 h-4 transition-colors duration-300" :class="isAgentMode ? 'text-indigo-600' : 'text-[#A8A29E]'" />
             </div>

             <!-- Center Input Box -->
             <div class="w-full max-w-2xl relative group">
                 <!-- Image Previews -->
                 <div v-if="uploadedImages.length > 0 && !isAgentMode" class="flex gap-2 mb-4 justify-center">
                    <div v-for="(img, index) in uploadedImages" :key="index" class="relative group/img">
                        <img :src="img.base64" class="w-16 h-16 object-cover rounded-xl border border-black/10 shadow-sm" />
                        <button @click="removeImage(index)" class="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center shadow-md hover:bg-red-600">
                            <X class="w-3 h-3" />
                        </button>
                    </div>
                 </div>

                 <!-- Copied File Input -->
                 <input type="file" ref="fileInputRef" @change="handleImageSelect" accept="image/*" multiple class="hidden" />

                 <div class="relative bg-white rounded-[2rem] shadow-xl shadow-indigo-900/5 border border-black/5 transition-all duration-300 hover:shadow-2xl hover:shadow-indigo-900/10 hover:-translate-y-0.5 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-500/50">
                     <form @submit="handleSubmit" class="flex items-center p-2 pl-4">
                         <!-- Upload Button -->
                         <Button v-if="!isAgentMode" type="button" variant="ghost" size="icon" @click="triggerImageUpload" :disabled="uploadedImages.length >= MAX_IMAGES" class="text-[#78716C] hover:text-[#1C1917] hover:bg-black/5 rounded-full w-10 h-10 flex-shrink-0">
                             <Plus class="w-5 h-5" />
                         </Button>

                         <!-- Input -->
                         <textarea
                            v-model="input"
                            ref="textareaRef"
                            @keydown.enter.exact.prevent="handleSubmit"
                            @input="adjustHeight"
                            placeholder="询问任何问题... (Shift+Enter 换行)"
                            rows="1"
                            class="flex-1 bg-transparent border-none focus:ring-0 text-lg px-4 py-3 placeholder:text-[#A8A29E] text-[#1C1917] resize-none overflow-hidden min-h-[56px] max-h-[200px]"
                            :disabled="false"
                            autocomplete="off"
                         ></textarea>

                         <!-- Right Actions -->
                         <div class="flex items-center gap-1 pr-1">

                             <Button type="submit" :disabled="!input.trim() && uploadedImages.length === 0" size="icon" :class="['w-10 h-10 rounded-full transition-all duration-200', (!input.trim() && uploadedImages.length === 0) ? 'bg-[#E7E5E4] text-[#A8A29E]' : 'bg-[#1C1917] text-white hover:bg-[#333] shadow-md']">
                                 <SendIcon class="w-5 h-5" />
                             </Button>
                         </div>
                     </form>
                 </div>
                 
                 <!-- Footer Hints -->
                 <div class="mt-8 flex justify-center gap-4 text-xs text-[#A8A29E] font-medium">
                     <span class="flex items-center gap-1 hover:text-[#78716C] cursor-pointer transition-colors border border-black/5 px-3 py-1.5 rounded-full bg-white/50"><PenLine class="w-3 h-3" /> 帮我写作</span>
                     <span class="flex items-center gap-1 hover:text-[#78716C] cursor-pointer transition-colors border border-black/5 px-3 py-1.5 rounded-full bg-white/50"><ImageIcon class="w-3 h-3" /> 分析图片</span>
                     <span class="flex items-center gap-1 hover:text-[#78716C] cursor-pointer transition-colors border border-black/5 px-3 py-1.5 rounded-full bg-white/50"><Wand2 class="w-3 h-3" /> 代码优化</span>
                 </div>
             </div>
          </div>

          <!-- Messages -->
          <div v-else class="space-y-8 relative z-10">
            <template v-for="(msg, index) in messages" :key="msg.id">
              <!-- User Message -->
              <div v-if="msg.role === 'user'" class="animate-in fade-in slide-in-from-bottom-4 duration-500 fill-mode-forwards" style="animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);">
                <!-- Edit mode - Full width like reference image -->
                <div v-if="editingMessageId === msg.id" class="w-full">
                  <div class="bg-[#FAFAF9] border border-[#E7E5E4] rounded-xl p-4 shadow-sm">
                    <textarea
                      v-model="editingContent"
                      class="w-full min-h-[60px] text-[15px] text-[#1C1917] bg-transparent resize-none outline-none placeholder:text-[#A8A29E] font-normal leading-relaxed"
                      @keydown.enter.ctrl="saveEditAndRegenerate"
                    ></textarea>
                  </div>
                  <div class="flex items-center justify-between mt-3 px-1">
                    <p class="text-xs text-[#78716C] flex items-center gap-1.5">
                      <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <circle cx="12" cy="12" r="10" stroke-width="1.5"/>
                        <path d="M12 8v4M12 16h.01" stroke-width="2" stroke-linecap="round"/>
                      </svg>
                      Editing this message will create a new conversation branch.
                    </p>
                    <div class="flex items-center gap-2">
                      <Button size="sm" variant="outline" @click="cancelEdit" class="h-8 px-4 text-[#57534E] border-[#D6D3D1] hover:bg-[#F5F5F4]">Cancel</Button>
                      <Button size="sm" @click="saveEditAndRegenerate" class="h-8 px-4 bg-[#1C1917] hover:bg-[#44403C] text-white">Save</Button>
                    </div>
                  </div>
                </div>
                <!-- Normal mode - Right aligned -->
                <div v-else class="flex justify-end group">
                  <div class="flex flex-col items-end gap-1 max-w-[85%]">
                    <div class="bg-[#334155] text-white px-5 py-3.5 rounded-2xl rounded-br-sm text-[15px] leading-relaxed shadow-lg shadow-indigo-900/10 transition-all hover:shadow-indigo-900/20 hover:-translate-y-0.5 tracking-wide font-light whitespace-pre-wrap">
                      <!-- Render Images if present -->
                      <div v-if="msg.images && msg.images.length > 0" class="flex flex-wrap gap-2 mb-2">
                        <img 
                          v-for="(img, imgIndex) in msg.images" 
                          :key="imgIndex"
                          :src="img" 
                          class="max-w-full h-auto max-h-[300px] rounded-lg border border-white/10"
                        />
                      </div>
                      {{ msg.content }}
                    </div>
                    <!-- Edit button (below message) -->
                    <div class="flex items-center gap-2">
                      <button 
                        @click="startEdit(msg)"
                        class="flex items-center gap-1 px-2 py-1 text-xs text-[#A8A29E] hover:text-[#44403C] hover:bg-black/5 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        title="编辑消息"
                      >
                        <Pencil class="w-3 h-3" />
                        <span>编辑</span>
                      </button>
                      <button 
                        @click="rollbackToMessage(msg.id)"
                        class="flex items-center gap-1 px-2 py-1 text-xs text-[#A8A29E] hover:text-red-600 hover:bg-red-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        title="回退并删除此消息"
                      >
                        <CornerUpLeft class="w-3 h-3" />
                        <span>回退</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

               <!-- Assistant Message -->
              <div v-else class="flex gap-5 animate-in fade-in duration-700 slide-in-from-bottom-2 group" style="animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);">
                <div class="flex-shrink-0 mt-1">
                  <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#334155] to-[#1e293b] flex items-center justify-center shadow-lg shadow-indigo-500/10">
                    <BookOpen class="w-4.5 h-4.5 text-white" />
                  </div>
                </div>
                <div class="flex-1 min-w-0 space-y-2.5">
                    <div class="text-[13px] font-bold text-[#334155] ml-1 tracking-wide uppercase opacity-70">Sage</div>
                    
                    <!-- Agent Process/Thinking Block -->
                    <div v-if="msg.agentSteps && msg.agentSteps.length > 0" class="mb-4">
                      <details class="group bg-white/50 rounded-xl border border-black/5 open:bg-white open:shadow-sm transition-all" :open="(index === messages.length - 1 && status === 'streaming') || (!msg.content && msg.agentSteps.length > 0)">
                          <summary class="flex items-center gap-2 px-3 py-2 cursor-pointer text-xs font-medium text-[#78716C] hover:text-[#44403C] select-none list-none rounded-xl">
                              <Brain class="w-3.5 h-3.5 text-indigo-500" />
                              <span>思考过程</span>
                              <span class="ml-auto flex items-center gap-2 text-[10px] text-[#78716C] bg-black/5 px-2 py-0.5 rounded-full group-open:hidden">
                                  <span v-if="status === 'streaming' && index === messages.length - 1" class="flex items-center gap-1">
                                    <Timer class="w-3 h-3" />
                                    {{ thinkingSeconds }}s
                                  </span>
                                  <span>{{ msg.agentSteps.length }} 步骤</span>
                              </span>
                              <ChevronDown class="w-3.5 h-3.5 transition-transform duration-200 group-open:rotate-180 text-[#A8A29E]" />
                          </summary>
                          <div class="px-3 pb-3 space-y-3 pt-1 border-t border-black/5 mx-1 mt-1">
                              <div v-for="(step, i) in msg.agentSteps" :key="i" class="text-xs">
                                  <!-- Thought -->
                                  <div v-if="step.type === 'thought'" class="text-[#57534E] italic border-l-2 border-black/10 pl-3 py-1">
                                      {{ step.content }}
                                  </div>
                                  <!-- Action -->
                                  <div v-else-if="step.type === 'action'" class="bg-[#F8F7F5] rounded-lg p-2.5 border border-black/5 text-[#44403C]">
                                      <div class="flex items-center gap-1.5 mb-1.5 text-indigo-600 font-bold">
                                          <Wrench class="w-3 h-3" />
                                          <span>调用: {{ step.toolName }}</span>
                                      </div>
                                      <div class="bg-white rounded border border-black/5 p-2 overflow-x-auto">
                                          <pre class="font-mono text-[10px]">{{ JSON.stringify(step.toolInput, null, 2) }}</pre>
                                      </div>
                                  </div>
                                  <!-- Observation -->
                                  <div v-else-if="step.type === 'observation'" class="bg-[#ECFDF5]/50 rounded-lg p-2.5 border border-emerald-100/50 text-[#44403C]">
                                      <div class="flex items-center gap-1.5 mb-1.5 text-emerald-600 font-bold">
                                          <Check class="w-3 h-3" />
                                          <span>结果</span>
                                      </div>
                                      <div class="bg-white/50 rounded border border-emerald-100/50 p-2 overflow-x-auto max-h-40 scrollbar-thin">
                                          <pre class="font-mono text-[10px] whitespace-pre-wrap">{{ step.content }}</pre>
                                      </div>
                                  </div>
                                  <!-- Error -->
                                  <div v-else-if="step.type === 'error'" class="bg-red-50 text-red-600 p-2 rounded border border-red-100 font-medium">
                                      Error: {{ step.content }}
                                  </div>
                              </div>
                          </div>
                      </details>
                    </div>

                    <!-- Reasoning Block for Non-Agent Models -->
                    <div v-if="msg.reasoning" class="mb-4">
                      <details class="group bg-white/50 rounded-xl border border-black/5 open:bg-white open:shadow-sm transition-all" :open="index === messages.length - 1 && status === 'streaming'">
                          <summary class="flex items-center gap-2 px-3 py-2 cursor-pointer text-xs font-medium text-[#78716C] hover:text-[#44403C] select-none list-none rounded-xl">
                              <Brain class="w-3.5 h-3.5 text-indigo-500" />
                              <span>深度思考</span>
                              <ChevronDown class="w-3.5 h-3.5 transition-transform duration-200 group-open:rotate-180 text-[#A8A29E] ml-auto" />
                          </summary>
                          <div class="px-3 pb-3 pt-1 border-t border-black/5 mx-1 mt-1">
                              <div class="text-xs text-[#57534E] whitespace-pre-wrap leading-relaxed italic border-l-2 border-indigo-100 pl-3">
                                  {{ msg.reasoning }}
                              </div>
                          </div>
                      </details>
                    </div>

                    <div class="prose prose-slate max-w-none text-[#1C1917] leading-8 font-normal tracking-normal glass p-5 rounded-2xl rounded-tl-sm shadow-sm border-0">

                        <div v-if="msg.content" v-html="renderMarkdown(msg.content)"></div>
                        <div v-else-if="status !== 'streaming'" class="text-[#A8A29E] italic">
                            (No response generated)
                        </div>

                         <div v-if="!msg.content && (index === messages.length - 1 && status === 'streaming')" class="py-1 flex items-center gap-3">
                           <div class="relative flex items-center justify-center w-5 h-5">
                             <div class="absolute inset-0 bg-indigo-500/20 rounded-full animate-ping"></div>
                             <div class="relative w-2.5 h-2.5 bg-gradient-to-tr from-indigo-500 to-violet-500 rounded-full animate-spin"></div>
                           </div>
                           <span class="text-sm font-medium text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-violet-500 animate-pulse">正在思考 <span v-if="thinkingSeconds > 0">({{ thinkingSeconds }}s)</span>...</span>
                         </div>

                    </div>
                    
                    <!-- Message Actions -->
                    <div v-if="msg.content" class="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity pl-1">
                      <button 
                        @click="copyMessage(msg)" 
                        class="p-1.5 text-[#A8A29E] hover:text-[#44403C] hover:bg-black/5 rounded-md transition-colors"
                        title="复制"
                      >
                         <Check v-if="copiedMessageId === msg.id" class="w-3.5 h-3.5 text-green-600" />
                         <Copy v-else class="w-3.5 h-3.5" />
                      </button>
                      <button 
                        @click="regenerateFromMessage(messages[index - 1]!)"
                        v-if="index > 0 && messages[index - 1]?.role === 'user'"
                        class="p-1.5 text-[#A8A29E] hover:text-[#44403C] hover:bg-black/5 rounded-md transition-colors"
                        title="重新生成"
                      >
                         <RefreshCcw class="w-3.5 h-3.5" />
                      </button>
                    </div>
                </div>
              </div>
            </template>
            <div ref="bottomRef" class="h-4"></div>
          </div>
        </div>
      </ScrollArea>

      <!-- Input Area -->
      <div v-if="messages.length > 0" :class="[
          'p-6 fixed bottom-0 right-0 bg-gradient-to-t from-[#F8F7F5] via-[#F8F7F5]/90 to-transparent z-20 pointer-events-none transition-all duration-300 ease-in-out',
          isSidebarCollapsed ? 'left-0' : 'left-0 md:left-[280px]'
      ]">
        <div class="max-w-3xl mx-auto pointer-events-auto">
          <!-- Stop Generation Button -->
          <div v-if="status === 'streaming'" class="flex justify-center mb-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
             <Button variant="outline" size="sm" class="bg-white/80 backdrop-blur border-white/50 text-[#44403C] shadow-lg hover:bg-white" @click="stopGeneration">
                <Square class="w-3 h-3 mr-2 fill-current" />
                停止生成
             </Button>
          </div>
          
          <div class="relative group">
             <!-- 图片预览区域 -->
             <div v-if="uploadedImages.length > 0 && !isAgentMode" class="flex gap-2 mb-2 px-2">
               <div v-for="(img, index) in uploadedImages" :key="index" class="relative group/img">
                 <img 
                   :src="img.base64" 
                   :alt="img.name"
                   class="w-16 h-16 object-cover rounded-lg border border-black/10 shadow-sm"
                 />
                 <button 
                   @click="removeImage(index)"
                   class="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-opacity shadow-md hover:bg-red-600"
                 >
                   <X class="w-3 h-3" />
                 </button>
               </div>
             </div>
             
             <!-- 隐藏的文件输入 -->
             <input 
               type="file"
               ref="fileInputRef"
               @change="handleImageSelect"
               accept="image/*"
               multiple
               class="hidden"
             />
             
             <form @submit="handleSubmit" class="relative glass-input rounded-2xl shadow-soft-lg flex items-end p-2.5 transition-all">
                <!-- 图片上传按钮（仅非 Agent 模式） -->
                <Button 
                  v-if="!isAgentMode"
                  type="button"
                  variant="ghost"
                  size="icon"
                  @click="triggerImageUpload"
                  :disabled="uploadedImages.length >= MAX_IMAGES"
                  :class="[
                    'h-10 w-10 mb-1.5 ml-1.5 rounded-xl transition-all flex-shrink-0',
                    uploadedImages.length >= MAX_IMAGES ? 'text-[#A8A29E] cursor-not-allowed' : 'text-[#78716C] hover:text-[#44403C] hover:bg-[#F5F5F4]'
                  ]"
                  title="上传图片（最多3张）"
                >
                  <ImageIcon class="w-5 h-5" />
                </Button>
                
                <textarea 
                  v-model="input"
                  ref="textareaRef"
                  @input="adjustHeight"
                  @keydown.enter.exact.prevent="handleSubmit"
                  :placeholder="uploadedImages.length > 0 ? '描述图片内容或提问...' : '问我任何问题...'" 
                  class="flex-1 border-0 focus:ring-0 shadow-none bg-transparent py-3 px-4 min-h-[56px] max-h-[200px] text-base placeholder:text-[#A8A29E] resize-none text-[#1C1917] outline-none font-medium leading-relaxed"
                  :disabled="false"
                  autocomplete="off"
                  rows="1"
                ></textarea>

                <Button 
                  type="submit" 
                  :disabled="(!input.trim() && uploadedImages.length === 0)"
                  size="icon"
                  :class="[
                    'h-10 w-10 mb-1.5 mr-1.5 rounded-xl transition-all flex-shrink-0 shadow-md duration-200',
                    (!input.trim() && uploadedImages.length === 0) ? 'bg-[#E7E5E4] text-[#A8A29E] cursor-not-allowed shadow-none' : 'bg-[#334155] hover:bg-[#1E293B] text-white hover:shadow-lg hover:shadow-indigo-500/20 transform active:scale-95'
                  ]"
                >
                  <SendIcon class="w-5 h-5" />
                </Button>
             </form>
             <div class="text-center mt-3 text-[10px] text-[#A8A29E] font-bold tracking-[0.2em] opacity-60">
                SAGE INTELLIGENCE
             </div>
          </div>
        </div>
      </div>
    </main>


  </div>
</template>

<style>
/* Toast transition */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>
