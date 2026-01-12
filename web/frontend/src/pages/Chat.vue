<script setup lang="ts">
import { ref, watch } from 'vue'
import { useChat } from '@/composables/useChat'
import Sidebar from '@/components/chat/Sidebar.vue'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import MessageList from '@/components/chat/MessageList.vue'

// Mobile sidebar state
const sidebarOpen = ref(false)
const toggleSidebar = () => { sidebarOpen.value = !sidebarOpen.value }

// Desktop sidebar collapse state
const isSidebarCollapsed = ref(false)
const toggleSidebarDesktop = () => { isSidebarCollapsed.value = !isSidebarCollapsed.value }

const { 
  messages, input, handleSubmit, status, sessionId, sessions,
  startNewSession, loadSession: internalLoadSession, deleteSession,
  bottomRef, scrollContainerRef,
  copyMessage, copiedMessageId, editingMessageId, editingContent,
  startEdit, cancelEdit, saveEditAndRegenerate, stopGeneration,
  rollbackToMessage, isLoadingSession,
  toastMessage, toastType, regenerateFromMessage,
  searchQuery, showSearch,
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

// Sync refs for auto-scrolling
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
watch(() => messageListRef.value, (newVal) => {
  if (newVal) {
    // We sync the component instance or element for scroll container
    if (newVal.scrollContainerRef) {
      scrollContainerRef.value = newVal.scrollContainerRef
    }
    // We sync the bottom anchor element
    if (newVal.bottomRef) {
      bottomRef.value = newVal.bottomRef
    }
  }
}, { immediate: true })

// Watch for file input ref to sync with composable
watch(fileInputRef, (el) => {
  if (el) {
    // Logic to sync ref if needed, but in this architecture 
    // the ref is inside components. We might need to expose it or trigger click differently.
    // Actually, useChat expects fileInputRef to be a ref to the element.
    // Since we moved the element to sub-components, we need to handle this.
    // The simple way is: pass a handler to components that calls handleImageSelect manually or
    // simply let components handle the click and event.
    // useChat's handleImageSelect expects a ChangeEvent.
  }
})

// Function to handle file selection event from components
const onFileSelected = (event: Event) => {
  handleImageSelect(event)
}

</script>

<template>
  <div :class="['flex h-[100dvh] text-foreground font-sans selection:bg-muted', 'bg-background']">
    <!-- Toast Notification -->
    <Transition name="toast">
      <div v-if="toastMessage" 
        :class="[
          'fixed top-4 right-4 z-[100] px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all',
          toastType === 'error' ? 'bg-destructive text-destructive-foreground' : 'bg-primary text-primary-foreground'
        ]"
      >
        {{ toastMessage }}
      </div>
    </Transition>
    
    <!-- Loading Overlay -->
    <div v-if="isLoadingSession" :class="['fixed inset-0 z-[90] flex items-center justify-center md:ml-[280px]', 'bg-background/50']">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>
    
    <!-- Sidebar -->
    <Sidebar 
      :is-open="sidebarOpen"
      :is-collapsed="isSidebarCollapsed"
      :sessions="sessions"
      :current-session-id="sessionId"
      v-model:search-query="searchQuery"
      :show-search="showSearch"
      @toggle="toggleSidebar"
      @new-session="startNewSession"
      @load-session="loadSession"
      @delete-session="deleteSession"
    />

    <!-- Main -->
    <main :class="[
        'flex-1 flex flex-col min-w-0 relative transition-all duration-300 ease-in-out pt-14',
        isSidebarCollapsed ? 'md:ml-0' : 'md:ml-[280px]',
        'bg-muted/10'
    ]">
      <!-- Background Decor (Hidden on mobile for performance) -->
      <div class="hidden md:block fixed inset-0 pointer-events-none z-0">
          <div class="absolute top-0 right-0 w-[500px] h-[500px] bg-indigo-50/50 rounded-full blur-3xl opacity-60 mix-blend-multiply"></div>
          <div class="absolute bottom-0 left-0 w-[500px] h-[500px] bg-orange-50/50 rounded-full blur-3xl opacity-60 mix-blend-multiply"></div>
      </div>

      <ChatHeader 
        :session-id="sessionId"
        :is-sidebar-collapsed="isSidebarCollapsed"
        :sidebar-open="sidebarOpen"
        @toggle-sidebar="toggleSidebar"
        @toggle-sidebar-desktop="toggleSidebarDesktop"
      />

      <MessageList 
        ref="messageListRef"
        :messages="messages"
        :status="status"
        :uploaded-images="uploadedImages"
        :thinking-seconds="thinkingSeconds"
        :editing-message-id="editingMessageId"
        :editing-content="editingContent"
        :copied-message-id="copiedMessageId"
        :max-images="MAX_IMAGES"
        :input="input"
        @update:input="input = $event"
        @submit="handleSubmit"
        @remove-image="removeImage"
        @trigger-image-upload="triggerImageUpload"
        @handle-image-select="onFileSelected"
        @update:editing-content="editingContent = $event"
        @save-edit-and-regenerate="saveEditAndRegenerate"
        @cancel-edit="cancelEdit"
        @start-edit="startEdit"
        @rollback-to-message="rollbackToMessage"
        @copy-message="copyMessage"
        @regenerate-from-message="regenerateFromMessage"
      />

      <ChatInput 
        v-if="messages.length > 0"
        v-model="input"
        :uploaded-images="uploadedImages"
        :status="status"
        :is-sidebar-collapsed="isSidebarCollapsed"
        :max-images="MAX_IMAGES"
        @submit="handleSubmit"
        @stop="stopGeneration"
        @upload="triggerImageUpload"
        @remove-image="removeImage"
        @file-selected="onFileSelected"
      />
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
