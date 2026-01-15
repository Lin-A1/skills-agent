import { ref } from 'vue';
import {
    listSessions, createSession, getMessages, deleteSession as apiDeleteSession, streamURL,
    type Session, type Message, type AgentEvent
} from '@/api/agent';


export function useAgent() {
    const sessions = ref<Session[]>([]);
    const currentSession = ref<Session | null>(null);
    const messages = ref<Message[]>([]);
    const isThinking = ref(false);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    // 加载会话列表
    const loadSessions = async () => {
        try {
            isLoading.value = true;
            const res = await listSessions();
            sessions.value = res.sessions;
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    // 选择会话
    const selectSession = async (session: Session) => {
        currentSession.value = session;
        await loadMessages(session.id);
    };

    // 创建新会话
    const createNewSession = async () => {
        try {
            isLoading.value = true;
            const session = await createSession({ title: '新对话' });
            sessions.value.unshift(session);
            await selectSession(session);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    // 加载消息
    const loadMessages = async (sessionId: string) => {
        try {
            isLoading.value = true;
            const res = await getMessages(sessionId);
            messages.value = res.messages;
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    // 这里的 id 生成逻辑只是临时的，后端会生成真正的 ID
    const tempId = () => `temp-${Date.now()}`;

    // 发送消息（流式）
    const sendMessage = async (content: string) => {
        if (!currentSession.value) {
            await createNewSession();
        }

        if (!currentSession.value) return;

        const sessionId = currentSession.value.id;

        // 添加用户消息
        const userMsg: Message = {
            id: tempId(),
            session_id: sessionId,
            role: 'user',
            content: content,
            created_at: new Date().toISOString()
        };
        messages.value.push(userMsg);

        // 准备助手消息占位
        const assistantMsg = ref<Message>({
            id: `reply-${Date.now()}`,
            session_id: sessionId,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
            event_type: 'thinking', // 初始状态
            extra_data: { events: [] }
        });
        messages.value.push(assistantMsg.value);

        isThinking.value = true;
        error.value = null;

        try {
            try {
                const response = await fetch(streamURL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        session_id: sessionId,
                        message: content,
                        stream: true
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                if (!response.body) {
                    throw new Error('Response body is null');
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.trim() === '') continue;
                        if (line.startsWith('data: ')) {
                            const data = line.slice(6);
                            if (data === '[DONE]') continue;

                            try {
                                const event: AgentEvent = JSON.parse(data);

                                // 记录事件历史
                                if (!assistantMsg.value.extra_data.events) {
                                    assistantMsg.value.extra_data.events = [];
                                }
                                assistantMsg.value.extra_data.events.push(event);

                                // 处理不同事件类型
                                if (event.event_type === 'answer') {
                                    assistantMsg.value.content += (event.content || '');
                                    assistantMsg.value.event_type = 'answer';
                                } else if (event.event_type === 'thinking') {
                                    assistantMsg.value.event_type = 'thinking';
                                } else if (event.event_type === 'skill_call') {
                                    assistantMsg.value.event_type = 'skill_call';
                                    assistantMsg.value.skill_name = event.skill_name;
                                } else if (event.event_type === 'error') {
                                    error.value = event.error || 'Unknown error';
                                }
                            } catch (e) {
                                console.error('Failed to parse event:', e);
                            }
                        }
                    }
                }
            } catch (e: any) {
                error.value = e.message;
                assistantMsg.value.content += `\n[错误: ${e.message}]`;
            }
        } finally {
            isThinking.value = false;
            // 刷新消息以获取确切的 ID 和状态
            await loadMessages(sessionId);
        }
    };

    // 删除会话
    const deleteSession = async (sessionId: string) => {
        try {
            await apiDeleteSession(sessionId);
            sessions.value = sessions.value.filter(s => s.id !== sessionId);
            if (currentSession.value?.id === sessionId) {
                currentSession.value = null;
                messages.value = [];
            }
        } catch (e: any) {
            error.value = e.message;
        }
    };

    return {
        sessions,
        currentSession,
        messages,
        isThinking,
        isLoading,
        error,
        loadSessions,
        selectSession,
        createNewSession,
        deleteSession,
        sendMessage
    };
}
