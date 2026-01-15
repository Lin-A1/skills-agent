<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { X, Copy, Check } from 'lucide-vue-next'
import { renderMarkdown } from '@/lib/markdown'

const props = defineProps<{
  isOpen: boolean
  content: string
  language?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const copied = ref(false)
const scrollContainer = ref<HTMLDivElement | null>(null)
const shouldAutoScroll = ref(true)

const copyContent = async () => {
    try {
        await navigator.clipboard.writeText(props.content)
        copied.value = true
        setTimeout(() => copied.value = false, 2000)
    } catch (err) {
        console.error('Failed to copy', err)
    }
}

// Watch content change to auto-scroll
watch(() => props.content, async () => {
    if (shouldAutoScroll.value && props.isOpen) {
        await nextTick()
        if (scrollContainer.value) {
            scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
        }
    }
})

// Handle manual scroll to disable/enable auto-scroll
const handleScroll = (e: Event) => {
    const el = e.target as HTMLElement
    const threshold = 50
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
    shouldAutoScroll.value = isAtBottom
}
</script>

<template>
  <div 
    class="fixed inset-y-0 right-0 z-50 w-full md:w-[45vw] bg-background border-l border-border shadow-2xl transform transition-transform duration-300 ease-in-out flex flex-col"
    :class="isOpen ? 'translate-x-0' : 'translate-x-full'"
  >
    <!-- Header -->
    <div class="h-14 border-b border-border flex items-center justify-between px-4 bg-muted/30">
        <div class="flex items-center gap-2">
            <span class="font-semibold text-sm">Canvas</span>
             <span v-if="language" class="text-xs text-muted-foreground px-2 py-0.5 bg-muted rounded-full uppercase">{{ language }}</span>
        </div>
        <div class="flex items-center gap-1">
             <button @click="copyContent" class="p-2 hover:bg-muted rounded-lg text-muted-foreground hover:text-foreground transition-colors" title="Copy Content">
                <Check v-if="copied" class="w-4 h-4 text-green-500" />
                <Copy v-else class="w-4 h-4" />
            </button>
            <button @click="emit('close')" class="p-2 hover:bg-muted rounded-lg text-muted-foreground hover:text-foreground transition-colors">
                <X class="w-4 h-4" />
            </button>
        </div>
    </div>

    <!-- Content -->
    <div ref="scrollContainer" @scroll="handleScroll" class="flex-1 overflow-y-auto p-6 scrollbar-thin">
        <div v-if="content" class="prose prose-slate dark:prose-invert max-w-none">
             <!-- Wrap in code block if we have language and it looks like code, 
                  but rely on renderMarkdown to handle it if it's already markdown.
                  However, if content is raw code, we want to wrap it.
                  Let's check if content starts with ``` or not?
                  Actually, best is to wrap it if language is provided and not 'text' or 'markdown'
             -->
             <div v-if="language && language !== 'text' && language !== 'markdown'" v-html="renderMarkdown('```' + language + '\n' + content + '\n```')"></div>
             <div v-else v-html="renderMarkdown(content)"></div>
        </div>
        <div v-else class="flex flex-col items-center justify-center h-full text-muted-foreground">
            <span class="text-sm">Select code or markdown to view here</span>
        </div>
    </div>
  </div>
</template>
