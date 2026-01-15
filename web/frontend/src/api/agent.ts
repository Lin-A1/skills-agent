import axios from 'axios';

const AGENT_API_URL = import.meta.env.VITE_AGENT_API_URL || 'http://localhost:8009/api/agent';

// 创建 axios 实例
const agentApi = axios.create({
    baseURL: AGENT_API_URL,
    timeout: 30000, // 30s
    headers: {
        'Content-Type': 'application/json',
    },
});

export interface AgentEvent {
    event_type: 'thinking' | 'skill_call' | 'skill_result' | 'code_execute' | 'code_result' | 'answer' | 'error' | 'done';
    content?: string;
    skill_name?: string;
    code?: string;
    result?: any;
    error?: string;
    timestamp?: string;
}

export interface AgentResponse {
    id: string;
    session_id: string;
    model: string;
    content: string;
    events: AgentEvent[];
    skills_used: string[];
    usage: {
        prompt_tokens: number;
        completion_tokens: number;
        total_tokens: number;
    };
    created: number;
}

export interface Session {
    id: string;
    title?: string;
    created_at: string;
    updated_at: string;
    model: string;
    is_active: boolean;
    is_archived: boolean;
    message_count: number;
}

export interface Message {
    id: string;
    session_id: string;
    role: 'system' | 'user' | 'assistant' | 'tool';
    content: string;
    created_at: string;
    event_type?: string;
    skill_name?: string;
    execution_result?: any;
    extra_data?: any;
}

// Sessions
export const listSessions = async (page = 1, pageSize = 20) => {
    const response = await agentApi.get('/sessions', {
        params: { page, page_size: pageSize },
    });
    return response.data;
};

export const createSession = async (data: {
    title?: string;
    model?: string;
    system_prompt?: string;
    temperature?: number;
}) => {
    const response = await agentApi.post('/sessions', data);
    return response.data;
};

export const getSession = async (sessionId: string) => {
    const response = await agentApi.get(`/sessions/${sessionId}`);
    return response.data;
};

export const deleteSession = async (sessionId: string) => {
    const response = await agentApi.delete(`/sessions/${sessionId}`);
    return response.data;
};

// Messages
export const getMessages = async (sessionId: string, limit?: number) => {
    const response = await agentApi.get(`/sessions/${sessionId}/messages`, {
        params: { limit },
    });
    return response.data;
};

export const clearMessages = async (sessionId: string) => {
    const response = await agentApi.delete(`/sessions/${sessionId}/messages`);
    return response.data;
};

// Completion
export const complete = async (data: {
    message: string;
    session_id?: string;
    model?: string;
    stream?: boolean;
}) => {
    if (data.stream) {
        throw new Error('Use streamComplete for streaming requests');
    }
    const response = await agentApi.post('/completions', data);
    return response.data;
};

// Stream Completion
export const streamURL = `${AGENT_API_URL}/completions`;

// Skills
export const listSkills = async () => {
    const response = await agentApi.get('/skills');
    return response.data;
};

export const getSkill = async (skillName: string) => {
    const response = await agentApi.get(`/skills/${skillName}`);
    return response.data;
};
