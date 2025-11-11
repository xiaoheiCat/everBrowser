// Configuration
const API_BASE_URL = 'http://127.0.0.1:41465';
let currentSessionId = 'session_' + Date.now();
let isStreaming = false;
let messageCounter = 0;
let messageHistory = []; // 存储消息历史用于上下文

// Generate unique message ID
function generateMessageId(role) {
    return `msg_${role}_${Date.now()}_${++messageCounter}`;
}

// DOM Elements
const messagesContainer = document.getElementById('messages');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const statusEl = document.getElementById('status');
const statusDot = document.querySelector('.status-dot');

// 用于停止当前请求的 AbortController
let currentAbortController = null;

// Initialize
init();

function init() {
    setupEventListeners();
    checkHealth();
}

// Event Listeners
function setupEventListeners() {
    sendBtn.addEventListener('click', handleSendButtonClick);

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            // 只有在不处于流式处理状态时才允许发送消息
            if (!isStreaming) {
                handleSendButtonClick();
            }
        }
    });

    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 200) + 'px';
    });
}

// Health Check
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        const data = await response.json();

        if (data.status === 'healthy' && data.agent_ready) {
            updateStatus('就绪', 'success');
        } else {
            updateStatus('Agent 未就绪', 'warning');
        }
    } catch (error) {
        updateStatus('无法连接服务器', 'error');
        console.error('Health check failed:', error);
    }
}

// Update Status
function updateStatus(text, type = 'success') {
    statusEl.textContent = text;

    const colors = {
        success: '#4caf50',
        warning: '#ff9800',
        error: '#f44336'
    };
    statusDot.style.background = colors[type] || colors.success;
}

// 处理发送按钮点击事件
function handleSendButtonClick() {
    if (isStreaming) {
        // 如果正在流式处理，则停止当前请求
        stopCurrentRequest();
    } else {
        // 否则发送消息
        sendMessage();
    }
}

// 停止当前请求
function stopCurrentRequest() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
    isStreaming = false;
    updateStatus('已停止', 'warning');
    updateSendButton(false);
}

// 构建对话历史用于上下文
function buildConversationHistory(currentMessage) {
    // 获取最近的历史消息（不包括当前正在发送的消息）
    const recentHistory = messageHistory.slice(-10); // 最近10条消息
    
    // 构建对话历史，过滤掉空消息和系统消息
    const conversation = [];
    
    for (const msg of recentHistory) {
        if (msg.content && msg.content.trim() && msg.role !== 'system') {
            conversation.push({
                role: msg.role === 'user' ? 'user' : 'assistant',
                content: msg.content
            });
        }
    }
    
    // 添加当前用户消息
    conversation.push({
        role: 'user',
        content: currentMessage
    });
    
    return conversation;
}

// 更新发送按钮状态
function updateSendButton(isStreamingState) {
    if (isStreamingState) {
        // 显示停止按钮
        sendBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
        `;
        sendBtn.title = '停止';
        sendBtn.classList.add('stop-btn');
    } else {
        // 显示发送按钮
        sendBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
        `;
        sendBtn.title = '发送';
        sendBtn.classList.remove('stop-btn');
    }
}

// Send Message
async function sendMessage() {
    const message = input.value.trim();

    if (!message) return;

    // Add user message
    addMessage('user', message);

    // Clear input
    input.value = '';
    input.style.height = 'auto';

    // Disable input
    input.disabled = true;
    updateStatus('思考中...', 'warning');

    // Add AI message placeholder
    const aiMessageId = generateMessageId('ai');
    addMessage('ai', '', aiMessageId);
    addTypingIndicator(aiMessageId);

    // 构建包含上下文的对话历史
    const conversationHistory = buildConversationHistory(message);

    // Start streaming
    try {
        await streamChat(conversationHistory, aiMessageId);
    } catch (error) {
        if (error.name === 'AbortError') {
            updateMessageContent(aiMessageId, `<div class="error">⏹️ 已停止生成</div>`);
            updateStatus('已停止', 'warning');
        } else {
            console.error('Chat error:', error);
            updateMessageContent(aiMessageId, `<div class="error">❌ 出错了: ${error.message}</div>`);
            updateStatus('就绪', 'success');
        }
    } finally {
        input.disabled = false;
        input.focus();
        // 注意：这里不调用 updateSendButton(false)，因为已经在 stopCurrentRequest 或 streamChat 中处理
    }
}

