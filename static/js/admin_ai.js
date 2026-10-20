document.addEventListener('DOMContentLoaded', function () {
    const chatForm = document.getElementById('adminAiForm');
    const chatInput = document.getElementById('adminAiInput');
    const chatMessages = document.getElementById('adminAiMessages');
    const chips = document.querySelectorAll('.admin-prompt-chip');
    const clearBtn = document.getElementById('adminAiClear');

    let conversationHistory = [];

    function getCsrfToken() {
        const cookie = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='));
        if (cookie) {
            return cookie.split('=')[1];
        }
        const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
        return csrfInput ? csrfInput.value : '';
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function renderMarkdown(str) {
        if (!str) return '';
        let html = escapeHtml(str);

        // Code blocks ```lang\n...```
        html = html.replace(/```(?:[a-zA-Z0-9_\-]+)?\n([\s\S]*?)```/g, function (_, code) {
            return '<pre class="ai-code-block"><code>' + code + '</code></pre>';
        });

        // Inline code `code`
        html = html.replace(/`([^`\n]+)`/g, '<code class="ai-inline-code">$1</code>');

        // Headers
        html = html.replace(/^### (.*$)/gim, '<h4 class="ai-heading">$1</h4>');
        html = html.replace(/^## (.*$)/gim, '<h3 class="ai-heading">$1</h3>');

        // Bold and italic
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Links
        html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="ai-link">$1 ↗</a>');

        // Bullets
        html = html.replace(/^[•\-\*]\s+(.*)$/gim, '<li class="ai-bullet">$1</li>');
        html = html.replace(/(<li class="ai-bullet">.*<\/li>\s*)+/g, '<ul class="ai-list">$&</ul>');

        // Newlines
        const parts = html.split(/(<pre[\s\S]*?<\/pre>)/);
        for (let i = 0; i < parts.length; i++) {
            if (!parts[i].startsWith('<pre')) {
                parts[i] = parts[i].replace(/\n/g, '<br>');
            }
        }
        return parts.join('');
    }

    function appendMessage(role, text, meta) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `admin-chat-bubble ${role === 'user' ? 'bubble-user' : 'bubble-assistant'}`;

        const headerDiv = document.createElement('div');
        headerDiv.className = 'bubble-header';
        headerDiv.textContent = role === 'user' ? '👤 Administrator' : '🤖 EduBridge Admin AI Assistant';

        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'bubble-content';
        bodyDiv.innerHTML = role === 'user' ? escapeHtml(text) : renderMarkdown(text);

        msgDiv.appendChild(headerDiv);
        msgDiv.appendChild(bodyDiv);

        if (meta) {
            const footerDiv = document.createElement('div');
            footerDiv.className = 'bubble-meta text-muted small mt-2';
            const domainText = meta.topic ? `Retrieved domain: ${meta.topic.toUpperCase()}` : 'Live Institutional DB';
            const countText = meta.records_found !== undefined ? ` • Records analyzed: ${meta.records_found}` : '';
            const provText = meta.provider ? ` • ${meta.provider}` : '';
            footerDiv.textContent = `${domainText}${countText}${provText}`;
            msgDiv.appendChild(footerDiv);
        }

        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendErrorMessage(errMsg, retryPrompt) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'admin-chat-bubble bubble-assistant';
        msgDiv.style.borderLeft = '3px solid #DC2626';

        msgDiv.innerHTML = `
            <div class="bubble-header" style="color: #DC2626;">⚠️ EduBridge Admin AI Assistant Notification</div>
            <div class="bubble-content" style="color: #991B1B;">${escapeHtml(errMsg)}</div>
            <div style="margin-top: 0.5rem;">
                <button type="button" class="btn btn-secondary btn-sm" id="adminRetryBtn">↺ Retry Query</button>
            </div>
        `;
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        const retryBtn = msgDiv.querySelector('#adminRetryBtn');
        if (retryBtn) {
            retryBtn.addEventListener('click', function () {
                msgDiv.remove();
                handleSend(retryPrompt);
            });
        }
    }

    async function handleSend(promptText) {
        const text = promptText || (chatInput ? chatInput.value.trim() : '');
        if (!text) return;

        appendMessage('user', text);
        conversationHistory.push({ role: 'user', content: text });
        if (chatInput) chatInput.value = '';

        // Disable input during request
        if (chatInput) chatInput.disabled = true;
        const submitBtn = chatForm ? chatForm.querySelector('button[type="submit"]') : null;
        if (submitBtn) submitBtn.disabled = true;

        // Add loading placeholder
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'admin-chat-bubble bubble-assistant bubble-loading';
        loadingDiv.id = 'aiLoadingBubble';
        loadingDiv.innerHTML = '<div class="bubble-header">🤖 EduBridge Admin AI Assistant</div><div class="bubble-content"><em>Querying institutional database and synthesizing analytical insights...</em></div>';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const resp = await fetch('/administration/api/ai/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    prompt: text,
                    history: conversationHistory.slice(-8)
                })
            });

            const loadingEl = document.getElementById('aiLoadingBubble');
            if (loadingEl) loadingEl.remove();

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                appendErrorMessage(`Processing error (${resp.status}): ${err.error || 'Server error processing admin AI query.'}`, text);
                return;
            }

            const data = await resp.json();
            appendMessage('assistant', data.reply, {
                topic: data.topic,
                records_found: data.records_found,
                provider: data.provider
            });
            conversationHistory.push({ role: 'assistant', content: data.reply });
        } catch (err) {
            const loadingEl = document.getElementById('aiLoadingBubble');
            if (loadingEl) loadingEl.remove();
            appendErrorMessage('Network or security timeout: Unable to contact the administrator AI service.', text);
        } finally {
            if (chatInput) {
                chatInput.disabled = false;
                chatInput.focus();
            }
            if (submitBtn) submitBtn.disabled = false;
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    if (chatForm) {
        chatForm.addEventListener('submit', function (e) {
            e.preventDefault();
            handleSend();
        });
    }

    chips.forEach(chip => {
        chip.addEventListener('click', function () {
            const prompt = this.getAttribute('data-prompt');
            if (prompt) {
                handleSend(prompt);
            }
        });
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            conversationHistory = [];
            chatMessages.innerHTML = `
                <div class="admin-chat-bubble bubble-assistant">
                    <div class="bubble-header">🤖 EduBridge Admin AI Assistant</div>
                    <div class="bubble-content">
                        Session cleared. I am ready to analyze B.Tech student metrics, teacher activities, assessment participation, and scholarship opportunities. How may I assist your administration today?
                    </div>
                </div>
            `;
        });
    }
});
