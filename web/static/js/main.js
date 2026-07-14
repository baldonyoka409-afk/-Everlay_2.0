// Everlay Web UI - Main JavaScript
class EverlayApp {
    constructor() {
        this.currentAgent = 'default';
        this.currentModel = 'openai/gpt-4o-mini';
        this.currentConversationId = null;
        this.isStreaming = false;
        this.messageHistory = [];

        this.initElements();
        this.bindEvents();
        this.loadAgents();
        this.checkConnection();
        this.loadSessions();
    }

    initElements() {
        // Sidebar
        this.sidebar = document.getElementById('sidebar');
        this.sidebarToggle = document.getElementById('sidebarToggle');
        this.mobileMenuBtn = document.getElementById('mobileMenuBtn');
        this.mobileOverlay = document.getElementById('mobileOverlay');
        this.agentList = document.getElementById('agentList');
        this.sessionList = document.getElementById('sessionList');
        this.newSessionBtn = document.getElementById('newSessionBtn');
        this.settingsBtn = document.getElementById('settingsBtn');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.connectionText = document.getElementById('connectionText');

        // Header
        this.currentAgentName = document.getElementById('currentAgentName');
        this.agentSelector = document.getElementById('agentSelector');
        this.agentDropdown = document.getElementById('agentDropdown');
        this.currentModelName = document.getElementById('currentModelName');
        this.modelSelector = document.getElementById('modelSelector');
        this.modelDropdown = document.getElementById('modelDropdown');

        // Chat
        this.messagesContainer = document.getElementById('messages');
        this.welcomeMessage = document.getElementById('welcomeMessage');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.codeBtn = document.getElementById('codeBtn');
        this.attachBtn = document.getElementById('attachBtn');

        // Settings Modal
        this.settingsModal = document.getElementById('settingsModal');
        this.settingsClose = document.getElementById('settingsClose');
        this.settingsCancel = document.getElementById('settingsCancel');
        this.settingsSave = document.getElementById('settingsSave');
        this.tempSlider = document.getElementById('tempSlider');
        this.tempValue = document.getElementById('tempValue');
        this.maxTokensInput = document.getElementById('maxTokensInput');
        this.systemPromptInput = document.getElementById('systemPromptInput');
        this.streamToggle = document.getElementById('streamToggle');

        // Context menu
        this.contextMenu = document.getElementById('contextMenu');
    }

