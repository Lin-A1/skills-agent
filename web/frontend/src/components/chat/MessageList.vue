<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { 
  Brain, ChevronDown, Copy, RefreshCcw, ArrowDown,
  CornerUpLeft, Pencil, Check, SendIcon, Plus, ImageIcon, PenLine, Wand2, X
} from 'lucide-vue-next'
import { renderMarkdown } from '@/lib/markdown'
import AgentStepTimeline from './AgentStepTimeline.vue'

import type { ChatMessage, UploadedImage } from '@/composables/useChat'

const props = defineProps<{
  messages: ChatMessage[]
  status: string

  uploadedImages: UploadedImage[]
  thinkingSeconds: number
  editingMessageId: string | null
  editingContent: string
  copiedMessageId: string | null
  maxImages: number
  input: string
  isAgentMode?: boolean
}>()

const emit = defineEmits<{

  (e: 'removeImage', index: number): void
  (e: 'triggerImageUpload'): void
  (e: 'handleImageSelect', event: Event): void
  (e: 'update:input', value: string): void
  (e: 'submit'): void
  (e: 'update:editingContent', value: string): void
  (e: 'saveEditAndRegenerate'): void
  (e: 'cancelEdit'): void
  (e: 'startEdit', msg: ChatMessage): void
  (e: 'rollbackToMessage', id: string): void
  (e: 'copyMessage', msg: ChatMessage): void
  (e: 'regenerateFromMessage', msg: ChatMessage): void
  (e: 'update:isAgentMode', value: boolean): void
}>()

const scrollContainerRef = ref<InstanceType<typeof ScrollArea> | null>(null)
const bottomRef = ref<HTMLDivElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

// Initial empty state helpers
const triggerImageUpload = () => fileInputRef.value?.click()

// Helpers for visual timeline



onMounted(() => {
  // Attach scroll listener to Radix viewport
  const el = (scrollContainerRef.value as any)?.$el || scrollContainerRef.value
  const viewport = el?.querySelector('[data-radix-scroll-area-viewport]')
  if (viewport) {
    viewport.addEventListener('scroll', handleScroll)
  }
})

onUnmounted(() => {
  const el = (scrollContainerRef.value as any)?.$el || scrollContainerRef.value
  const viewport = el?.querySelector('[data-radix-scroll-area-viewport]')
  if (viewport) {
    viewport.removeEventListener('scroll', handleScroll)
  }
})

const showScrollButton = ref(false)

const handleScroll = (e: Event) => {
  const target = e.target as HTMLElement
  const { scrollTop, scrollHeight, clientHeight } = target
  showScrollButton.value = scrollHeight - scrollTop - clientHeight > 200
  // Emit scroll event if needed by parent, but usually not required for this local button
}

const scrollToBottom = () => {
    if (scrollContainerRef.value) {
        const viewport = scrollContainerRef.value.$el.querySelector('[data-radix-scroll-area-viewport]') as HTMLElement
        if (viewport) {
             viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
        }
    }
}

defineExpose({
  scrollContainerRef,
  bottomRef
})
</script>

