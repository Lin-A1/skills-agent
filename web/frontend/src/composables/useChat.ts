import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { mermaid } from '@/lib/markdown'

export interface AgentStep {
    type: 'thought' | 'action' | 'observation' | 'error'
    content: string
    toolName?: string
    toolInput?: any
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

export const useChat = () => {
    const messages = ref<ChatMessage[]>([])
    const input = ref('')
    const status = ref<'idle' | 'streaming'>('idle')
    const sessionId = ref<string | null>(null)
    const sessions = ref<SessionInfo[]>([])
    const copiedMessageId = ref<string | null>(null)
    const editingMessageId = ref<string | null>(null)
    const editingContent = ref('')
    const abortController = ref<AbortController | null>(null)
    const textareaRef = ref<HTMLTextAreaElement | null>(null)
    const scrollContainerRef = ref<HTMLElement | null>(null)
    const bottomRef = ref<HTMLElement | null>(null)
    const shouldAutoScroll = ref(true)
    const isLoadingSession = ref(false)
    const toastMessage = ref('')
    const toastType = ref<'success' | 'error'>('success')
    const isAgentMode = ref(false)
    const showKnowledgePanel = ref(false)
    const knowledgeSpace = ref<any>(null)
    const isLoadingKnowledge = ref(false)
    const searchQuery = ref('')
    const showSearch = ref(false)

    // Thinking timer state
    const thinkingSeconds = ref(0)
    let thinkingTimer: number | null = null

    const startThinkingTimer = () => {
        stopThinkingTimer()
        thinkingSeconds.value = 0
        thinkingTimer = window.setInterval(() => {
            thinkingSeconds.value++
        }, 1000)
    }

    const stopThinkingTimer = () => {
        if (thinkingTimer) {
            clearInterval(thinkingTimer)
            thinkingTimer = null
        }
        thinkingSeconds.value = 0
    }

    // 图片上传相关
    const uploadedImages = ref<{ base64: string; name: string }[]>([])
    const fileInputRef = ref<HTMLInputElement | null>(null)
    const MAX_IMAGES = 3
    const MAX_IMAGE_SIZE = 5 * 1024 * 1024 // 5MB

    // Load knowledge space - DISABLED (API removed)
    const loadKnowledgeSpace = async () => {
        // Knowledge space API has been removed
        // This function is kept for backwards compatibility
        knowledgeSpace.value = null
    }

    // Add user fact - DISABLED (API removed)
    const addFact = async (_content: string, _category: string) => {
        // Knowledge space API has been removed
        showToast('此功能已禁用', 'error')
    }

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
        const threshold = 150
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight

        // User is near bottom - enable auto-scroll
        if (distanceFromBottom < threshold) {
            shouldAutoScroll.value = true
        } else {
            // User scrolled away from bottom - disable auto-scroll
            shouldAutoScroll.value = false
        }
    }

    // ==================== Image Upload Handling ====================

