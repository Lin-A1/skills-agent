import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { mermaid } from '@/lib/markdown'

export interface AgentStep {
    type: 'thought' | 'action' | 'observation' | 'error' | 'plan'
    content: string
    toolName?: string
    toolInput?: any
    planData?: any
}

export interface ChatMessage {
    id: string
    role: 'user' | 'assistant'
    content: string
    reasoning?: string
    images?: string[]
    agentSteps?: AgentStep[]
}

export interface SessionInfo {
    id: string
    title: string | null
    created_at: string
    updated_at: string
    message_count: number
}

export interface UploadedImage {
    base64: string
    name: string
}

export const useChat = () => {
    const messages = ref<ChatMessage[]>([])
    const input = ref('')
    const status = ref<'idle' | 'streaming'>('idle')

    // 从 localStorage 恢复 sessionId（刷新页面后保持会话）
    const storedSessionId = localStorage.getItem('agent_session_id')
    const sessionId = ref<string | null>(storedSessionId)

    // 监听 sessionId 变化，同步到 localStorage
    watch(sessionId, (newId) => {
        if (newId) {
            localStorage.setItem('agent_session_id', newId)
        } else {
            localStorage.removeItem('agent_session_id')
        }
    })

    const sessions = ref<SessionInfo[]>([])
    const copiedMessageId = ref<string | null>(null)
    const editingMessageId = ref<string | null>(null)
    const editingContent = ref('')
    const abortController = ref<AbortController | null>(null)
    const textareaRef = ref<HTMLTextAreaElement | null>(null)
    const scrollContainerRef = ref<any>(null)
    const bottomRef = ref<HTMLElement | null>(null)
    const shouldAutoScroll = ref(true)
    const isLoadingSession = ref(false)
    const toastMessage = ref('')
    const toastType = ref<'success' | 'error'>('success')

    const searchQuery = ref('')
    const showSearch = ref(false)

    // Thinking timer state - minimal implementation for UI compatibility
    const thinkingSeconds = ref(0)
    // Timer functions removed as they were agent-specific

    // 图片上传相关
    const uploadedImages = ref<{ base64: string; name: string }[]>([])
    const fileInputRef = ref<HTMLInputElement | null>(null)
    const MAX_IMAGES = 3
    const MAX_IMAGE_SIZE = 5 * 1024 * 1024 // 5MB



    // Show toast notification
    const showToast = (message: string, type: 'success' | 'error' = 'success') => {
        toastMessage.value = message
        toastType.value = type
        setTimeout(() => { toastMessage.value = '' }, 3000)
    }

    const adjustHeight = () => {
        const el = textareaRef.value
        if (el) {
            el.style.height = 'auto'
            el.style.height = `${Math.min(el.scrollHeight, 200)}px`
        }
    }

    // Auto-resize when input changes programmatically (e.g. paste or clear)
    watch(input, () => {
        nextTick(adjustHeight)
    })

    // Scroll to bottom of chat
    const scrollToBottom = () => {
        nextTick(() => {
            if (!shouldAutoScroll.value) return

            if (bottomRef.value) {
                bottomRef.value.scrollIntoView({ behavior: 'instant', block: 'end' })
            }
        })
    }

    // Track if user manually scrolled away from bottom
    const checkScrollPosition = (e: Event) => {
        const viewport = e.target as HTMLElement
        if (!viewport) return

        const { scrollTop, scrollHeight, clientHeight } = viewport
        // Use a 50px threshold to detect if the user is at the bottom
        const threshold = 50
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight

        // If the user is at the bottom, stay in auto-scroll mode
        if (distanceFromBottom <= threshold) {
            shouldAutoScroll.value = true
        } else {
            // User scrolled up, disable auto-scroll
            shouldAutoScroll.value = false
        }
    }

    // ==================== Image Upload Handling ====================

    // Trigger file input click
    const triggerImageUpload = () => {
        fileInputRef.value?.click()
    }

    // Handle file selection
    const handleImageSelect = async (e: Event) => {
        const target = e.target as HTMLInputElement
        if (!target.files?.length) return

        for (const file of Array.from(target.files)) {
            if (uploadedImages.value.length >= MAX_IMAGES) {
                console.warn(`Maximum ${MAX_IMAGES} images allowed`)
                break
            }

            if (file.size > MAX_IMAGE_SIZE) {
                console.warn(`Image ${file.name} exceeds ${MAX_IMAGE_SIZE / 1024 / 1024}MB limit`)
                continue
            }

            if (!file.type.startsWith('image/')) {
                console.warn(`File ${file.name} is not an image`)
                continue
            }

            try {
                const base64 = await fileToBase64(file)
                uploadedImages.value.push({
                    base64,
                    name: file.name
                })
            } catch (err) {
                console.error(`Failed to process ${file.name}:`, err)
            }
        }

        // Clear input for re-upload
        target.value = ''
    }

    // Convert file to base64
    const fileToBase64 = (file: File): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(reader.result as string)
            reader.onerror = reject
            reader.readAsDataURL(file)
        })
    }

    // Remove uploaded image
    const removeImage = (index: number) => {
        uploadedImages.value.splice(index, 1)
    }

    // Clear all images
    const clearImages = () => {
        uploadedImages.value = []
    }

    // Load session list from backend (supports both Chat and Agent modes)
    const loadSessions = async () => {
        try {
            let url = '/api/chat/sessions?page_size=20'
            const response = await fetch(url)
            if (response.ok) {
                const data = await response.json()
                sessions.value = data.sessions || []
            }
        } catch (err) {
            console.error('Failed to load sessions:', err)
        }
    }

    // Load messages from a session
    const loadSession = async (id: string) => {
        // Abort any ongoing streaming before switching
        if (abortController.value) {
            abortController.value.abort()
            abortController.value = null
        }
        status.value = 'idle'
        isLoadingSession.value = true

        try {
            let url = `/api/chat/sessions/${id}/messages`
            const response = await fetch(url)
            if (response.ok) {
                const data = await response.json()
                sessionId.value = id

                // Chat API returns messages in data.messages
                const rawMessages = data.messages || []

                messages.value = rawMessages.map((m: any) => ({
                    id: m.id,
                    role: m.role,
                    content: m.content,
                    reasoning: m.extra_data?.reasoning,
                    images: m.images,
                    createdAt: m.created_at
                }))

                await nextTick()
                scrollToBottom()
                mermaid.run({
                    querySelector: '.language-mermaid'
                })
                // Close mobile sidebar after loading
                return true // Indicate success if needed
            } else {
                // Session not found or other error
                if (response.status === 404) {
                    // Clear invalid session ID from state and localStorage
                    sessionId.value = null
                    showToast('会话不存在,已自动清除', 'error')
                } else {
                    showToast('Failed to load session', 'error')
                }
            }
        } catch (err) {
            console.error('Failed to load session:', err)
            showToast('Network error loading session', 'error')
        } finally {
            isLoadingSession.value = false
        }
        return false
    }

    // Start a new session (clear messages and session_id)
    const startNewSession = () => {
        // Abort any ongoing streaming before starting new session
        if (abortController.value) {
            abortController.value.abort()
            abortController.value = null
        }
        status.value = 'idle'
        messages.value = []
        sessionId.value = null
    }

    // Delete a session (supports both Chat and Agent modes)
    const deleteSession = async (id: string) => {
        try {
            let url = `/api/chat/sessions/${id}`
            const response = await fetch(url, { method: 'DELETE' })
            if (response.ok) {
                sessions.value = sessions.value.filter(s => s.id !== id)
                if (sessionId.value === id) {
                    startNewSession()
                }
            }
        } catch (err) {
            console.error('Failed to delete session:', err)
        }
    }

    // Copy message content
    const copyMessage = async (msg: ChatMessage) => {
        try {
            await navigator.clipboard.writeText(msg.content)
            copiedMessageId.value = msg.id
            setTimeout(() => {
                copiedMessageId.value = null
            }, 2000)
        } catch (err) {
            console.error('Failed to copy:', err)
        }
    }

    // Start editing a user message
    const startEdit = (msg: ChatMessage) => {
        editingMessageId.value = msg.id
        editingContent.value = msg.content
    }

    // Cancel editing
    const cancelEdit = () => {
        editingMessageId.value = null
        editingContent.value = ''
    }

    // Save edit and regenerate from that point
    const saveEditAndRegenerate = async () => {
        if (!editingMessageId.value || !editingContent.value.trim()) return

        const msgIndex = messages.value.findIndex(m => m.id === editingMessageId.value)
        if (msgIndex === -1) return

        const targetMsg = messages.value[msgIndex]
        if (!targetMsg) return

        // 1. Delete this message and all messages after it from backend
        let deleteSuccess = true
        if (sessionId.value && targetMsg.id) {
            // Chat mode: delete one by one
            for (let i = messages.value.length - 1; i >= msgIndex; i--) {
                const msg = messages.value[i]
                if (msg && msg.id) {
                    try {
                        const response = await fetch(`/api/chat/sessions/${sessionId.value}/messages/${msg.id}`, {
                            method: 'DELETE'
                        })
                        if (!response.ok) {
                            deleteSuccess = false
                        }
                    } catch (err) {
                        console.error('Failed to delete message:', err)
                        deleteSuccess = false
                    }
                }
            }
        }

        if (!deleteSuccess) {
            showToast('删除消息失败，请刷新页面重试', 'error')
            cancelEdit()
            return
        }

        // 2. Remove messages locally (including the one being edited)
        messages.value = messages.value.slice(0, msgIndex)

        // 3. Resubmit as new message
        const newContent = editingContent.value
        cancelEdit()

        input.value = newContent
        await handleSubmit()
    }

    // Stop generation
    const stopGeneration = () => {
        if (abortController.value) {
            abortController.value.abort()
            abortController.value = null
            status.value = 'idle'

        }
    }

    // Rollback to before a specific message (delete the message and all after it)
    const rollbackToMessage = async (msgId: string) => {
        const msgIndex = messages.value.findIndex(m => m.id === msgId)
        if (msgIndex === -1) return

        // Delete this message and all messages after it from backend
        if (sessionId.value) {
            // Chat mode: delete one by one (reverse order)
            for (let i = messages.value.length - 1; i >= msgIndex; i--) {
                const msg = messages.value[i]
                if (msg && msg.id) {
                    try {
                        await fetch(`/api/chat/sessions/${sessionId.value}/messages/${msg.id}`, {
                            method: 'DELETE'
                        })
                    } catch (err) {
                        console.error('Failed to delete message:', err)
                    }
                }
            }
        }

        // Remove this message and all after it (locally)
        messages.value = messages.value.slice(0, msgIndex)
        showToast('已回退并删除该消息')
    }

    // Regenerate last assistant response
    const regenerateLastResponse = async () => {
        if (messages.value.length < 2) return

        // Find the last user message
        let lastUserMsgIndex = -1
        for (let i = messages.value.length - 1; i >= 0; i--) {
            const msg = messages.value[i]
            if (msg && msg.role === 'user') {
                lastUserMsgIndex = i
                break
            }
        }

        if (lastUserMsgIndex === -1) return

        // Delete all assistant messages after the last user message from backend
        if (sessionId.value) {
            // Chat mode: delete one by one
            for (let i = messages.value.length - 1; i > lastUserMsgIndex; i--) {
                const msg = messages.value[i]
                if (msg && msg.role === 'assistant' && msg.id) {
                    try {
                        await fetch(`/api/chat/sessions/${sessionId.value}/messages/${msg.id}`, {
                            method: 'DELETE'
                        })
                    } catch (err) {
                        console.error('Failed to delete message:', err)
                    }
                }
            }
        }

        // Remove all messages after the last user message (locally)
        messages.value = messages.value.slice(0, lastUserMsgIndex + 1)

        // Regenerate
        const lastUserMsg = messages.value[lastUserMsgIndex]
        if (lastUserMsg) {
            await regenerateFromMessage(lastUserMsg, true) // true = skip saving user message
        }
    }

    // Regenerate from a specific user message
    const regenerateFromMessage = async (userMsg: ChatMessage, skipSaveUserMessage = false) => {
        status.value = 'streaming'
        abortController.value = new AbortController()

        // 立即创建一个空的 assistant 消息以显示思考动画
        const assistantMsgId = (Date.now() + 1).toString()
        messages.value.push({
            id: assistantMsgId,
            role: 'assistant',
            content: '',
            reasoning: ''
        })

        await nextTick()
        scrollToBottom()

        try {
            const requestBody: Record<string, any> = {
                message: userMsg.content,
                stream: true, // Only stream
                skip_save_user_message: skipSaveUserMessage
            }

            if (sessionId.value) {
                requestBody.session_id = sessionId.value
            }

            // 添加图片
            if (uploadedImages.value.length > 0) {
                requestBody.images = uploadedImages.value.map(img => img.base64)
                clearImages() // 发送后清空图片
            }

            const response = await fetch('/api/chat/completions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
                signal: abortController.value.signal
            })

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}))
                throw new Error(errorData.detail || `HTTP ${response.status}`)
            }

            if (!response.body) throw new Error('No response body')

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let assistantMsg = ''
            let assistantReasoning = ''
            let buffer = ''

            // Track timing for minimum thinking animation
            const startTime = Date.now()

            // Delay showing the first chunk to let animation play for at least 600ms
            const MIN_THINKING_TIME = 600
            let isFirstChunk = true

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })

                const lines = buffer.split('\n')
                buffer = lines.pop() || ''

                for (const line of lines) {
                    const trimmed = line.trim()
                    if (!trimmed || !trimmed.startsWith('data:')) continue

                    const data = trimmed.slice(5).trim()
                    if (data === '[DONE]') continue

                    try {
                        const chunk = JSON.parse(data)

                        if (chunk.session_id && !sessionId.value) {
                            sessionId.value = chunk.session_id
                            // Reload sessions to show the new one
                            loadSessions()
                        }

                        const delta = chunk.choices?.[0]?.delta
                        const content = delta?.content
                        const reasoning = delta?.reasoning_content

                        if (content || reasoning) {

                            if (isFirstChunk) {
                                const elapsed = Date.now() - startTime
                                if (elapsed < MIN_THINKING_TIME) {
                                    await new Promise(resolve => setTimeout(resolve, MIN_THINKING_TIME - elapsed))
                                }
                                isFirstChunk = false
                            }

                            const lastMsg = messages.value[messages.value.length - 1]
                            if (lastMsg && lastMsg.id === assistantMsgId) {
                                if (reasoning) {
                                    assistantReasoning += reasoning
                                    lastMsg.reasoning = assistantReasoning
                                }
                                if (content) {
                                    assistantMsg += content
                                    lastMsg.content = assistantMsg
                                }
                            }
                            // Only auto scroll if user was already at bottom
                            if (shouldAutoScroll.value) {
                                scrollToBottom()
                            }
                        }
                    } catch {
                        // Skip invalid JSON
                    }
                }
            }

        } catch (err) {
            // 查找并更新出错的消息，而不是推入新消息
            const errorMsgIndex = messages.value.findIndex(m => m.id === assistantMsgId)
            if (errorMsgIndex !== -1) {
                const errorMsg = messages.value[errorMsgIndex]
                if ((err as Error).name === 'AbortError') {
                    console.log('Generation stopped by user')
                    showToast('已停止生成', 'success')
                    // 如果内容为空，可能需要删除或显示"已停止"
                    if (errorMsg && !errorMsg.content && !errorMsg.reasoning) {
                        messages.value.splice(errorMsgIndex, 1)
                    }
                } else {
                    console.error('Chat error:', err)
                    showToast(`错误: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
                    if (errorMsg) {
                        errorMsg.content = `Error: ${err instanceof Error ? err.message : 'Unknown error'}`
                    }
                }
            } else {
                // Fallback if message not found
                if ((err as Error).name !== 'AbortError') {
                    showToast(`错误: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
                }
            }
        } finally {
            status.value = 'idle'

            abortController.value = null
            await nextTick()
            mermaid.run({ querySelector: '.language-mermaid' })
        }
    }



    const handleSubmit = async (e?: Event) => {
        e?.preventDefault()
        if (!input.value.trim() && uploadedImages.value.length === 0) return

        // If streaming, stop first
        if (status.value === 'streaming') {
            stopGeneration()
            // Wait a bit for state cleanup
            await nextTick()
        }

        const userMsg = input.value.trim()
        input.value = ''

        // 用户发送消息时，强制启用自动滚动
        shouldAutoScroll.value = true

        if (textareaRef.value) {
            textareaRef.value.style.height = '56px'
        }

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: userMsg,
            images: uploadedImages.value.length > 0 ? uploadedImages.value.map(img => img.base64) : undefined
        }

        messages.value.push(userMessage)

        await regenerateFromMessage(userMessage)
    }

    // Keyboard shortcuts handler
    const handleKeyboardShortcuts = (e: KeyboardEvent) => {
        // Ctrl+N: New conversation
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault()
            startNewSession()
            showToast('已创建新对话', 'success')
        }

        // Ctrl+R: Regenerate last response
        if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
            e.preventDefault()
            if (messages.value.length >= 2) {
                regenerateLastResponse()
            }
        }

        // Ctrl+F: Toggle search
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault()
            showSearch.value = !showSearch.value
            if (!showSearch.value) {
                searchQuery.value = ''
            }
        }

        // Esc: Stop generation or close search
        if (e.key === 'Escape') {
            if (status.value === 'streaming') {
                stopGeneration()
            } else if (showSearch.value) {
                showSearch.value = false
                searchQuery.value = ''
            }
        }
    }

    // Setup scroll listener and code copy handler
    onMounted(() => {
        loadSessions()

        // 如果有保存的 sessionId，恢复会话消息
        if (sessionId.value) {
            loadSession(sessionId.value)
        }

        nextTick(() => {
            // Delegate click listener for code copy buttons
            document.addEventListener('click', async (e) => {
                const target = (e.target as HTMLElement).closest('.copy-code-btn') as HTMLElement
                if (target && target.dataset.code) {
                    try {
                        const code = decodeURIComponent(target.dataset.code)
                        await navigator.clipboard.writeText(code)

                        // Visual feedback
                        const originalHTML = target.innerHTML
                        target.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-green-600"><polyline points="20 6 9 17 4 12"/></svg><span class="text-green-600">已复制</span>`
                        setTimeout(() => {
                            target.innerHTML = originalHTML
                        }, 2000)
                    } catch (err) {
                        console.error('Failed to copy code:', err)
                    }
                }
            })

            // Keyboard shortcuts
            window.addEventListener('keydown', handleKeyboardShortcuts)
        })
    })

    // Cleanup scroll listener and keyboard shortcuts
    onUnmounted(() => {
        if (scrollContainerRef.value) {
            const container = (scrollContainerRef.value as any).$el || scrollContainerRef.value
            const viewport = container.querySelector('[data-radix-scroll-area-viewport]')
            if (viewport) {
                viewport.removeEventListener('scroll', checkScrollPosition as EventListener)
            }
        }
        window.removeEventListener('keydown', handleKeyboardShortcuts)
    })

    // Watch for new messages to scroll
    watch(() => messages.value.length, () => {
        scrollToBottom()
    })



    // Watch for scroll container to bind event
    let currentViewport: HTMLElement | null = null
    watch(scrollContainerRef, (newVal) => {
        if (currentViewport) {
            currentViewport.removeEventListener('scroll', checkScrollPosition as EventListener)
        }

        if (newVal) {
            nextTick(() => {
                const container = newVal.$el || newVal
                const viewport = container.querySelector('[data-radix-scroll-area-viewport]')
                if (viewport) {
                    currentViewport = viewport
                    viewport.addEventListener('scroll', checkScrollPosition as EventListener)
                }
            })
        }
    }, { immediate: true })

    return {
        messages,
        input,
        handleSubmit,
        status,
        sessionId,
        sessions,
        startNewSession,
        loadSession,
        deleteSession,
        adjustHeight,
        textareaRef,
        scrollContainerRef,
        bottomRef,
        copyMessage,
        copiedMessageId,
        editingMessageId,
        editingContent,
        startEdit,
        cancelEdit,
        saveEditAndRegenerate,
        stopGeneration,
        rollbackToMessage,
        regenerateLastResponse,
        isLoadingSession,
        toastMessage,
        toastType,
        showToast,
        regenerateFromMessage,
        searchQuery,
        showSearch,
        // 图片上传相关
        uploadedImages,
        fileInputRef,
        MAX_IMAGES,
        triggerImageUpload,
        handleImageSelect,
        removeImage,
        clearImages,
        // Thinking timer (now exposed if needed by template)
        thinkingSeconds
    }
}
