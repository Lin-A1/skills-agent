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
  isSidebarCollapsed: boolean
  maxImages: number
  isCanvasOpen?: boolean
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
      'p-6 fixed bottom-0 z-20 pointer-events-none transition-all duration-300 ease-in-out',
      'bg-gradient-to-t from-background via-background/90 to-transparent',
      isSidebarCollapsed ? 'left-0' : 'left-0 md:left-[280px]',
      isCanvasOpen ? 'md:right-[45vw] right-0' : 'right-0'
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
         <div v-if="uploadedImages.length > 0" class="flex gap-2 mb-2 px-2">
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
         
         <form @submit.prevent="emit('submit')" class="relative bg-background rounded-[2rem] shadow-lg shadow-black/5 dark:shadow-black/20 flex items-end p-2 transition-all border border-black/5 dark:border-white/5 ring-4 ring-black/[0.02] dark:ring-white/[0.02]">
            <!-- Upload Button (Non-Agent Mode) -->
            <Button 
              type="button"
              variant="ghost"
              size="icon"
              @click="triggerFileSelect"
              :disabled="uploadedImages.length >= maxImages"
              :class="[
                'h-10 w-10 mb-1 rounded-full transition-all flex-shrink-0',
                uploadedImages.length >= maxImages ? 'text-muted-foreground cursor-not-allowed' : 'text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5'
              ]"
              title="Upload Image (Max 3)"
            >
              <ImageIcon class="w-5 h-5" />
            </Button>
            
            <textarea 
              :value="modelValue"
              @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
              ref="textareaRef"
              @keydown.enter.exact.prevent="status !== 'streaming' && emit('submit')"
              :placeholder="uploadedImages.length > 0 ? 'Describe image...' : 'Message Sage...'" 
              class="flex-1 border-0 focus:ring-0 shadow-none bg-transparent py-3.5 px-4 min-h-[56px] max-h-[200px] text-[15px] placeholder:text-muted-foreground/50 resize-none overflow-y-auto scrollbar-thin text-foreground outline-none font-normal leading-relaxed"
              :disabled="false"
              autocomplete="off"
              rows="1"
            ></textarea>

            <Button 
              type="submit" 
              :disabled="status === 'streaming' || (!modelValue.trim() && uploadedImages.length === 0)"
              size="icon"
              :class="[
                'h-10 w-10 mb-1 mr-1 rounded-full transition-all flex-shrink-0 duration-200 transform',
                (!modelValue.trim() && uploadedImages.length === 0) 
                  ? 'bg-transparent text-muted-foreground scale-90 opacity-50 cursor-not-allowed' 
                  : 'bg-primary text-primary-foreground shadow-md hover:shadow-lg hover:scale-110 active:scale-95'
              ]"
            >
              <SendIcon class="w-4 h-4" />
            </Button>
         </form>
         <div class="text-center mt-3 text-[10px] text-muted-foreground/40 font-medium tracking-widest uppercase">
            Sage Intelligence
         </div>
      </div>
    </div>
  </div>
</template>