<template>
  <ScrollArea ref="scrollContainerRef" class="flex-1">
    <div class="max-w-3xl mx-auto px-6 py-8 w-full pb-40">
      
      <!-- Empty State (New Design) -->
      <div v-if="messages.length === 0" class="flex flex-col items-center justify-center min-h-[70vh] relative z-20 animate-in fade-in zoom-in-95 duration-500">
         
         <!-- Title -->
         <!-- Title with Glow Effect -->
         <div class="relative z-10 text-center mb-12">
            <div class="absolute -inset-10 bg-gradient-to-r from-violet-500/20 via-sky-500/20 to-emerald-500/20 blur-3xl opacity-30 dark:opacity-20 rounded-full pointer-events-none"></div>
            <h2 class="text-4xl font-semibold bg-clip-text text-transparent bg-gradient-to-br from-foreground to-foreground/70 tracking-tight relative">
              How can I help you?
            </h2>
         </div>



         <!-- Center Input Box -->
         <div class="w-full max-w-2xl relative group">
             <!-- Image Previews -->
             <div v-if="uploadedImages.length > 0" class="flex gap-2 mb-4 justify-center">
                <div v-for="(img, index) in uploadedImages" :key="index" class="relative group/img">
                    <img :src="img.base64" class="w-16 h-16 object-cover rounded-xl border border-border shadow-sm" />
                    <button @click="emit('removeImage', index)" class="absolute -top-2 -right-2 w-5 h-5 bg-destructive text-destructive-foreground rounded-full flex items-center justify-center shadow-md hover:bg-destructive/90">
                        <X class="w-3 h-3" />
                    </button>
                </div>
             </div>

             <!-- Copied File Input -->
             <input type="file" ref="fileInputRef" @change="emit('handleImageSelect', $event)" accept="image/*" multiple class="hidden" />

             <div class="relative bg-background rounded-[2rem] shadow-xl shadow-primary/5 border border-border transition-all duration-300 hover:shadow-2xl hover:shadow-primary/10 hover:-translate-y-0.5 focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary/50">
                 <form @submit.prevent="emit('submit')" class="flex items-center p-2 pl-4">
                     <!-- Upload Button -->
                     <Button type="button" variant="ghost" size="icon" @click="triggerImageUpload" :disabled="uploadedImages.length >= maxImages" class="text-muted-foreground hover:text-foreground hover:bg-muted rounded-full w-10 h-10 flex-shrink-0">
                         <Plus class="w-5 h-5" />
                     </Button>

                     <!-- Input -->
                     <textarea
                        autofocus
                        :value="input"
                        @input="emit('update:input', ($event.target as HTMLTextAreaElement).value)"
                        @keydown.enter.exact.prevent="emit('submit')"
                        placeholder="Ask me anything... (Shift+Enter for newline)"
                        rows="1"
                        class="flex-1 bg-transparent border-none focus:ring-0 text-lg px-4 py-3 placeholder:text-muted-foreground text-foreground resize-none overflow-y-auto scrollbar-thin min-h-[56px] max-h-[200px]"
                        :disabled="false"
                        autocomplete="off"
                     ></textarea>

                     <!-- Right Actions -->
                     <div class="flex items-center gap-3 pr-2">
                         <!-- Agent Mode Toggle -->
                         <div 
                           class="flex items-center gap-1.5 cursor-pointer group/toggle p-1.5 rounded-lg hover:bg-muted/50 transition-all select-none"
                           @click="$emit('update:isAgentMode', !isAgentMode)"
                           title="Enable Agent Capabilities (Deep Research, Coding, etc.)"
                         >
                            <div :class="[
                                'w-8 h-4 rounded-full relative transition-colors duration-300 ease-in-out',
                                isAgentMode ? 'bg-primary' : 'bg-muted-foreground/20'
                            ]">
                                <div :class="[
                                    'absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-300 shadow-sm',
                                    isAgentMode ? 'translate-x-4' : 'translate-x-0'
                                ]"></div>
                            </div>
                            <span :class="['text-xs font-semibold tracking-wide transition-colors', isAgentMode ? 'text-primary' : 'text-muted-foreground/70 group-hover/toggle:text-foreground']">Agent Mode</span>
                         </div>

                         <div class="h-6 w-[1px] bg-border mx-1"></div>

                         <Button type="submit" :disabled="!input.trim() && uploadedImages.length === 0" size="icon" :class="['w-9 h-9 rounded-full transition-all duration-200', (!input.trim() && uploadedImages.length === 0) ? 'bg-muted text-muted-foreground' : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-md']">
                             <SendIcon class="w-4 h-4" />
                         </Button>
                     </div>
                 </form>
             </div>
             
             <!-- Footer Hints -->
             <div class="mt-8 flex justify-center gap-4 text-xs text-muted-foreground font-medium">
                 <span class="flex items-center gap-1 hover:text-foreground cursor-pointer transition-colors border border-border px-3 py-1.5 rounded-full bg-background/50"><PenLine class="w-3 h-3" /> Help me write</span>
                 <span class="flex items-center gap-1 hover:text-foreground cursor-pointer transition-colors border border-border px-3 py-1.5 rounded-full bg-background/50"><ImageIcon class="w-3 h-3" /> Analyze images</span>
                 <span class="flex items-center gap-1 hover:text-foreground cursor-pointer transition-colors border border-border px-3 py-1.5 rounded-full bg-background/50"><Wand2 class="w-3 h-3" /> Optimize code</span>
             </div>
         </div>
      </div>

      <!-- Messages -->
      <div v-else class="space-y-8 relative z-10">
        <template v-for="(msg, index) in messages" :key="msg.id">
          <!-- User Message -->
          <div v-if="msg.role === 'user'" class="animate-in fade-in slide-in-from-bottom-4 duration-500 fill-mode-forwards" style="animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);">
            <!-- Edit mode -->
            <div v-if="editingMessageId === msg.id" class="w-full">
              <div class="bg-background border border-border rounded-xl p-4 shadow-sm">
                <textarea
                  :value="editingContent"
                  @input="emit('update:editingContent', ($event.target as HTMLTextAreaElement).value)"
                  class="w-full min-h-[60px] text-[15px] text-foreground bg-transparent resize-none outline-none placeholder:text-muted-foreground font-normal leading-relaxed"
                  @keydown.enter.ctrl="emit('saveEditAndRegenerate')"
                ></textarea>
              </div>
              <div class="flex items-center justify-between mt-3 px-1">
                <p class="text-xs text-muted-foreground flex items-center gap-1.5">
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <circle cx="12" cy="12" r="10" stroke-width="1.5"/>
                    <path d="M12 8v4M12 16h.01" stroke-width="2" stroke-linecap="round"/>
                  </svg>
                  Editing this message will create a new conversation branch.
                </p>
                <div class="flex items-center gap-2">
                  <Button size="sm" variant="outline" @click="emit('cancelEdit')" class="h-8 px-4 text-muted-foreground border-border hover:bg-muted">Cancel</Button>
                  <Button size="sm" @click="emit('saveEditAndRegenerate')" class="h-8 px-4 bg-primary hover:bg-primary/90 text-primary-foreground">Save</Button>
                </div>
              </div>
            </div>
            <!-- Normal mode -->
            <div v-else class="flex justify-end group">
              <div class="flex flex-col items-end gap-1 max-w-[85%]">
                <div class="bg-secondary text-secondary-foreground px-6 py-4 rounded-[1.5rem] rounded-tr-md text-[16px] leading-7 font-normal md:max-w-2xl shadow-none">
                  <!-- Render Images if present -->
                  <div v-if="msg.images && msg.images.length > 0" class="grid grid-cols-2 gap-2 mb-3">
                    <img 
                      v-for="(img, imgIndex) in msg.images" 
                      :key="imgIndex"
                      :src="img" 
                      class="w-full h-auto rounded-xl border border-black/5 dark:border-white/5 object-cover"
                    />
                  </div>
                  {{ msg.content }}
                </div>
                <!-- Edit button -->
                <div class="flex items-center gap-2 pr-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <button 
                    @click="emit('startEdit', msg)"
                    class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-lg transition-all"
                    title="Edit Message"
                  >
                    <Pencil class="w-3.5 h-3.5" />
                  </button>
                  <button 
                    @click="emit('rollbackToMessage', msg.id)"
                    class="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all"
                    title="Rollback and delete"
                  >
                    <CornerUpLeft class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>

           <!-- Assistant Message -->
          <div v-else class="flex gap-4 animate-in fade-in duration-700 slide-in-from-bottom-2 group pl-0 md:pl-0" style="animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);">
            <div class="flex-1 min-w-0 space-y-2">
                
                <!-- Agent Steps Timeline (Handles both steps and text in Agent Mode) -->
                <AgentStepTimeline 
                  v-if="msg.agentSteps && msg.agentSteps.length > 0"
                  :steps="msg.agentSteps"
                  :is-streaming="index === messages.length - 1 && status === 'streaming'"
                />

                <!-- Reasoning Block for Non-Agent Models -->
                <div v-if="msg.reasoning" class="mb-4">
                  <details class="group bg-zinc-50/50 dark:bg-zinc-900/50 rounded-xl border border-black/5 dark:border-white/5 open:bg-transparent transition-all" :open="index === messages.length - 1 && status === 'streaming'">
                      <summary class="flex items-center gap-2 px-3 py-2 cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground select-none list-none rounded-xl">
                          <Brain class="w-3.5 h-3.5 text-zinc-500" />
                          <span>Thinking Process</span>
                          <ChevronDown class="w-3.5 h-3.5 transition-transform duration-200 group-open:rotate-180 text-muted-foreground ml-auto" />
                      </summary>
                      <div class="px-4 pb-4 pt-1">
                          <div class="text-[13px] text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap leading-relaxed border-l-[1.5px] border-zinc-200 dark:border-zinc-800 pl-4 py-1">
                              {{ msg.reasoning }}
                          </div>
                      </div>
                  </details>
                </div>

                <!-- Standard Content Renderer (Only if NO agent steps) -->
                <div v-if="(!msg.agentSteps || msg.agentSteps.length === 0)" class="prose prose-zinc dark:prose-invert max-w-none text-foreground leading-7 font-normal tracking-wide px-1">
                    <div v-if="msg.content" v-html="renderMarkdown(msg.content)"></div>
                    <div v-else-if="status !== 'streaming'" class="text-muted-foreground italic text-sm">
                        
                    </div>
                     <div v-if="!msg.content && (index === messages.length - 1 && status === 'streaming')" class="py-2 flex items-center gap-3">
                       <span class="relative flex h-2.5 w-2.5">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-zinc-500"></span>
                        </span>
                     </div>
                </div>
                
                <!-- Message Actions -->
                <div v-if="msg.content" class="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity px-1">
                  <button 
                    @click="emit('copyMessage', msg)" 
                    class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-md transition-colors"
                    title="Copy"
                  >
                     <Check v-if="copiedMessageId === msg.id" class="w-3.5 h-3.5 text-green-600" />
                     <Copy v-else class="w-3.5 h-3.5" />
                  </button>
                  <button 
                    @click="emit('regenerateFromMessage', messages[index - 1]!)"
                    v-if="index > 0 && messages[index - 1]?.role === 'user'"
                    class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 rounded-md transition-colors"
                    title="Regenerate"
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

    <!-- Scroll to Bottom Button -->
    <Transition name="fade">
      <button 
        v-if="showScrollButton"
        @click="scrollToBottom"
        class="fixed bottom-24 right-8 z-40 p-3 rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl hover:bg-primary/90 transition-all duration-300 hover:-translate-y-1"
        aria-label="Scroll to bottom"
      >
        <ArrowDown class="w-5 h-5" />
      </button>
    </Transition>
  </ScrollArea>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
