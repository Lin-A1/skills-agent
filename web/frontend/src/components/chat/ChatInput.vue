<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Button } from '@/components/ui/button'
import { 
  SendIcon, Square, X, ImageIcon
} from 'lucide-vue-next'
import type { UploadedImage } from '@/composables/useChat'

const props = defineProps<{
  modelValue: string
  uploadedImages: UploadedImage[]
  status: string
  isAgentMode: boolean
  isSidebarCollapsed: boolean
  maxImages: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'submit'): void
  (e: 'stop'): void
  (e: 'upload'): void
  (e: 'removeImage', index: number): void
  (e: 'fileSelected', event: Event): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const adjustHeight = () => {
  const el = textareaRef.value
  if (el) {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }
}

watch(() => props.modelValue, () => {
  nextTick(adjustHeight)
})

const triggerFileSelect = () => {
  fileInputRef.value?.click()
}
</script>

<template>
  <div :class="[
      'p-6 fixed bottom-0 right-0 z-20 pointer-events-none transition-all duration-300 ease-in-out',
      isAgentMode ? 'bg-gradient-to-t from-background via-background/90 to-transparent' : 'bg-gradient-to-t from-background via-background/90 to-transparent',
      isSidebarCollapsed ? 'left-0' : 'left-0 md:left-[280px]'
  ]">
    <div class="max-w-3xl mx-auto pointer-events-auto">
      <!-- Stop Generation Button -->
      <div v-if="status === 'streaming'" class="flex justify-center mb-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
         <Button variant="outline" size="sm" class="bg-background/80 backdrop-blur border-border text-foreground shadow-lg hover:bg-background" @click="emit('stop')">
            <Square class="w-3 h-3 mr-2 fill-current" />
            Stop Generating
         </Button>
      </div>
      
      <div class="relative group">
         <!-- Image Preview -->
         <div v-if="uploadedImages.length > 0 && !isAgentMode" class="flex gap-2 mb-2 px-2">
           <div v-for="(img, index) in uploadedImages" :key="index" class="relative group/img">
             <img 
               :src="img.base64" 
               :alt="img.name"
               class="w-16 h-16 object-cover rounded-lg border border-border shadow-sm"
             />
             <button 
               @click="emit('removeImage', index)"
               class="absolute -top-1.5 -right-1.5 w-5 h-5 bg-destructive text-destructive-foreground rounded-full flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-opacity shadow-md hover:bg-destructive/90"
             >
               <X class="w-3 h-3" />
             </button>
           </div>
         </div>
         
         <!-- Hidden File Input -->
         <input 
           type="file"
           ref="fileInputRef"
           @change="emit('fileSelected', $event)"
           accept="image/*"
           multiple
           class="hidden"
         />
         
         <form @submit.prevent="emit('submit')" class="relative glass-input rounded-2xl shadow-soft-lg flex items-end p-2.5 transition-all">
            <!-- Upload Button (Non-Agent Mode) -->
            <Button 
              v-if="!isAgentMode"
              type="button"
              variant="ghost"
              size="icon"
              @click="triggerFileSelect"
              :disabled="uploadedImages.length >= maxImages"
              :class="[
                'h-10 w-10 mb-1.5 ml-1.5 rounded-xl transition-all flex-shrink-0',
                uploadedImages.length >= maxImages ? 'text-muted-foreground cursor-not-allowed' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              ]"
              title="Upload Image (Max 3)"
            >
              <ImageIcon class="w-5 h-5" />
            </Button>
            
            <textarea 
              :value="modelValue"
              @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
              ref="textareaRef"
              @keydown.enter.exact.prevent="emit('submit')"
              :placeholder="uploadedImages.length > 0 ? 'Describe image...' : 'Ask anything...'" 
              class="flex-1 border-0 focus:ring-0 shadow-none bg-transparent py-3 px-4 min-h-[56px] max-h-[200px] text-base placeholder:text-muted-foreground resize-none overflow-y-auto scrollbar-thin text-foreground outline-none font-medium leading-relaxed"
              :disabled="false"
              autocomplete="off"
              rows="1"
            ></textarea>

            <Button 
              type="submit" 
              :disabled="(!modelValue.trim() && uploadedImages.length === 0)"
              size="icon"
              :class="[
                'h-10 w-10 mb-1.5 mr-1.5 rounded-xl transition-all flex-shrink-0 shadow-md duration-200',
                (!modelValue.trim() && uploadedImages.length === 0) ? 'bg-muted text-muted-foreground cursor-not-allowed shadow-none' : 'bg-primary hover:bg-primary/90 text-primary-foreground hover:shadow-lg hover:shadow-primary/20 transform active:scale-95'
              ]"
            >
              <SendIcon class="w-5 h-5" />
            </Button>
         </form>
         <div class="text-center mt-3 text-[10px] text-muted-foreground font-bold tracking-[0.2em] opacity-60">
            SAGE INTELLIGENCE
         </div>
      </div>
    </div>
  </div>
</template>
