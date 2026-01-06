<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'

const error = ref<Error | null>(null)
const hasError = ref(false)

// Catch errors from child components
onErrorCaptured((err, _instance, info) => {
  console.error('Error caught by ErrorBoundary:', err, info)
  error.value = err
  hasError.value = true
  
  // Return false to prevent error propagation
  return false
})

const reset = () => {
  error.value = null
  hasError.value = false
  // Force re-mount by emitting event to parent
  window.location.reload()
}
</script>

<template>
  <div v-if="hasError" class="flex items-center justify-center min-h-screen bg-[#FAFAF9] p-6">
    <div class="max-w-md w-full bg-white rounded-2xl shadow-xl border border-black/5 p-8">
      <!-- Icon -->
      <div class="flex justify-center mb-6">
        <div class="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center">
          <AlertTriangle class="w-8 h-8 text-red-500" />
        </div>
      </div>

      <!-- Title -->
      <h2 class="text-2xl font-bold text-[#1C1917] text-center mb-3">
        出错了
      </h2>

      <!-- Description -->
      <p class="text-[#57534E] text-center mb-6 leading-relaxed">
        应用遇到了一个意外错误。别担心，你的数据是安全的。
      </p>

      <!-- Error Details (for development) -->
      <details class="mb-6 bg-[#FAFAF9] rounded-lg p-4 border border-black/5">
        <summary class="text-xs font-mono text-[#78716C] cursor-pointer hover:text-[#1C1917] transition-colors">
          错误详情
        </summary>
        <div class="mt-3 text-xs font-mono text-red-600 break-all">
          {{ error?.message || '未知错误' }}
        </div>
        <div class="mt-2 text-xs font-mono text-[#A8A29E] break-all max-h-40 overflow-auto">
          {{ error?.stack }}
        </div>
      </details>

      <!-- Actions -->
      <div class="space-y-3">
        <button
          @click="reset"
          class="w-full flex items-center justify-center gap-2 px-4 py-3 bg-[#334155] text-white rounded-xl hover:bg-[#1e293b] transition-colors font-medium shadow-sm hover:shadow-md"
        >
          <RefreshCw class="w-4 h-4" />
          重新加载页面
        </button>
        
        <button
          @click="hasError = false"
          class="w-full px-4 py-3 bg-white text-[#57534E] border border-black/10 rounded-xl hover:bg-[#FAFAF9] transition-colors font-medium"
        >
          尝试继续使用
        </button>
      </div>

      <!-- Support Info -->
      <p class="mt-6 text-xs text-center text-[#A8A29E]">
        如果问题持续存在，请联系技术支持
      </p>
    </div>
  </div>

  <!-- Normal content when no error -->
  <slot v-else />
</template>