    bindEvents() {
        // Sidebar toggle
        this.sidebarToggle?.addEventListener('click', () => this.toggleSidebar());
        this.mobileMenuBtn?.addEventListener('click', () => this.toggleSidebar());
        this.mobileOverlay?.addEventListener('click', () => this.closeSidebar());

        // Agent selector
        this.agentSelector?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleDropdown(this.agentDropdown);
        });
        this.agentDropdown?.addEventListener('click', (e) => {
            const option = e.target.closest('.selector-option');
            if (option) this.selectAgent(option.dataset.agent);
        });

        // Model selector
        this.modelSelector?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleDropdown(this.modelDropdown);
        });
        this.modelDropdown?.addEventListener('click', (e) => {
            const option = e.target.closest('.selector-option');
            if (option) this.selectModel(option.dataset.model);
        });

        // Close dropdowns on outside click
        document.addEventListener('click', () => this.closeAllDropdowns());

        // New session
        this.newSessionBtn?.addEventListener('click', () => this.newSession());

        // Settings
        this.settingsBtn?.addEventListener('click', () => this.openSettings());
        this.settingsClose?.addEventListener('click', () => this.closeSettings());
        this.settingsCancel?.addEventListener('click', () => this.closeSettings());
        this.settingsSave?.addEventListener('click', () => this.saveSettings());
        this.tempSlider?.addEventListener('input', (e) => {
            this.tempValue.textContent = parseFloat(e.target.value).toFixed(1);
        });

        // Message input
        this.messageInput?.addEventListener('keydown', (e) => this.handleKeydown(e));
        this.sendBtn?.addEventListener('click', () => this.sendMessage());
        this.clearBtn?.addEventListener('click', () => this.clearChat());
        this.codeBtn?.addEventListener('click', () => this.insertCodeBlock());

        // Auto-resize textarea
        this.messageInput?.addEventListener('input', () => this.autoResize());

        // Context menu
        document.addEventListener('contextmenu', (e) => this.showContextMenu(e));
        document.addEventListener('click', () => this.hideContextMenu());
    }

    async loadAgents() {
        try {
            const response = await fetch('/api/agents');
            const agents = await response.json();

            // Populate agent list in sidebar
            this.agentList.innerHTML = agents.map(a => `
                <li>
                    <button class="nav-item" data-agent="${a.name}">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"></path>
                            <path d="M12 6v6l4 2"></path>
                        </svg>
                        ${a.name}
                    </button>
                </li>
            `).join('');

            // Populate agent dropdown
            this.agentDropdown.innerHTML = agents.map(a => `
                <div class="selector-option ${a.name === this.currentAgent ? 'selected' : ''}" data-agent="${a.name}">
                    ${a.name}
                </div>
            `).join('');

            // Bind agent list clicks
            this.agentList.querySelectorAll('.nav-item').forEach(btn => {
                btn.addEventListener('click', () => this.selectAgent(btn.dataset.agent));
            });

            // Populate model dropdown
            this.loadModels();
        } catch (e) {
            console.error('Failed to load agents:', e);
        }
    }

    async loadModels() {
        try {
            const response = await fetch('/api/models');
            const data = await response.json();
            const models = data.models || [];

            // Filter to show popular models first
            const popularModels = [
                'nvidia/nemotron-3-ultra-550b-a55b:free',
                'poolside/laguna-m.1:free',
                'openai/gpt-4o-mini',
                'openai/gpt-4o',
                'anthropic/claude-3.5-sonnet',
                'google/gemini-2.5-pro',
            ];

            const otherModels = models
                .map(m => m.id)
                .filter(id => !popularModels.includes(id));

            const allModels = [...popularModels, ...otherModels];

            this.modelDropdown.innerHTML = allModels.map(m => `
                <div class="selector-option ${m === this.currentModel ? 'selected' : ''}" data-model="${m}">
                    ${m}
                </div>
            `).join('');
        } catch (e) {
            console.error('Failed to load models:', e);
            // Fallback
            const fallback = ['nvidia/nemotron-3-ultra-550b-a55b:free', 'openai/gpt-4o-mini'];
            this.modelDropdown.innerHTML = fallback.map(m => `
                <div class="selector-option ${m === this.currentModel ? 'selected' : ''}" data-model="${m}">
                    ${m}
                </div>
            `).join('');
        }
    }

    async checkConnection() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();
            if (data.status === 'ok') {
                this.setConnectionStatus(true);
            } else {
                this.setConnectionStatus(false);
            }
        } catch (e) {
            this.setConnectionStatus(false);
        }
    }

    setConnectionStatus(connected) {
        this.connectionStatus.classList.toggle('connected', connected);
        this.connectionText.textContent = connected ? 'Connected' : 'Disconnected';
    }

    toggleSidebar() {
        this.sidebar.classList.toggle('open');
        this.mobileOverlay.classList.toggle('open');
    }

    closeSidebar() {
        this.sidebar.classList.remove('open');
        this.mobileOverlay.classList.remove('open');
    }

    toggleDropdown(dropdown) {
        this.closeAllDropdowns();
        dropdown.classList.toggle('open');
    }

    closeAllDropdowns() {
        document.querySelectorAll('.selector-dropdown').forEach(d => d.classList.remove('open'));
    }

    selectAgent(agentName) {
        this.currentAgent = agentName;
        this.currentAgentName.textContent = agentName;
        this.agentDropdown.querySelectorAll('.selector-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.agent === agentName);
        });
        this.agentList.querySelectorAll('.nav-item').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.agent === agentName);
        });
        this.closeAllDropdowns();
        this.closeSidebar();
        this.newSession(); // Start new conversation with new agent
    }

    selectModel(modelName) {
        this.currentModel = modelName;
        this.currentModelName.textContent = modelName;
        this.modelDropdown.querySelectorAll('.selector-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.model === modelName);
        });
        this.closeAllDropdowns();
    }

    async newSession() {
        this.currentConversationId = null;
        this.messageHistory = [];
        this.messagesContainer.innerHTML = '';
        this.welcomeMessage.style.display = 'flex';
        this.updateSessionList();
    }

    async loadSessions() {
        try {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();
            this.renderSessionList(sessions);
        } catch (e) {
            console.error('Failed to load sessions:', e);
        }
    }

    renderSessionList(sessions) {
        this.sessionList.innerHTML = sessions.map(s => `
            <li>
                <button class="nav-item" data-session="${s.conversation_id}" title="${s.agent} • ${s.message_count} messages">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                    ${s.agent} • ${new Date(s.updated_at).toLocaleString()}
                </button>
            </li>
        `).join('');

        this.sessionList.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', () => this.loadSession(btn.dataset.session));
        });
    }

    async loadSession(conversationId) {
        try {
            const response = await fetch(`/api/sessions/${conversationId}`);
            const session = await response.json();

            this.currentConversationId = session.conversation_id;
            this.currentAgent = session.agent;
            this.currentModel = session.model;
            this.currentAgentName.textContent = session.agent;
            this.currentModelName.textContent = session.model;

            // Update UI
            this.agentDropdown.querySelectorAll('.selector-option').forEach(opt => {
                opt.classList.toggle('selected', opt.dataset.agent === session.agent);
            });
            this.modelDropdown.querySelectorAll('.selector-option').forEach(opt => {
                opt.classList.toggle('selected', opt.dataset.model === session.model);
            });

            // Load messages - would need a messages endpoint
            this.welcomeMessage.style.display = 'none';
            this.messagesContainer.innerHTML = '';

            // For now just show session info
            this.addSystemMessage(`Loaded session: ${session.conversation_id.slice(0, 8)}... (${session.message_count} messages)`);
            this.closeSidebar();
        } catch (e) {
            console.error('Failed to load session:', e);
            this.addErrorMessage('Failed to load session');
        }
    }

    updateSessionList() {
        this.loadSessions();
    }

    handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.sendMessage();
        }
    }

    autoResize() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 200) + 'px';
    }

    async sendMessage() {
        const text = this.messageInput.value.trim();
        if (!text || this.isStreaming) return;

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.sendBtn.disabled = true;
        this.isStreaming = true;

        // Hide welcome message
        this.welcomeMessage.style.display = 'none';

        // Add user message
        this.addMessage('user', text);

        try {
            // Create new session if needed
            if (!this.currentConversationId) {
                this.currentConversationId = crypto.randomUUID();
            }

            // Send via WebSocket for streaming
            await this.sendViaWebSocket(text);
        } catch (e) {
            console.error('Send error:', e);
            this.addErrorMessage('Failed to send message');
        } finally {
            this.sendBtn.disabled = false;
            this.isStreaming = false;
        }
    }

    async sendViaWebSocket(message) {
        const ws = new WebSocket(`ws://${location.host}/api/chat/stream`);

        ws.onopen = () => {
            ws.send(JSON.stringify({
                message,
                agent: this.currentAgent,
                model: this.currentModel,
                temperature: parseFloat(this.tempSlider?.value || '0.7'),
                max_tokens: parseInt(this.maxTokensInput?.value || '4096'),
                conversation_id: this.currentConversationId,
                stream: true
            }));
        };

        let assistantMessageEl = null;
        let accumulatedContent = '';

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.error) {
                    this.addErrorMessage(data.error);
                    ws.close();
                    return;
                }

                if (!assistantMessageEl) {
                    assistantMessageEl = this.addMessage('assistant', '');
                }

                accumulatedContent += data.content;
                this.updateMessageContent(assistantMessageEl, accumulatedContent);

                if (data.complete) {
                    ws.close();
                    this.messageHistory.push({ role: 'user', content: message });
                    this.messageHistory.push({ role: 'assistant', content: accumulatedContent });
                    this.updateSessionList();
                }
            } catch (e) {
                console.error('WS message error:', e);
            }
        };

        ws.onerror = (e) => {
            console.error('WebSocket error:', e);
            this.addErrorMessage('Connection error');
        };

        ws.onclose = () => {
            this.sendBtn.disabled = false;
            this.isStreaming = false;
        };
    }

    addMessage(role, content) {
        const wrapper = document.createElement('div');
        wrapper.className = `message ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'AI';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        const header = document.createElement('div');
        header.className = 'message-header';
        header.innerHTML = `
            <span class="message-role">${role === 'user' ? 'You' : 'AI'}</span>
            <span class="message-time">${new Date().toLocaleTimeString()}</span>
        `;

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = content;

        contentDiv.appendChild(header);
        contentDiv.appendChild(textDiv);
        wrapper.appendChild(avatar);
        wrapper.appendChild(contentDiv);

        this.messagesContainer.appendChild(wrapper);
        this.scrollToBottom();

        return textDiv; // Return text div for streaming updates
    }

    updateMessageContent(textDiv, content) {
        textDiv.textContent = content;
        this.scrollToBottom();
    }

    addSystemMessage(content) {
        const div = document.createElement('div');
        div.className = 'message system';
        div.innerHTML = `<div class="message-text" style="color: var(--fg-secondary); font-style: italic;">${content}</div>`;
        this.messagesContainer.appendChild(div);
        this.scrollToBottom();
    }

    addErrorMessage(content) {
        const div = document.createElement('div');
        div.className = 'message error';
        div.innerHTML = `<div class="message-text" style="color: var(--error);">❌ ${content}</div>`;
        this.messagesContainer.appendChild(div);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    clearChat() {
        this.messagesContainer.innerHTML = '';
        this.welcomeMessage.style.display = 'flex';
        this.messageHistory = [];
        this.currentConversationId = null;
    }

    insertCodeBlock() {
        const text = '\n```python\n\n```\n';
        this.messageInput.value += text;
        this.messageInput.focus();
        this.autoResize();
    }

    openSettings() {
        this.settingsModal.classList.add('open');
        this.settingsModal.style.display = 'flex';
    }

    closeSettings() {
        this.settingsModal.classList.remove('open');
        setTimeout(() => {
            if (!this.settingsModal.classList.contains('open')) {
                this.settingsModal.style.display = 'none';
            }
        }, 200);
    }

    saveSettings() {
        // Settings are applied on next send
        this.closeSettings();
        this.addSystemMessage('Settings saved');
    }

    showContextMenu(e) {
        // Only show on message text
        if (e.target.closest('.message-text')) {
            e.preventDefault();
            this.contextMenu.style.left = `${e.pageX}px`;
            this.contextMenu.style.top = `${e.pageY}px`;
            this.contextMenu.classList.add('open');
        }
    }

    hideContextMenu() {
        this.contextMenu.classList.remove('open');
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new EverlayApp();
});