import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { mermaid } from '@/lib/markdown'

export interface AgentStep {
    type: 'thinking' | 'skill_call' | 'skill_result' | 'code_execute' | 'code_result' | 'error' | 'text'
    content?: string
    skillName?: string
    code?: string
    result?: Record<string, any>
    error?: string
    timestamp?: string
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
    mode: 'chat' | 'agent'
}

export interface UploadedImage {
    base64: string
    name: string
}

export const useChat = () => {
    const messages = ref<ChatMessage[]>([])
    const input = ref('')

    // Agent 模式状态
    const storedAgentMode = localStorage.getItem('is_agent_mode') === 'true'
    const isAgentMode = ref(storedAgentMode)

    // 监听 Agent 模式变化，同步到 localStorage
    watch(isAgentMode, (newVal) => {
        localStorage.setItem('is_agent_mode', String(newVal))
    })

    // toggleAgentMode will be defined after loadSessions
    let toggleAgentMode: () => void

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

    // Canvas state
    const isCanvasOpen = ref(false)
    const canvasContent = ref('')
    const canvasLanguage = ref('')
    const userManuallyClosedCanvas = ref(false)

    const openCanvas = (content: string, language: string) => {
        canvasContent.value = content
        canvasLanguage.value = language
        isCanvasOpen.value = true
        userManuallyClosedCanvas.value = false
    }

    const closeCanvas = () => {
        isCanvasOpen.value = false
        userManuallyClosedCanvas.value = true
    }

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
            const [chatRes, agentRes] = await Promise.allSettled([
                fetch('/api/chat/sessions?page_size=20'),
                fetch('/api/agent/sessions?page_size=20')
            ])

            let allSessions: SessionInfo[] = []

            if (chatRes.status === 'fulfilled' && chatRes.value.ok) {
                const data = await chatRes.value.json()
                const chats = data.sessions || []
                allSessions = allSessions.concat(chats.map((s: any) => ({ ...s, mode: 'chat' })))
            }

            if (agentRes.status === 'fulfilled' && agentRes.value.ok) {
                const data = await agentRes.value.json()
                const agents = data.sessions || []
                allSessions = allSessions.concat(agents.map((s: any) => ({ ...s, mode: 'agent' })))
            }

            // Sort by updated_at desc
            sessions.value = allSessions.sort((a, b) =>
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            )
        } catch (err) {
            console.error('Failed to load sessions:', err)
        }
    }

    // Define toggleAgentMode now that loadSessions is available
    toggleAgentMode = () => {
        // Toggle user preference for NEW chats
        if (!sessionId.value) {
            isAgentMode.value = !isAgentMode.value
        }
    }

    // Load messages from a session
    const loadSession = async (id: string, modeOverride?: 'chat' | 'agent') => {
        // Find session mode from list if not provided
        if (!modeOverride) {
            const session = sessions.value.find(s => s.id === id)
            if (session) {
                isAgentMode.value = (session.mode === 'agent')
            }
        } else {
            isAgentMode.value = (modeOverride === 'agent')
        }

        // Abort any ongoing streaming before switching
        if (abortController.value) {
            abortController.value.abort()
            abortController.value = null
        }
        status.value = 'idle'
        isLoadingSession.value = true

        try {
            const baseUrl = isAgentMode.value ? '/api/agent' : '/api/chat'
            const url = `${baseUrl}/sessions/${id}/messages`
            const response = await fetch(url)
            if (response.ok) {
                const data = await response.json()
                sessionId.value = id

                // API returns messages in data.messages
                const rawMessages = data.messages || []

                messages.value = rawMessages.map((m: any) => ({
                    id: m.id,
                    role: m.role,
                    content: m.content,
                    reasoning: m.extra_data?.reasoning,
                    images: m.images,
                    // Agent messages may have agent step data in extra_data
                    agentSteps: m.extra_data?.agentSteps,
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
        // Note: We do NOT reset isAgentMode here. It reflects the mode for the Next message.
    }

    // Delete a session (supports both Chat and Agent modes)
    const deleteSession = async (id: string) => {
        try {
            const baseUrl = isAgentMode.value ? '/api/agent' : '/api/chat'
            const url = `${baseUrl}/sessions/${id}`
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
            // Chat/Agent mode: delete one by one
            const baseUrl = isAgentMode.value ? '/api/agent' : '/api/chat'
            for (let i = messages.value.length - 1; i >= msgIndex; i--) {
                const msg = messages.value[i]
                if (msg && msg.id) {
                    try {
                        const response = await fetch(`${baseUrl}/sessions/${sessionId.value}/messages/${msg.id}`, {
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
            // Chat/Agent mode: delete one by one (reverse order)
            const baseUrl = isAgentMode.value ? '/api/agent' : '/api/chat'
            for (let i = messages.value.length - 1; i >= msgIndex; i--) {
                const msg = messages.value[i]
                if (msg && msg.id) {
                    try {
                        await fetch(`${baseUrl}/sessions/${sessionId.value}/messages/${msg.id}`, {
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
            // Chat/Agent mode: delete one by one
            const baseUrl = isAgentMode.value ? '/api/agent' : '/api/chat'
            for (let i = messages.value.length - 1; i > lastUserMsgIndex; i--) {
                const msg = messages.value[i]
                if (msg && msg.role === 'assistant' && msg.id) {
                    try {
                        await fetch(`${baseUrl}/sessions/${sessionId.value}/messages/${msg.id}`, {
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
        // Find the index of this user message
        const userMsgIndex = messages.value.findIndex(m => m.id === userMsg.id)
        if (userMsgIndex !== -1) {
            // Delete all messages after this user message (backend cleanup if needed)
            // Delete all messages after this user message (backend cleanup if needed)
            if (sessionId.value) {
                const baseUrl = isAgentMode.value ? '/api/agent' : '/api/chat'
                const deletePromises = []
                for (let i = messages.value.length - 1; i > userMsgIndex; i--) {
                    const msg = messages.value[i]
                    if (msg && msg.id) {
                        // Wait for deletion to avoid context pollution
                        deletePromises.push(
                            fetch(`${baseUrl}/sessions/${sessionId.value}/messages/${msg.id}`, {
                                method: 'DELETE'
                            }).catch(err => console.error('Failed to delete message during regen:', err))
                        )
                    }
                }
                if (deletePromises.length > 0) {
                    await Promise.all(deletePromises)
                }
            }
            // Retain messages only up to the user message
            messages.value = messages.value.slice(0, userMsgIndex + 1)
        }

        status.value = 'streaming'
        abortController.value = new AbortController()

        // Reset manual close state for new generation interaction
        userManuallyClosedCanvas.value = false

        // 立即创建一个空的 assistant 消息以显示思考动画
        const assistantMsgId = (Date.now() + 1).toString()
        messages.value.push({
            id: assistantMsgId,
            role: 'assistant',
            content: '',
            reasoning: '',
            agentSteps: isAgentMode.value ? [] : undefined
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

            // 根据模式选择不同的API端点
            const apiEndpoint = isAgentMode.value ? '/api/agent/completions' : '/api/chat/completions'

            const response = await fetch(apiEndpoint, {
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

                        // 处理 Agent 事件
                        if (isAgentMode.value && chunk.event_type) {
                            const lastMsg = messages.value[messages.value.length - 1]
                            if (lastMsg && lastMsg.id === assistantMsgId) {
                                if (!lastMsg.agentSteps) {
                                    lastMsg.agentSteps = []
                                }

                                const eventType = chunk.event_type as string

                                if (eventType === 'thinking') {
                                    // 添加或更新思考步骤
                                    const existingThinking = lastMsg.agentSteps.find(
                                        s => s.type === 'thinking' && !s.content
                                    )
                                    if (existingThinking) {
                                        existingThinking.content = chunk.content
                                    } else {
                                        lastMsg.agentSteps.push({
                                            type: 'thinking',
                                            content: chunk.content,
                                            timestamp: chunk.timestamp
                                        })
                                    }
                                } else if (eventType === 'skill_call') {
                                    lastMsg.agentSteps.push({
                                        type: 'skill_call',
                                        content: chunk.content,
                                        skillName: chunk.skill_name,
                                        code: chunk.code,
                                        timestamp: chunk.timestamp
                                    })
                                } else if (eventType === 'code_execute') {
                                    lastMsg.agentSteps.push({
                                        type: 'code_execute',
                                        skillName: chunk.skill_name,
                                        code: chunk.code,
                                        timestamp: chunk.timestamp
                                    })
                                } else if (eventType === 'skill_result' || eventType === 'code_result') {
                                    lastMsg.agentSteps.push({
                                        type: eventType === 'skill_result' ? 'skill_result' : 'code_result',
                                        skillName: chunk.skill_name,
                                        result: chunk.result,
                                        timestamp: chunk.timestamp
                                    })
                                } else if (eventType === 'answer') {
                                    // Agent 的 answer 事件
                                    if (chunk.content) {
                                        assistantMsg += chunk.content
                                        lastMsg.content = assistantMsg

                                        // 将 answer 内容也作为步骤添加到 agentSteps
                                        const lastStep = lastMsg.agentSteps[lastMsg.agentSteps.length - 1]
                                        if (lastStep && lastStep.type === 'text') {
                                            lastStep.content = (lastStep.content || '') + chunk.content
                                        } else {
                                            lastMsg.agentSteps.push({
                                                type: 'text',
                                                content: chunk.content,
                                                timestamp: chunk.timestamp
                                            })
                                        }
                                    }
                                } else if (eventType === 'error') {
                                    lastMsg.agentSteps.push({
                                        type: 'error',
                                        error: chunk.error,
                                        timestamp: chunk.timestamp
                                    })
                                }

                                // 自动滚动
                                if (shouldAutoScroll.value) {
                                    scrollToBottom()
                                }
                            }
                            continue
                        }

                        // 处理 Chat 模式的响应
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

                                    // Detect code block for canvas
                                    // Look for the last opened code block
                                    const codeBlockRegex = /```(\w*)\n([\s\S]*?)(?:```|$)/g
                                    let match
                                    let lastMatch
                                    while ((match = codeBlockRegex.exec(assistantMsg)) !== null) {
                                        lastMatch = match
                                    }

                                    if (lastMatch) {
                                        const lang = lastMatch[1] || ''
                                        const code = lastMatch[2] || ''

                                        // Auto-open if specific languages or just always for code?
                                        // Let's auto-open if it's a new code block or we are streaming one
                                        // A simple heuristic: if we are in a code block that is growing.

                                        // Only update if content changed or it's new
                                        if (code !== canvasContent.value) {
                                            canvasContent.value = code
                                            canvasLanguage.value = lang

                                            // Auto-expand logic:
                                            // If not open, open it. But respect manual close.
                                            if (!isCanvasOpen.value && !userManuallyClosedCanvas.value) {
                                                isCanvasOpen.value = true
                                            }
                                        }
                                    }
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
            // Delegate click listener for code interactions
            document.addEventListener('click', handleGlobalClick)

            // Keyboard shortcuts
            window.addEventListener('keydown', handleKeyboardShortcuts)
        })
    })

    // Global click handler for copy/canvas buttons
    const handleGlobalClick = async (e: Event) => {
        const target = e.target as HTMLElement

        // Handle Copy Code
        const copyBtn = target.closest('.copy-code-btn') as HTMLElement
        if (copyBtn && copyBtn.dataset.code) {
            try {
                const code = decodeURIComponent(copyBtn.dataset.code)
                await navigator.clipboard.writeText(code)

                const originalHTML = copyBtn.innerHTML
                copyBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-green-600"><polyline points="20 6 9 17 4 12"/></svg><span class="text-green-600">已复制</span>`
                setTimeout(() => {
                    copyBtn.innerHTML = originalHTML
                }, 2000)
            } catch (err) {
                console.error('Failed to copy code:', err)
            }
            return
        }

        // Handle Open Canvas
        const canvasBtn = target.closest('.open-canvas-btn') as HTMLElement
        if (canvasBtn && canvasBtn.dataset.code) {
            const code = decodeURIComponent(canvasBtn.dataset.code)
            const language = canvasBtn.dataset.language || ''
            openCanvas(code, language)
        }
    }

    // Cleanup scroll listener and keyboard shortcuts
    onUnmounted(() => {
        document.removeEventListener('click', handleGlobalClick)

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
        thinkingSeconds,
        // Canvas
        isCanvasOpen,
        canvasContent,
        canvasLanguage,
        openCanvas,
        closeCanvas,
        // Agent 模式
        isAgentMode,
        toggleAgentMode
    }
}