// Stream Chat
async function streamChat(conversationHistory, messageId) {
    isStreaming = true;
    let fullContent = '';

    // 创建新的 AbortController
    currentAbortController = new AbortController();
    
    // 更新按钮为停止状态
    updateSendButton(true);
    
    // 设置placeholder为思考状态
    input.placeholder = 'everBrowser AI 正在思考...';

    try {
        const response = await fetch(`${API_BASE_URL}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                messages: conversationHistory, // 发送对话历史
                session_id: currentSessionId
            }),
            signal: currentAbortController.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        switch (data.type) {
                            case 'start':
                                removeTypingIndicator(messageId);
                                break;

                            case 'token':
                                fullContent += data.content;
                                updateMessageContent(messageId, formatContent(fullContent));
                                scrollToBottom();
                                break;

                            case 'end':
                                updateStatus('就绪', 'success');
                                break;

                            case 'error':
                                throw new Error(data.error);
                                
                            case 'ping':
                                // 忽略心跳包，用于连接检查
                                break;
                        }
                    } catch (e) {
                        console.error('Parse error:', e);
                    }
                }
            }
        }
    } finally {
        isStreaming = false;
        currentAbortController = null;
        // 确保按钮状态恢复为发送状态
        updateSendButton(false);
        // 恢复placeholder
        input.placeholder = '输入消息...';
    }
}

// Add Message
function addMessage(role, content, id = null) {
    const welcome = messagesContainer.querySelector('.welcome');
    if (welcome) {
        welcome.remove();
    }

    const messageId = id || generateMessageId(role);
    const isUser = role === 'user';

    console.log(`Adding ${role} message with ID: ${messageId}`);

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;
    messageDiv.id = messageId;

    messageDiv.innerHTML = `
        <div class="message-content" id="${messageId}-content">
            ${formatContent(content)}
        </div>
    `;

    messagesContainer.appendChild(messageDiv);
    scrollToBottom();

    // 保存消息到历史记录（用于上下文）
    if (content && content.trim()) {
        messageHistory.push({
            role: role,
            content: content,
            id: messageId,
            timestamp: Date.now()
        });
        
        // 限制历史记录长度，保留最近20条消息
        if (messageHistory.length > 20) {
            messageHistory.shift();
        }
    }

    return messageId;
}

// Add Typing Indicator
function addTypingIndicator(messageId) {
    const contentEl = document.getElementById(`${messageId}-content`);
    if (contentEl) {
        contentEl.innerHTML = `
            <div class="code-loading">
                <div class="code-loading-dots">
                    <div class="code-loading-dot"></div>
                    <div class="code-loading-dot"></div>
                    <div class="code-loading-dot"></div>
                </div>
            </div>
        `;
    }
}

// Remove Typing Indicator
function removeTypingIndicator(messageId) {
    const contentEl = document.getElementById(`${messageId}-content`);
    if (contentEl) {
        contentEl.innerHTML = '';
    }
}

// Update Message Content
function updateMessageContent(messageId, content) {
    const contentEl = document.getElementById(`${messageId}-content`);
    if (contentEl) {
        contentEl.innerHTML = content;
    }
}



// Format Content
function formatContent(content) {
    if (!content) return '';

    // 处理分隔线（---）
    content = content.replace(/^---$/gm, '<hr class="think-divider">');
    
    // 处理引用格式（> 开头的行）- 将多行引用合并为一个blockquote
    content = content.replace(/^> .*(?:\n> .*)*/gm, function(match) {
        // 移除每行的 > 前缀，并将多行内容合并
        const cleanContent = match.replace(/^> /gm, '');
        return '<blockquote>' + cleanContent + '</blockquote>';
    });
    
    // Simple markdown-like formatting
    content = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');

    return content;
}

// Scroll to Bottom
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Periodic health check
setInterval(checkHealth, 30000);
