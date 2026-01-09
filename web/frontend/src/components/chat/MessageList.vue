<script setup lang="ts">
import { ref } from 'vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { 
  Bot, Brain, ChevronDown, Copy, BookOpen, RefreshCcw, 
  CornerUpLeft, Pencil, Timer, Check, Wrench, SendIcon, Plus, ImageIcon, PenLine, Wand2
} from 'lucide-vue-next'
import { renderMarkdown } from '@/lib/markdown'
import AgentPlan from '@/components/AgentPlan.vue'
import type { ChatMessage, UploadedImage, AgentStep } from '@/composables/useChat'

const props = defineProps<{
  messages: ChatMessage[]
  status: string
  isAgentMode: boolean
  uploadedImages: UploadedImage[]
  thinkingSeconds: number
  editingMessageId: string | null
  editingContent: string
  copiedMessageId: string | null
  maxImages: number
  input: string
}>()

const emit = defineEmits<{
  (e: 'update:isAgentMode', value: boolean): void
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

         <!-- Agent Toggle (Prominent) -->
         <div class="flex items-center gap-3 mb-6 bg-background/50 backdrop-blur-sm px-4 py-2 rounded-full border border-border shadow-sm hover:shadow-md transition-all duration-300 cursor-pointer" @click="emit('update:isAgentMode', !isAgentMode)">
             <div class="flex items-center gap-2">
                 <span class="text-xs font-semibold uppercase tracking-wider transition-colors duration-300" :class="isAgentMode ? 'text-primary' : 'text-muted-foreground'">Agent Mode</span>
                 <div class="w-8 h-5 rounded-full relative transition-colors duration-300" :class="isAgentMode ? 'bg-primary' : 'bg-muted'">
                     <div class="absolute top-1 left-1 w-3 h-3 rounded-full bg-background shadow-sm transition-transform duration-300" :class="isAgentMode ? 'translate-x-3' : 'translate-x-0'"></div>
                 </div>
             </div>
             <Bot class="w-4 h-4 transition-colors duration-300" :class="isAgentMode ? 'text-primary' : 'text-muted-foreground'" />
         </div>

         <!-- Center Input Box -->
         <div class="w-full max-w-2xl relative group">
             <!-- Image Previews -->
             <div v-if="uploadedImages.length > 0 && !isAgentMode" class="flex gap-2 mb-4 justify-center">
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
                     <Button v-if="!isAgentMode" type="button" variant="ghost" size="icon" @click="triggerImageUpload" :disabled="uploadedImages.length >= maxImages" class="text-muted-foreground hover:text-foreground hover:bg-muted rounded-full w-10 h-10 flex-shrink-0">
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
                
                <!-- Agent Plan (Always Visible) -->
                <div v-if="msg.agentSteps && msg.agentSteps.some((s: AgentStep) => s.type === 'plan')" class="mb-4 space-y-2">
                    <div v-for="(step, i) in msg.agentSteps.filter((s: AgentStep) => s.type === 'plan')" :key="'plan-'+i">
                         <AgentPlan :plan="step.planData" />
                    </div>
                </div>

                <!-- Agent Process/Thinking Block -->
                <div v-if="msg.agentSteps && msg.agentSteps.some((s: AgentStep) => s.type !== 'plan')" class="mb-4">
                  <details class="group bg-background/50 rounded-xl border border-border open:bg-background open:shadow-sm transition-all" :open="(index === messages.length - 1 && status === 'streaming') || (!msg.content && msg.agentSteps.some((s: AgentStep) => s.type !== 'plan'))">
                      <summary class="flex items-center gap-2 px-3 py-2 cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground select-none list-none rounded-xl">
                          <Brain class="w-3.5 h-3.5 text-indigo-500" />
                          <span>Thinking Process</span>
                          <span class="ml-auto flex items-center gap-2 text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full group-open:hidden">
                              <span v-if="status === 'streaming' && index === messages.length - 1" class="flex items-center gap-1">
                                <Timer class="w-3 h-3" />
                                {{ thinkingSeconds }}s
                              </span>
                              <span>{{ msg.agentSteps.filter((s: AgentStep) => s.type !== 'plan').length }} steps</span>
                          </span>
                          <ChevronDown class="w-3.5 h-3.5 transition-transform duration-200 group-open:rotate-180 text-muted-foreground" />
                      </summary>
                      <div class="px-3 pb-3 space-y-3 pt-1 border-t border-border mx-1 mt-1">
                          <div v-for="(step, i) in msg.agentSteps.filter((s: AgentStep) => s.type !== 'plan')" :key="i" class="text-xs">
                              <!-- Thought -->
                              <div v-if="step.type === 'thought'" class="text-muted-foreground italic border-l-2 border-border pl-3 py-1">
                                  {{ step.content }}
                              </div>
                              <!-- Action -->
                              <div v-else-if="step.type === 'action'" class="bg-muted/30 rounded-lg p-2.5 border border-border text-foreground">
                                  <div class="flex items-center gap-1.5 mb-1.5 text-indigo-600 font-bold">
                                      <Wrench class="w-3 h-3" />
                                      <span>Call: {{ step.toolName }}</span>
                                  </div>
                                  <div class="bg-background rounded border border-border p-2 overflow-x-auto">
                                      <pre class="font-mono text-[10px]">{{ JSON.stringify(step.toolInput, null, 2) }}</pre>
                                  </div>
                              </div>
                              <!-- Observation -->
                              <div v-else-if="step.type === 'observation'" class="bg-emerald-50/50 rounded-lg p-2.5 border border-emerald-100/50 text-foreground">
                                  <div class="flex items-center gap-1.5 mb-1.5 text-emerald-600 font-bold">
                                      <Check class="w-3 h-3" />
                                      <span>Result</span>
                                  </div>
                                  <div class="bg-background/50 rounded border border-emerald-100/50 p-2 overflow-x-auto max-h-40 scrollbar-thin">
                                      <pre class="font-mono text-[10px] whitespace-pre-wrap">{{ step.content }}</pre>
                                  </div>
                              </div>
                              <!-- Error -->
                              <div v-else-if="step.type === 'error'" class="bg-red-50 text-destructive p-2 rounded border border-red-100 font-medium">
                                  Error: {{ step.content }}
                              </div>
                          </div>
                      </div>
                  </details>
                </div>

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
