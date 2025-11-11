// Configuration
const API_BASE_URL = 'http://127.0.0.1:41465';
let currentSessionId = 'session_' + Date.now();
let isStreaming = false;
let messageCounter = 0;

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

// Initialize
init();

function init() {
    setupEventListeners();
    checkHealth();
}

// Event Listeners
function setupEventListeners() {
    sendBtn.addEventListener('click', sendMessage);

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
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

// Send Message
async function sendMessage() {
    const message = input.value.trim();

    if (!message || isStreaming) return;

    // Add user message
    addMessage('user', message);

    // Clear input
    input.value = '';
    input.style.height = 'auto';

    // Disable input
    input.disabled = true;
    sendBtn.disabled = true;
    updateStatus('思考中...', 'warning');

    // Add AI message placeholder
    const aiMessageId = generateMessageId('ai');
    addMessage('ai', '', aiMessageId);
    addTypingIndicator(aiMessageId);

    // Start streaming
    try {
        await streamChat(message, aiMessageId);
    } catch (error) {
        console.error('Chat error:', error);
        updateMessageContent(aiMessageId, `<div class="error">❌ 出错了: ${error.message}</div>`);
        updateStatus('就绪', 'success');
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

// Stream Chat
async function streamChat(message, messageId) {
    isStreaming = true;
    let fullContent = '';

    try {
        const response = await fetch(`${API_BASE_URL}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId
            })
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
                        }
                    } catch (e) {
                        console.error('Parse error:', e);
                    }
                }
            }
        }
    } finally {
        isStreaming = false;
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

    // 处理引用格式（> 开头的行）
    content = content.replace(/^>\s*(.*)$/gm, '<blockquote>$1</blockquote>');
    
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
