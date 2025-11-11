// ==UserScript==
// @name         everBrowser Chat - AI 浏览器助手
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  Claude.ai 风格的 AI 浏览器助手，可以操作当前页面
// @author       everBrowser
// @match        *://*/*
// @icon         data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgdmlld0JveD0iMCAwIDMyIDMyIj48cmVjdCB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIGZpbGw9IiNlMDdiMzkiIHJ4PSI4Ii8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIyMCIgZm9udC13ZWlnaHQ9ImJvbGQiIGZpbGw9IndoaXRlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIj5FPC90ZXh0Pjwvc3ZnPg==
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    // Configuration
    const API_BASE_URL = 'http://127.0.0.1:41465';
    let currentSessionId = 'session_' + Date.now();
    let isStreaming = false;
    let isCollapsed = false;

    // Inject Styles
    GM_addStyle(`
        /* Page Body Adjustment */
        body {
            margin-right: 420px !important;
            transition: margin-right 0.3s ease;
        }

        body.eb-sidebar-collapsed {
            margin-right: 50px !important;
        }

        /* Sidebar Container */
        #everBrowserSidebar {
            position: fixed;
            top: 0;
            right: 0;
            width: 420px;
            height: 100vh;
            background: #1a1a1a;
            box-shadow: -4px 0 16px rgba(0, 0, 0, 0.3);
            display: flex;
            flex-direction: column;
            z-index: 999999;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
            color: #f0f0f0;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        #everBrowserSidebar.collapsed {
            width: 50px;
        }

        /* Collapsed Tab */
        .eb-collapsed-tab {
            display: none;
            position: absolute;
            top: 50%;
            left: 0;
            width: 50px;
            height: 200px;
            transform: translateY(-50%);
            background: linear-gradient(135deg, #e07b39, #ff8c47);
            border-radius: 8px 0 0 8px;
            cursor: pointer;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 12px;
            padding: 20px 0;
            box-shadow: -2px 0 8px rgba(0, 0, 0, 0.2);
        }

        #everBrowserSidebar.collapsed .eb-collapsed-tab {
            display: flex;
        }

        .eb-collapsed-icon {
            font-size: 24px;
            writing-mode: vertical-rl;
            text-orientation: mixed;
        }

        .eb-collapsed-text {
            font-size: 14px;
            font-weight: 600;
            writing-mode: vertical-rl;
            text-orientation: mixed;
            color: white;
        }

        /* Main Content Area */
        .eb-main-content {
            display: flex;
            flex-direction: column;
            height: 100%;
            opacity: 1;
            transition: opacity 0.3s ease;
        }

        #everBrowserSidebar.collapsed .eb-main-content {
            opacity: 0;
            pointer-events: none;
        }

        /* Header */
        .eb-header {
            padding: 16px;
            background: linear-gradient(135deg, #e07b39, #ff8c47);
            display: flex;
            align-items: center;
            justify-content: space-between;
            user-select: none;
            flex-shrink: 0;
        }

        .eb-header-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .eb-logo {
            width: 28px;
            height: 28px;
            background: white;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: #e07b39;
            font-size: 16px;
        }

        .eb-title {
            font-weight: 600;
            font-size: 15px;
            color: white;
        }

        .eb-header-right {
            display: flex;
            gap: 8px;
        }

        .eb-header-btn {
            width: 32px;
            height: 32px;
            background: rgba(255, 255, 255, 0.2);
            border: none;
            border-radius: 6px;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
            font-size: 18px;
            font-weight: bold;
        }

        .eb-header-btn:hover {
            background: rgba(255, 255, 255, 0.3);
        }

        .eb-collapse-btn {
            font-size: 16px;
        }

        /* Status Bar */
        .eb-status {
            padding: 8px 16px;
            background: #2d2d2d;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid #3d3d3d;
        }

        .eb-status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #4caf50;
            animation: eb-pulse 2s infinite;
        }

        @keyframes eb-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Messages Container */
        .eb-messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #212121;
        }

        .eb-messages::-webkit-scrollbar {
            width: 6px;
        }

        .eb-messages::-webkit-scrollbar-track {
            background: transparent;
        }

        .eb-messages::-webkit-scrollbar-thumb {
            background: #3d3d3d;
            border-radius: 3px;
        }

        /* Welcome Screen */
        .eb-welcome {
            text-align: center;
            padding: 40px 20px;
            color: #b0b0b0;
        }

        .eb-welcome-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }

        .eb-welcome-title {
            font-size: 18px;
            font-weight: 900;
            margin-bottom: 8px;
            color: #f0f0f0;
        }

        .eb-welcome-text {
            font-size: 13px;
            line-height: 1.5;
        }

        /* Message */
        .eb-message {
            display: flex;
            gap: 10px;
            animation: eb-fadeIn 0.3s ease;
        }

        @keyframes eb-fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .eb-message-content {
            flex: 1;
            padding: 10px 12px;
            border-radius: 10px;
            font-size: 14px;
            line-height: 1.5;
        }

        .eb-user-message .eb-message-content {
            background: #3d3d3d;
        }

        .eb-ai-message .eb-message-content {
            background: #2d2d2d;
        }

        .eb-message-content p {
            margin: 0 0 8px 0;
        }

        .eb-message-content p:last-child {
            margin-bottom: 0;
        }

        .eb-message-content code {
            background: rgba(255, 255, 255, 0.1);
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }

        /* Tool Call */
        .eb-tool-call {
            background: #2a2a2a;
            border: 1px solid #3d3d3d;
            border-radius: 6px;
            padding: 8px;
            margin-top: 8px;
            font-size: 12px;
        }

        .eb-tool-header {
            display: flex;
            align-items: center;
            gap: 6px;
            color: #e07b39;
            font-weight: 500;
            margin-bottom: 4px;
        }

        .eb-tool-body {
            color: #b0b0b0;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            white-space: pre-wrap;
            word-break: break-all;
        }

        /* Typing Indicator */
        .eb-typing {
            display: flex;
            gap: 4px;
            padding: 4px 0;
        }

        .eb-typing-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #808080;
            animation: eb-typing 1.4s infinite;
        }

        .eb-typing-dot:nth-child(2) {
            animation-delay: 0.2s;
        }

        .eb-typing-dot:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes eb-typing {
            0%, 60%, 100% {
                transform: translateY(0);
                opacity: 0.7;
            }
            30% {
                transform: translateY(-8px);
                opacity: 1;
            }
        }

        /* Code Block Loading Animation */
        .eb-code-loading {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 12px;
            margin: 6px 0;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            position: relative;
            overflow: hidden;
        }

        .eb-code-loading::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
            animation: eb-code-loading-shimmer 1.5s infinite;
        }

        @keyframes eb-code-loading-shimmer {
            0% {
                left: -100%;
            }
            100% {
                left: 100%;
            }
        }

        .eb-code-loading-dots {
            display: flex;
            gap: 5px;
            justify-content: center;
            align-items: center;
            height: 16px;
        }

        .eb-code-loading-dot {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #e07b39;
            animation: eb-code-loading-dot 1.4s infinite ease-in-out;
        }

        .eb-code-loading-dot:nth-child(2) {
            animation-delay: 0.2s;
        }

        .eb-code-loading-dot:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes eb-code-loading-dot {
            0%, 60%, 100% {
                transform: scale(1);
                opacity: 0.7;
            }
            30% {
                transform: scale(1.3);
                opacity: 1;
            }
        }

        /* Input Container */
        .eb-input-container {
            padding: 12px;
            background: #1a1a1a;
            border-top: 1px solid #3d3d3d;
        }

        .eb-input-wrapper {
            position: relative;
        }

        .eb-input {
            width: 100%;
            min-height: 40px;
            max-height: 120px;
            padding: 10px 40px 10px 12px;
            background: #2d2d2d;
            border: 1px solid #3d3d3d;
            border-radius: 8px;
            color: #f0f0f0;
            font-size: 14px;
            font-family: inherit;
            resize: none;
            outline: none;
            transition: border-color 0.2s;
        }

        .eb-input:focus {
            border-color: #e07b39;
        }

        .eb-input::placeholder {
            color: #808080;
        }

        .eb-send-btn {
            position: absolute;
            right: 6px;
            bottom: 6px;
            width: 28px;
            height: 28px;
            background: #e07b39;
            border: none;
            border-radius: 6px;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }

        .eb-send-btn:hover:not(:disabled) {
            background: #ff8c47;
        }

        .eb-send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Error Message */
        .eb-error {
            background: rgba(244, 67, 54, 0.1);
            border: 1px solid #f44336;
            color: #f44336;
            padding: 8px;
            border-radius: 6px;
            font-size: 13px;
            margin-top: 8px;
        }
    `);

    // Create Sidebar
    function createSidebar() {
        const sidebar = document.createElement('div');
        sidebar.id = 'everBrowserSidebar';

        sidebar.innerHTML = `
            <div class="eb-collapsed-tab" onclick="toggleSidebar()">
                <div class="eb-collapsed-icon">🤖</div>
                <div class="eb-collapsed-text">everBrowser</div>
            </div>
            <div class="eb-main-content">
                <div class="eb-header">
                    <div class="eb-header-left">
                        <div class="eb-logo">E</div>
                        <div class="eb-title">everBrowser</div>
                    </div>
                    <div class="eb-header-right">
                        <button class="eb-header-btn eb-collapse-btn" id="ebCollapse" title="收起侧边栏">«</button>
                    </div>
                </div>
                <div class="eb-status">
                    <span class="eb-status-dot"></span>
                    <span id="ebStatus">正在连接...</span>
                </div>
                <div class="eb-messages" id="ebMessages">
                    <div class="eb-welcome">
                        <div class="eb-welcome-icon">🌐</div>
                        <div class="eb-welcome-title">欢迎使用 everBrowser</div>
                        <div class="eb-welcome-text">
                            我是你的 AI 浏览器助手<br>
                            可以帮你操作当前页面、搜索信息等
                        </div>
                    </div>
                </div>
                <div class="eb-input-container">
                    <div class="eb-input-wrapper">
                        <textarea
                            id="ebInput"
                            class="eb-input"
                            placeholder="输入消息... (Shift+Enter 换行)"
                            rows="1"
                        ></textarea>
                        <button class="eb-send-btn" id="ebSend">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(sidebar);
        setupEventListeners(sidebar);
        checkHealth();

        return sidebar;
    }

    // Setup Event Listeners
    function setupEventListeners(sidebar) {
        const input = sidebar.querySelector('#ebInput');
        const sendBtn = sidebar.querySelector('#ebSend');
        const collapseBtn = sidebar.querySelector('#ebCollapse');

        sendBtn.addEventListener('click', sendMessage);
        collapseBtn.addEventListener('click', toggleSidebar);

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });
    }

    // Toggle Sidebar
    function toggleSidebar() {
        const sidebar = document.getElementById('everBrowserSidebar');
        const collapseBtn = document.getElementById('ebCollapse');

        isCollapsed = !isCollapsed;

        if (isCollapsed) {
            sidebar.classList.add('collapsed');
            document.body.classList.add('eb-sidebar-collapsed');
            if (collapseBtn) collapseBtn.innerHTML = '»';
        } else {
            sidebar.classList.remove('collapsed');
            document.body.classList.remove('eb-sidebar-collapsed');
            if (collapseBtn) collapseBtn.innerHTML = '«';
            // Focus input when expanding
            setTimeout(() => {
                const input = document.getElementById('ebInput');
                if (input) input.focus();
            }, 300);
        }
    }

    // Check Health
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
            console.error('everBrowser: Health check failed', error);
        }
    }

    // Update Status
    function updateStatus(text, type = 'success') {
        const statusEl = document.getElementById('ebStatus');
        const dotEl = document.querySelector('.eb-status-dot');

        if (statusEl) {
            statusEl.textContent = text;
        }

        if (dotEl) {
            const colors = {
                success: '#4caf50',
                warning: '#ff9800',
                error: '#f44336'
            };
            dotEl.style.background = colors[type] || colors.success;
        }
    }

    // Send Message
    async function sendMessage() {
        const input = document.getElementById('ebInput');
        const sendBtn = document.getElementById('ebSend');
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
        const aiMessageId = 'msg_' + Date.now();
        addMessage('ai', '', aiMessageId);
        addTypingIndicator(aiMessageId);

        // Start streaming
        try {
            await streamChat(message, aiMessageId);
        } catch (error) {
            console.error('everBrowser: Chat error', error);
            updateMessageContent(aiMessageId, `<div class="eb-error">❌ 出错了: ${error.message}</div>`);
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
        let toolCalls = [];

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

                                case 'tool_call_start':
                                case 'tool_call_complete':
                                    const toolCall = {
                                        name: data.tool_name,
                                        args: data.tool_args || {},
                                        id: data.tool_call_id || Date.now()
                                    };
                                    toolCalls.push(toolCall);
                                    updateMessageWithTools(messageId, fullContent, toolCalls);
                                    break;

                                case 'tool_result':
                                    updateStatus(`执行: ${data.tool_name}`, 'warning');
                                    break;

                                case 'end':
                                    updateStatus('就绪', 'success');
                                    break;

                                case 'error':
                                    throw new Error(data.error);
                            }
                        } catch (e) {
                            console.error('everBrowser: Parse error', e);
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
        const messagesContainer = document.getElementById('ebMessages');
        const welcome = messagesContainer.querySelector('.eb-welcome');
        if (welcome) {
            welcome.remove();
        }

        const messageId = id || 'msg_' + Date.now();
        const isUser = role === 'user';

        const messageDiv = document.createElement('div');
        messageDiv.className = `eb-message eb-${role}-message`;
        messageDiv.id = messageId;

        messageDiv.innerHTML = `
            <div class="eb-message-content" id="${messageId}-content">
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
                <div class="eb-code-loading">
                    <div class="eb-code-loading-dots">
                        <div class="eb-code-loading-dot"></div>
                        <div class="eb-code-loading-dot"></div>
                        <div class="eb-code-loading-dot"></div>
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

    // Update Message with Tools
    function updateMessageWithTools(messageId, content, toolCalls) {
        let html = formatContent(content);

        if (toolCalls.length > 0) {
            html += '<div style="margin-top: 8px;">';
            for (const tool of toolCalls) {
                html += `
                    <div class="eb-tool-call">
                        <div class="eb-tool-header">
                            <span>🔧</span>
                            <span>调用工具: ${tool.name}</span>
                        </div>
                        <div class="eb-tool-body">${JSON.stringify(tool.args, null, 2)}</div>
                    </div>
                `;
            }
            html += '</div>';
        }

        updateMessageContent(messageId, html);
    }

    // Format Content
    function formatContent(content) {
        if (!content) return '';

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
        const messagesContainer = document.getElementById('ebMessages');
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    // Initialize
    console.log('everBrowser: User script loaded');
    createSidebar();

    // Periodic health check
    setInterval(checkHealth, 30000);

    // Keyboard shortcut: Alt+E to toggle sidebar
    document.addEventListener('keydown', (e) => {
        if (e.altKey && e.key === 'e') {
            e.preventDefault();
            toggleSidebar();
        }
    });

    // Make toggleSidebar available globally for onclick
    window.toggleSidebar = toggleSidebar;

})();
