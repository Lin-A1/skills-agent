<script setup lang="ts">
import { ref } from 'vue'
import { 
  Sparkles, Search, CheckCircle2, XCircle, 
  ChevronDown, Code2, Terminal, Loader2
} from 'lucide-vue-next'
import { renderMarkdown } from '@/lib/markdown'

export interface AgentStep {
  type: 'thinking' | 'skill_call' | 'skill_result' | 'code_execute' | 'code_result' | 'error' | 'text'
  content?: string
  skillName?: string
  code?: string
  result?: Record<string, any>
  error?: string
  timestamp?: string
}

const props = defineProps<{
  steps: AgentStep[]
  isStreaming?: boolean
}>()

const expandedSteps = ref<Set<number>>(new Set())

const toggleStep = (index: number) => {
  if (expandedSteps.value.has(index)) {
    expandedSteps.value.delete(index)
  } else {
    expandedSteps.value.add(index)
  }
}

const getStepTitle = (step: AgentStep) => {
  switch (step.type) {
    case 'thinking': return step.content || '分析中...'
    case 'skill_call': return `调用技能: ${step.skillName || '未知'}`
    case 'skill_result': return `${step.skillName || '技能'}执行完成`
    case 'code_execute': return `执行 ${step.skillName || '代码'}`
    case 'code_result': return `${step.skillName || '执行'}结果`
    case 'error': return '执行出错'
    default: return '处理中'
  }
}

const isExpandable = (step: AgentStep) => {
  return step.code || step.result || step.error
}

// Helper to check if we should show the connecting line
const showConnector = (index: number) => {
  if (index >= props.steps.length - 1) return false
  const current = props.steps[index]
  const next = props.steps[index + 1]
  
  if (!current || !next) return false
  
  // Don't connect if current or next is text
  if (current.type === 'text' || next.type === 'text') return false
  return true
}
</script>

