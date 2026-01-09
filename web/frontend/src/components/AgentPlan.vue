<script setup lang="ts">
import { ref } from 'vue'
import { 
  ClipboardList, 
  ChevronDown, 
  Circle, 
  CheckCircle2, 
  Loader2, 
  XCircle, 
  MinusCircle
} from 'lucide-vue-next'

defineProps<{
  plan: {
    goal: string
    approach: string
    steps: Array<{
      id: string
      description: string
      tool_hint?: string
      status: 'pending' | 'in_progress' | 'done' | 'failed' | 'skipped'
    }>
    estimated_iterations?: number
  }
}>()

const isOpen = ref(true)

const stepStatusIcon = (status: string) => {
  switch (status) {
    case 'done': return CheckCircle2
    case 'in_progress': return Loader2
    case 'failed': return XCircle
    case 'skipped': return MinusCircle
    default: return Circle
  }
}

const stepStatusColor = (status: string) => {
  switch (status) {
    case 'done': return 'text-emerald-500'
    case 'in_progress': return 'text-indigo-500'
    case 'failed': return 'text-red-500'
    case 'skipped': return 'text-gray-400'
    default: return 'text-gray-300'
  }
}
</script>

<template>
  <div class="bg-white/80 rounded-xl border border-indigo-100 shadow-sm overflow-hidden transition-all duration-300 hover:shadow-md">
    <!-- Header -->
    <div 
      @click="isOpen = !isOpen"
      class="flex items-center gap-2 px-4 py-3 bg-indigo-50/50 cursor-pointer select-none border-b border-indigo-100/50"
    >
      <ClipboardList class="w-4 h-4 text-indigo-600" />
      <span class="text-sm font-semibold text-indigo-900">执行计划</span>
      
      <div class="ml-auto flex items-center gap-2">
        <span class="text-xs text-indigo-400 font-medium px-2 py-0.5 bg-white/50 rounded-full border border-indigo-100">
          {{ plan.steps?.length || 0 }} 步骤
        </span>
        <ChevronDown 
          class="w-4 h-4 text-indigo-400 transition-transform duration-200"
          :class="{ 'rotate-180': !isOpen }"
        />
      </div>
    </div>

    <!-- Body -->
    <div v-show="isOpen" class="p-4 space-y-4">
      <!-- Goal & Approach -->
      <div class="space-y-2">
        <div class="text-sm text-gray-800 font-medium leading-relaxed">
          <span class="text-indigo-600 font-bold mr-1">目标:</span>
          {{ plan.goal }}
        </div>
        <div v-if="plan.approach" class="text-xs text-gray-500 bg-gray-50 p-2 rounded-lg border border-gray-100">
          <span class="font-semibold text-gray-700 mr-1">思路:</span>
          {{ plan.approach }}
        </div>
      </div>

      <!-- Steps List -->
      <div class="space-y-2 relative">
        <!-- Connecting Line -->
        <div class="absolute left-[0.95rem] top-3 bottom-3 w-px bg-gray-100 -z-10"></div>

        <div 
          v-for="step in (plan.steps || [])" 
          :key="step.id"
          class="flex items-start gap-3 group"
        >
          <!-- Icon -->
          <div class="mt-0.5 relative bg-white p-0.5 rounded-full">
            <component 
              :is="stepStatusIcon(step.status)" 
              class="w-4 h-4 transition-colors duration-300"
              :class="[
                stepStatusColor(step.status),
                step.status === 'in_progress' ? 'animate-spin' : ''
              ]"
            />
          </div>

          <!-- Content -->
          <div class="flex-1 min-w-0">
            <div 
              class="text-sm leading-tight transition-colors duration-200"
              :class="[
                step.status === 'done' ? 'text-gray-500 line-through decoration-gray-300' : 'text-gray-700',
                step.status === 'in_progress' ? 'font-medium text-indigo-700' : ''
              ]"
            >
              {{ step.description }}
            </div>
            
            <!-- Tool Hint -->
            <div v-if="step.tool_hint" class="flex items-center gap-1 mt-1">
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 border border-gray-200 font-mono">
                {{ step.tool_hint }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
