<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { 
  Brain, ChevronDown, Copy, BookOpen, RefreshCcw, 
  CornerUpLeft, Pencil, Check, SendIcon, Plus, ImageIcon, PenLine, Wand2, X
} from 'lucide-vue-next'
import { renderMarkdown } from '@/lib/markdown'

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
}>()

const scrollContainerRef = ref<InstanceType<typeof ScrollArea> | null>(null)
const bottomRef = ref<HTMLDivElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

// Initial empty state helpers
const triggerImageUpload = () => fileInputRef.value?.click()

// Helpers for visual timeline


// Code block copy handler
const handleCopyCode = async (e: MouseEvent) => {
  const target = (e.target as HTMLElement).closest('.copy-code-btn')
  if (!target) return
  
  const btn = target as HTMLButtonElement
  const code = decodeURIComponent(btn.getAttribute('data-code') || '')
  if (code) {
    try {
      await navigator.clipboard.writeText(code)
      
      // Visual feedback
      const originalHTML = btn.innerHTML
      btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-green-500"><polyline points="20 6 9 17 4 12"/></svg> Copied!`
      
      setTimeout(() => {
        btn.innerHTML = originalHTML
      }, 2000)
    } catch (err) {
      console.error('Failed to copy', err)
    }
  }
}

onMounted(() => {
  document.addEventListener('click', handleCopyCode)
})

onUnmounted(() => {
  document.removeEventListener('click', handleCopyCode)
})

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
         <h2 class="text-3xl font-medium text-foreground mb-12 tracking-tight">How can I help you?</h2>



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
                     <div class="flex items-center gap-1 pr-1">
                         <Button type="submit" :disabled="!input.trim() && uploadedImages.length === 0" size="icon" :class="['w-10 h-10 rounded-full transition-all duration-200', (!input.trim() && uploadedImages.length === 0) ? 'bg-muted text-muted-foreground' : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-md']">
                             <SendIcon class="w-5 h-5" />
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
                <div class="bg-primary text-primary-foreground px-5 py-3.5 rounded-2xl rounded-br-sm text-[15px] leading-relaxed shadow-lg shadow-primary/10 transition-all hover:shadow-primary/20 hover:-translate-y-0.5 tracking-wide font-light whitespace-pre-wrap">
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
                <!-- Edit button -->
                <div class="flex items-center gap-2">
                  <button 
                    @click="emit('startEdit', msg)"
                    class="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    title="Edit Message"
                  >
                    <Pencil class="w-3 h-3" />
                    <span>Edit</span>
                  </button>
                  <button 
                    @click="emit('rollbackToMessage', msg.id)"
                    class="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    title="Rollback and delete"
                  >
                    <CornerUpLeft class="w-3 h-3" />
                    <span>Rollback</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

           <!-- Assistant Message -->
          <div v-else class="flex gap-5 animate-in fade-in duration-700 slide-in-from-bottom-2 group" style="animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1);">
            <div class="flex-shrink-0 mt-1">
              <div class="w-9 h-9 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/10">
                <BookOpen class="w-4.5 h-4.5 text-primary-foreground" />
              </div>
            </div>
            <div class="flex-1 min-w-0 space-y-2.5">
                <div class="text-[13px] font-bold text-primary ml-1 tracking-wide uppercase opacity-70">Sage</div>
                


                <!-- Reasoning Block for Non-Agent Models -->
                <div v-if="msg.reasoning" class="mb-4">
                  <details class="group bg-background/50 rounded-xl border border-border open:bg-background open:shadow-sm transition-all" :open="index === messages.length - 1 && status === 'streaming'">
                      <summary class="flex items-center gap-2 px-3 py-2 cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground select-none list-none rounded-xl">
                          <Brain class="w-3.5 h-3.5 text-indigo-500" />
                          <span>Deep Thinking</span>
                          <ChevronDown class="w-3.5 h-3.5 transition-transform duration-200 group-open:rotate-180 text-muted-foreground ml-auto" />
                      </summary>
                      <div class="px-3 pb-3 pt-1 border-t border-border mx-1 mt-1">
                          <div class="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed italic border-l-2 border-indigo-100 pl-3">
                              {{ msg.reasoning }}
                          </div>
                      </div>
                  </details>
                </div>

                <div class="prose prose-slate max-w-none text-foreground leading-8 font-normal tracking-normal glass p-5 rounded-2xl rounded-tl-sm shadow-sm border-0">

                    <div v-if="msg.content" v-html="renderMarkdown(msg.content)"></div>
                    <div v-else-if="status !== 'streaming'" class="text-muted-foreground italic">
                        (No response generated)
                    </div>

                     <div v-if="!msg.content && (index === messages.length - 1 && status === 'streaming')" class="py-1 flex items-center gap-3">
                       <div class="relative flex items-center justify-center w-5 h-5">
                         <div class="absolute inset-0 bg-indigo-500/20 rounded-full animate-ping"></div>
                         <div class="relative w-2.5 h-2.5 bg-gradient-to-tr from-indigo-500 to-violet-500 rounded-full animate-spin"></div>
                       </div>
                       <span class="text-sm font-medium text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-violet-500 animate-pulse">Thinking <span v-if="thinkingSeconds > 0">({{ thinkingSeconds }}s)</span>...</span>
                     </div>

                </div>
                
                <!-- Message Actions -->
                <div v-if="msg.content" class="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity pl-1">
                  <button 
                    @click="emit('copyMessage', msg)" 
                    class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
                    title="Copy"
                  >
                     <Check v-if="copiedMessageId === msg.id" class="w-3.5 h-3.5 text-green-600" />
                     <Copy v-else class="w-3.5 h-3.5" />
                  </button>
                  <button 
                    @click="emit('regenerateFromMessage', messages[index - 1]!)"
                    v-if="index > 0 && messages[index - 1]?.role === 'user'"
                    class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
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
  </ScrollArea>
</template>