<template>
  <div v-if="steps.length > 0" class="mb-4">
    <div class="space-y-4">
      <template v-for="(step, index) in steps" :key="index">
        
        <!-- Text Content Step (Render as Main Message) -->
        <div 
          v-if="step.type === 'text'" 
          class="prose prose-zinc dark:prose-invert max-w-none text-foreground leading-7 font-normal tracking-wide animate-in fade-in duration-500 mb-6 px-1"
        >
          <div v-if="step.content" v-html="renderMarkdown(step.content)"></div>
          <span v-if="isStreaming && index === steps.length - 1" class="inline-block w-1.5 h-4 ml-0.5 bg-current animate-pulse align-middle rounded-full"></span>
        </div>

        <!-- Action Step (Render as Timeline Item) -->
        <div v-else class="relative pl-8 group pb-4">
          <!-- Timeline Line -->
          <div 
            v-if="showConnector(index)"
            class="absolute left-[11px] top-6 h-[calc(100%+8px)] w-[1px] bg-zinc-200 dark:bg-zinc-800"
          ></div>
          
          <!-- Timeline Dot -->
          <div 
            :class="[
              'absolute -left-0 top-1 w-6 h-6 rounded-full flex items-center justify-center z-10 transition-all duration-300',
              'bg-background border border-zinc-200 dark:border-zinc-700 shadow-sm',
              step.type === 'thinking' && !step.result ? 'animate-pulse ring-4 ring-violet-500/20 border-violet-500' : 'group-hover:border-zinc-400 dark:group-hover:border-zinc-500'
            ]"
          >
            <!-- Loading Animation for Active Step -->
            <Loader2 
              v-if="isStreaming && index === steps.length - 1 && step.type !== 'error'"
              class="w-3.5 h-3.5 text-zinc-500 animate-spin"
            />
            <Sparkles v-else-if="step.type === 'thinking'" class="w-3.5 h-3.5 text-violet-500" />
            <Search v-else-if="step.type === 'skill_call'" class="w-3.5 h-3.5 text-sky-500" />
            <Terminal v-else-if="step.type === 'code_execute'" class="w-3.5 h-3.5 text-amber-500" />
            <XCircle v-else-if="step.type === 'error'" class="w-3.5 h-3.5 text-red-500" />
            <CheckCircle2 v-else class="w-3.5 h-3.5 text-emerald-500" />
          </div>
          
          <!-- Step Card (Minimalist) -->
          <div 
            :class="[
              'rounded-lg transition-all duration-200 -mt-1',
              isExpandable(step) ? 'cursor-pointer hover:bg-zinc-50 dark:hover:bg-white/5' : ''
            ]"
            @click="isExpandable(step) && toggleStep(index)"
          >
            <!-- Header Row -->
            <div class="flex items-center gap-3 py-1.5 px-2">
              <!-- Step Title -->
              <span class="text-[13px] text-zinc-600 dark:text-zinc-400 font-medium group-hover:text-foreground transition-colors">
                {{ getStepTitle(step) }}
              </span>
              
              <!-- Skill Badge -->
              <span 
                v-if="step.skillName && step.type !== 'skill_call'" 
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 font-mono"
              >
                {{ step.skillName }}
              </span>
              
              <!-- Expand Arrow -->
              <ChevronDown 
                v-if="isExpandable(step)"
                :class="[
                  'w-3.5 h-3.5 ml-auto text-zinc-400 transition-transform duration-200',
                  expandedSteps.has(index) ? 'rotate-180 text-foreground' : ''
                ]"
              />
            </div>
            
            <!-- Expanded Content -->
            <Transition
              enter-active-class="transition-all duration-200 ease-out"
              leave-active-class="transition-all duration-150 ease-in"
              enter-from-class="opacity-0 max-h-0"
              enter-to-class="opacity-100 max-h-[400px]"
              leave-from-class="opacity-100 max-h-[400px]"
              leave-to-class="opacity-0 max-h-0"
            >
              <div 
                v-if="expandedSteps.has(index)"
                class="overflow-hidden border-t border-border/50"
              >
                <div class="p-3 space-y-3 bg-white/50 dark:bg-slate-900/50 rounded-b-xl">
                  <!-- Code Block -->
                  <div v-if="step.code">
                    <div class="text-xs text-slate-500 dark:text-slate-500 mb-1.5 flex items-center gap-1 font-medium">
                      <Code2 class="w-3.5 h-3.5" />
                      执行代码
                    </div>
                    <pre class="p-3 rounded-lg bg-[#1e1e2e] text-[#cdd6f4] text-xs font-mono leading-relaxed overflow-x-auto max-h-[200px] scrollbar-thin shadow-inner"><code>{{ step.code }}</code></pre>
                  </div>
                  
                  <!-- Result -->
                  <div v-if="step.result">
                    <div 
                      class="text-xs mb-1.5 flex items-center gap-1 font-medium"
                      :class="step.result.success !== false ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'"
                    >
                      <component :is="step.result.success !== false ? CheckCircle2 : XCircle" class="w-3.5 h-3.5" />
                      {{ step.result.success !== false ? '执行成功' : '执行失败' }}
                    </div>
                    <pre class="p-3 rounded-lg bg-[#1e1e2e] text-[#a6adc8] text-xs font-mono leading-relaxed overflow-x-auto max-h-[160px] scrollbar-thin shadow-inner"><code>{{ step.result.stdout || JSON.stringify(step.result, null, 2) }}</code></pre>
                  </div>
                  
                  <!-- Error -->
                  <div v-if="step.error" class="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/50 text-sm text-red-600 dark:text-red-400">
                    {{ step.error }}
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </template>

      <!-- Streaming Loading Indicator (at the very end if still thinking) -->
      <div v-if="isStreaming && (!steps.length || steps[steps.length-1]?.type === 'text') && (steps.length === 0 || steps[steps.length-1]?.content)" class="pl-6 animate-pulse text-slate-400 text-sm flex items-center gap-2">
         <Loader2 class="w-3 h-3 animate-spin" />
         Agent 正在思考...
      </div>
    </div>
  </div>
</template>