    // Trigger file input click
    const triggerImageUpload = () => {
        if (isAgentMode.value) return // Agent mode doesn't support images
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
            if (isAgentMode.value) {
                url = '/api/agent/sessions?user_id=anonymous&limit=20'
            }
            const response = await fetch(url)
            if (response.ok) {
                const data = await response.json()
                sessions.value = data.sessions || []
            }
        } catch (err) {
            console.error('Failed to load sessions:', err)
        }
    }

    // Load messages from a session (supports both Chat and Agent modes)
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
            if (isAgentMode.value) {
                url = `/api/agent/sessions/${id}?user_id=anonymous`
            }
            const response = await fetch(url)
            if (response.ok) {
                const data = await response.json()
                sessionId.value = id

                // Agent API returns messages directly in data.messages
                // Chat API returns messages in data.messages too
                const rawMessages = data.messages || []

                if (isAgentMode.value) {
                    // For Agent mode, reconstruct messages with agentSteps
                    const reconstructedMessages: ChatMessage[] = []
                    let currentSteps: AgentStep[] = []

                    for (const m of rawMessages) {
                        if (m.role === 'user') {
                            // User message - push directly
                            reconstructedMessages.push({
                                id: m.id,
                                role: 'user',
                                content: m.content,
                                createdAt: m.created_at
                            } as ChatMessage)
                            currentSteps = [] // Reset steps for new conversation turn
                        } else if (m.role === 'tool') {
                            // Tool message - convert to agent step
                            const toolResult = m.tool_result || {}
                            if (m.content?.includes('[思考]')) {
                                // This is actually a thought stored as tool message
                                currentSteps.push({
                                    type: 'thought',
                                    content: m.content.replace('[思考] ', '')
                                })
                            } else if (m.content?.includes('[调用工具:')) {
                                // Action
                                currentSteps.push({
                                    type: 'action',
                                    content: '',
                                    toolName: m.tool_name || 'Unknown',
                                    toolInput: toolResult.action || {}
                                })
                            } else if (m.content?.includes('[工具结果:')) {
                                // Observation
                                currentSteps.push({
                                    type: 'observation',
                                    content: JSON.stringify(toolResult, null, 2)
                                })
                            }
                        } else if (m.role === 'assistant') {
                            // Check if this is a thought message
                            if (m.content?.startsWith('[思考]')) {
                                currentSteps.push({
                                    type: 'thought',
                                    content: m.content.replace('[思考] ', '')
                                })
                            } else {
                                // Final answer - attach accumulated steps
                                reconstructedMessages.push({
                                    id: m.id,
                                    role: 'assistant',
                                    content: m.content,
                                    agentSteps: currentSteps.length > 0 ? [...currentSteps] : undefined,
                                    createdAt: m.created_at
                                } as ChatMessage)
                                currentSteps = [] // Reset for next turn
                            }
                        }
                    }

                    // If there are remaining steps (e.g. interrupted session without final answer), add a placeholder message
                    if (currentSteps.length > 0) {
                        reconstructedMessages.push({
                            id: 'interrupted-' + Date.now(),
                            role: 'assistant',
                            content: '', // Empty content will trigger "(No response generated)" logic in UI
                            agentSteps: [...currentSteps],
                            createdAt: new Date().toISOString()
                        } as ChatMessage)
                    }

                    // Treat explicit "(No response generated)" content as empty to show placeholder style
                    reconstructedMessages.forEach(msg => {
                        if (msg.role === 'assistant' && msg.content === '(No response generated)') {
                            msg.content = ''
                        }
                    })

                    messages.value = reconstructedMessages
                } else {
                    // Chat mode - simple mapping
                    messages.value = rawMessages.map((m: any) => ({
                        id: m.id,
                        role: m.role,
                        content: m.content,
                        reasoning: m.extra_data?.reasoning,
                        createdAt: m.created_at
                    }))
                }

                await nextTick()
                scrollToBottom()
                mermaid.run({
                    querySelector: '.language-mermaid'
                })
                // Close mobile sidebar after loading
                return true // Indicate success if needed
            } else {
                showToast('Failed to load session', 'error')
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
            if (isAgentMode.value) {
                url = `/api/agent/sessions/${id}`
            }
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
        if (sessionId.value && targetMsg.id) {
            if (isAgentMode.value) {
                try {
                    await fetch(`/api/agent/sessions/${sessionId.value}/messages/${targetMsg.id}?include_following=true`, {
                        method: 'DELETE'
                    })
                } catch (err) {
                    console.error('Failed to delete messages in agent mode:', err)
                }
            } else {
                // Chat mode: delete one by one
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
            stopThinkingTimer()
        }
    }

    // Rollback to before a specific message (delete the message and all after it)
    const rollbackToMessage = async (msgId: string) => {
        const msgIndex = messages.value.findIndex(m => m.id === msgId)
        if (msgIndex === -1) return

        // Delete this message and all messages after it from backend
        if (sessionId.value) {
            if (isAgentMode.value) {
                // Agent mode: single cascading delete
                try {
                    await fetch(`/api/agent/sessions/${sessionId.value}/messages/${msgId}?include_following=true`, {
                        method: 'DELETE'
                    })
                } catch (err) {
                    console.error('Failed to delete messages in agent mode:', err)
                }
            } else {
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
            if (isAgentMode.value) {
                // Agent mode: delete starting from the first message to be removed
                // We find the first message after lastUserMsgIndex
                const firstMsgToDelete = messages.value[lastUserMsgIndex + 1]
                if (firstMsgToDelete && firstMsgToDelete.id) {
                    try {
                        await fetch(`/api/agent/sessions/${sessionId.value}/messages/${firstMsgToDelete.id}?include_following=true`, {
                            method: 'DELETE'
                        })
                    } catch (err) {
                        console.error('Failed to delete messages in agent mode:', err)
                    }
                }
            } else {
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
        if (isAgentMode.value) {
            await streamAgentRun(userMsg)
            return
        }

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
                stream: true,
                skip_save_user_message: skipSaveUserMessage
            }

            if (sessionId.value) {
                requestBody.session_id = sessionId.value
            }

            // 添加图片（仅非 Agent 模式）
            if (!isAgentMode.value && uploadedImages.value.length > 0) {
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
                        errorMsg.agentSteps = [{
                            type: 'error',
                            content: err instanceof Error ? err.message : 'Unknown error'
                        }]
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
            stopThinkingTimer()
            abortController.value = null
            await nextTick()
            mermaid.run({ querySelector: '.language-mermaid' })
            // Attempt to refresh knowledge space after run
            if (knowledgeSpace.value) {
                loadKnowledgeSpace()
            }
        }
    }

    // Stream output from Agent API
    const streamAgentRun = async (userMsg: ChatMessage) => {
        status.value = 'streaming'
        startThinkingTimer()
        abortController.value = new AbortController()

        // 立即创建一个空的 assistant 消息以显示思考动画
        const assistantMsgId = (Date.now() + 1).toString()
        messages.value.push({
            id: assistantMsgId,
            role: 'assistant',
            content: '',
            agentSteps: []
        })

        await nextTick()
        scrollToBottom()

        try {
            const requestBody: Record<string, any> = {
                message: userMsg.content,
                stream: true,
                max_iterations: 10
            }

            if (sessionId.value) {
                requestBody.session_id = sessionId.value
            }

            const response = await fetch('/api/agent/run', {
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

            let fullContent = '' // We build the final answer here
            let buffer = ''

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() || ''

                for (const line of lines) {
                    const trimmed = line.trim()
                    if (!trimmed || !trimmed.startsWith('data:')) continue

                    const dataStr = trimmed.slice(5).trim()
                    if (dataStr === '[DONE]') continue

                    try {
                        const event = JSON.parse(dataStr)
                        // event format: { type: "thought"|"action"|"observation"|"final_answer"|"error", data: ... }

                        const type = event.type
                        const data = event.data

                        const lastMsg = messages.value[messages.value.length - 1]
                        if (lastMsg && lastMsg.id === assistantMsgId) {
                            if (!lastMsg.agentSteps) lastMsg.agentSteps = []

                            // Capture session_id if present in any event (e.g. intent)
                            if (data && data.session_id && !sessionId.value) {
                                sessionId.value = data.session_id
                                // Reload sessions to update list
                                loadSessions()
                            }

                            if (type === 'thought') {
                                lastMsg.agentSteps.push({
                                    type: 'thought',
                                    content: data
                                })
                            } else if (type === 'action') {
                                // data is usually { name: "tool", input: "..." }
                                const toolName = data.name || data.tool || 'Unknown Tool'
                                const toolInput = data.arguments || data.input || data

                                lastMsg.agentSteps.push({
                                    type: 'action',
                                    content: '', // Tool action doesn't have text content usually, essentially structured
                                    toolName,
                                    toolInput
                                })
                            } else if (type === 'observation') {
                                let obsData = data
                                // Try to unwrap
                                if (typeof data === 'object' && data !== null) {
                                    if (data.output) obsData = data.output
                                    else if (data.result) obsData = data.result
                                }

                                const obsStr = typeof obsData === 'string' ? obsData : JSON.stringify(obsData, null, 2)

                                lastMsg.agentSteps.push({
                                    type: 'observation',
                                    content: obsStr
                                })

                            } else if (type === 'final_answer') {
                                // This is the actual text to show as the final answer
                                if (lastMsg.content === '') {
                                    // First chunk
                                    fullContent = data
                                } else {
                                    fullContent += data // Append
                                }
                                lastMsg.content = fullContent
                            } else if (type === 'error') {
                                lastMsg.agentSteps.push({
                                    type: 'error',
                                    content: data
                                })
                            }

                            if (shouldAutoScroll.value) {
                                scrollToBottom()
                            }

                        }

                    } catch (e) {
                        console.warn("Error parsing SSE event:", e)
                    }
                }
            }
        } catch (err) {
            if ((err as Error).name === 'AbortError') {
                showToast('Agent 任务已停止', 'success')
            } else {
                console.error('Agent error:', err)
                showToast(`Agent Error: ${err instanceof Error ? err.message : 'Unknown'}`, 'error')
                messages.value.push({
                    id: Date.now().toString(),
                    role: 'assistant',
                    content: `\n\n**System Error**: ${err instanceof Error ? err.message : 'Unknown error'}`
                })
            }
        } finally {
            status.value = 'idle'
            abortController.value = null
            await nextTick()
            mermaid.run({ querySelector: '.language-mermaid' })
            // Attempt to refresh knowledge space after run
            if (knowledgeSpace.value) {
                loadKnowledgeSpace()
            }
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

        nextTick(() => {
            // Bind scroll event to ScrollArea viewport
            if (scrollContainerRef.value) {
                const container = (scrollContainerRef.value as any).$el || scrollContainerRef.value
                const viewport = container.querySelector('[data-radix-scroll-area-viewport]')
                if (viewport) {
                    viewport.addEventListener('scroll', checkScrollPosition)
                }
            }

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

    // Watch for agent mode changes to reload sessions
    watch(isAgentMode, () => {
        // When mode changes, clear current session and reload session list
        startNewSession()
        loadSessions()
    })

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
        isAgentMode,
        showKnowledgePanel,
        knowledgeSpace,
        isLoadingKnowledge,
        searchQuery,
        showSearch,
        loadKnowledgeSpace,
        addFact,
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
