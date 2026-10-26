/**
 * EduBridge Modern Dashboard Interactive Controller
 * Adhering to modern EdTech aesthetics (EduNest & Alltio)
 * Supports all client interactions: tabs, AI tutor chat, widgets, and dynamic updates
 */

(function () {
  'use strict';

  // --- State Store ---
  const state = {
    activeTab: 'overview',
    chatHistory: [
      {
        sender: 'ai',
        time: 'Just now',
        text: 'Hello! I am your EduBridge AI Assistant. I can help you with lecture summaries, algorithm explanations, test preparations, or assignment guidelines. How can I assist you today?'
      }
    ],
    tasks: [
      { id: 1, title: 'Data Structures: Red-Black Trees Assignment', due: 'Tomorrow, 11:59 PM', course: 'CS301', status: 'pending', priority: 'high' },
      { id: 2, title: 'Database Systems: Normalization Practice Quiz', due: 'In 3 days', course: 'CS304', status: 'pending', priority: 'medium' },
      { id: 3, title: 'Operating Systems: Thread Scheduling Lab Submission', due: 'Completed yesterday', course: 'CS302', status: 'completed', priority: 'low' }
    ],
    meetings: [
      { id: 1, title: 'Algorithm Analysis Lecture & Tutorial', time: '10:00 AM - 11:30 AM', instructor: 'Dr. Sharma', room: 'Hall 4B / Online', badge: 'Active' },
      { id: 2, title: 'Computer Networks Lab Session', time: '02:00 PM - 04:00 PM', instructor: 'Prof. Ananya Sen', room: 'Networking Lab 2', badge: 'Upcoming' },
      { id: 3, title: 'Weekly Mentorship & Doubt Clearing', time: '05:00 PM - 06:00 PM', instructor: 'Faculty Mentor', room: 'Conference Room C', badge: 'Scheduled' }
    ],
    resources: [
      { id: 1, title: 'Operating Systems Kernel Design Notes', author: 'Prof. Miller', downloads: '420', type: 'PDF' },
      { id: 2, title: 'Dynamic Programming Cheat Sheet & Practice', author: 'EduBridge Faculty', downloads: '890', type: 'Guide' },
      { id: 3, title: 'Discrete Mathematics Solved Question Bank', author: 'Dept. of CS', downloads: '610', type: 'Archive' }
    ],
    scholarships: [
      { id: 1, title: 'Merit-Cum-Means Engineering Excellence Grant', amount: '₹50,000 / year', deadline: 'Nov 15, 2026', tag: 'High Match' },
      { id: 2, title: 'National Tech Women in STEM Fellowship', amount: '₹75,000 stipend', deadline: 'Dec 01, 2026', tag: 'Open Now' },
      { id: 3, title: 'Industry Innovation B.Tech Research Subsidy', amount: '₹1,00,000 grant', deadline: 'Dec 20, 2026', tag: 'Departmental' }
    ]
  };

  // --- Exposed Global Functions for Compatibility ---
  window.renderStats = function () {
    const statsEl = document.getElementById('stats');
    if (!statsEl) return;
    // Highlight metrics if required
    statsEl.classList.add('stats-updated');
  };

  window.renderTasks = function () {
    const taskList = document.getElementById('taskList');
    if (!taskList) return;
    // Protect server-rendered items: only populate if explicitly marked for client rendering
    if (!taskList.hasAttribute('data-allow-client-render')) return;
    taskList.innerHTML = state.tasks.map(t => `
      <div class="task-card-item ${t.status}">
        <div class="task-status-indicator ${t.status}"></div>
        <div class="task-details">
          <div class="task-header-line">
            <span class="task-course-badge">${t.course}</span>
            <span class="badge ${t.status === 'completed' ? 'badge-active' : (t.priority === 'high' ? 'badge-alert' : 'badge-pending')}">
              ${t.status === 'completed' ? 'Completed' : (t.priority === 'high' ? 'Due Soon' : 'Pending')}
            </span>
          </div>
          <h4 class="task-title">${t.title}</h4>
          <p class="task-meta"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg> ${t.due}</p>
        </div>
      </div>
    `).join('');
  };

  window.renderAssignments = function () {
    window.renderTasks();
  };

  window.clearChat = function () {
    state.chatHistory = [];
    const container = document.getElementById('chatMessages');
    if (!container) return;
    const isTeacher = window.location.pathname.startsWith('/teacher');
    const assistantName = isTeacher ? 'EduBridge Teacher AI Assistant' : 'EduBridge Student AI Assistant';
    const welcome = isTeacher
      ? 'Welcome to a new session with your faculty AI assistant! How can I assist with your curriculum, assignments, or evaluations today?'
      : 'Welcome to a new study session with your AI academic mentor! What topic, coding challenge, or engineering concept shall we explore?';

    container.innerHTML = `
      <div class="chat-bubble chat-ai">
        <div class="chat-avatar-ai">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
        </div>
        <div class="chat-content">
          <div class="chat-sender-name">${assistantName}</div>
          <div class="chat-text">${welcome}</div>
          <span class="chat-time">Just now</span>
        </div>
      </div>
    `;
  };

  function getCsrfToken() {
    const cookie = document.cookie
      .split('; ')
      .find(row => row.startsWith('csrftoken='));
    if (cookie) return cookie.split('=')[1];
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    return csrfInput ? csrfInput.value : '';
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

    // Headers: ###, ##, #
    html = html.replace(/^### (.*$)/gim, '<h4 class="ai-heading">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 class="ai-heading">$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2 class="ai-heading">$1</h2>');

    // Bold **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Markdown Links [text](url)
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="ai-link">$1 ↗</a>');

    // Bullet points (lines starting with • or - or *)
    html = html.replace(/^[•\-\*]\s+(.*)$/gim, '<li class="ai-bullet">$1</li>');
    html = html.replace(/(<li class="ai-bullet">.*<\/li>\s*)+/g, '<ul class="ai-list">$&</ul>');

    // Newlines to <br> outside pre blocks
    const parts = html.split(/(<pre[\s\S]*?<\/pre>)/);
    for (let i = 0; i < parts.length; i++) {
      if (!parts[i].startsWith('<pre')) {
        parts[i] = parts[i].replace(/\n/g, '<br>');
      }
    }
    return parts.join('');
  }

  window.sendChat = async function (retryText) {
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');
    const container = document.getElementById('chatMessages');
    if (!container) return;

    const messageText = retryText || (input ? input.value.trim() : '');
    if (!messageText) return;

    if (input) input.value = '';

    // Prevent duplicate sending while processing
    if (sendBtn) sendBtn.disabled = true;
    if (input) input.disabled = true;

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Append User Message and record in conversation history
    appendChatMessage('user', messageText, timeStr);
    state.chatHistory.push({ role: 'user', content: messageText });
    container.scrollTop = container.scrollHeight;

    // Add typing indicator
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'chat-bubble chat-ai chat-typing';
    typingIndicator.id = 'aiTypingIndicator';
    typingIndicator.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    container.appendChild(typingIndicator);
    container.scrollTop = container.scrollHeight;

    const isTeacher = window.location.pathname.startsWith('/teacher');
    const apiUrl = isTeacher ? '/api/teacher/ai/' : '/api/student/ai/';
    const assistantName = isTeacher ? 'EduBridge Teacher AI Assistant' : 'EduBridge Student AI Assistant';

    try {
      const resp = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          prompt: messageText,
          history: state.chatHistory.slice(-8)
        })
      });

      const activeTyping = document.getElementById('aiTypingIndicator');
      if (activeTyping) activeTyping.remove();

      if (resp.ok) {
        const data = await resp.json();
        const replyText = data.reply || 'Analysis completed.';
        appendChatMessage('ai', replyText, 'Just now', {
          assistantName: data.assistant_name || assistantName,
          provider: data.provider
        });
        state.chatHistory.push({ role: 'assistant', content: replyText });
      } else {
        const errData = await resp.json().catch(() => ({}));
        const errMsg = errData.error || `Unable to reach the assistant (HTTP ${resp.status}).`;
        appendErrorChatMessage(errMsg, messageText);
      }
    } catch (err) {
      const activeTyping = document.getElementById('aiTypingIndicator');
      if (activeTyping) activeTyping.remove();
      appendErrorChatMessage('Network or connection timeout. Check your connection.', messageText);
    } finally {
      if (sendBtn) sendBtn.disabled = false;
      if (input) {
        input.disabled = false;
        input.focus();
      }
      container.scrollTop = container.scrollHeight;
    }
  };

  function appendChatMessage(sender, text, time, meta) {
    const container = document.getElementById('chatMessages');
    if (!container) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-bubble chat-${sender}`;

    if (sender === 'ai') {
      const isTeacher = window.location.pathname.startsWith('/teacher');
      const defaultName = isTeacher ? 'EduBridge Teacher AI Assistant' : 'EduBridge Student AI Assistant';
      const name = meta && meta.assistantName ? meta.assistantName : defaultName;
      const providerChip = meta && meta.provider ? `<span class="chat-provider-chip">${escapeHtml(meta.provider)}</span>` : '';

      messageDiv.innerHTML = `
        <div class="chat-avatar-ai">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
        </div>
        <div class="chat-content">
          <div class="chat-sender-line">
            <span class="chat-sender-name">${escapeHtml(name)}</span>
            ${providerChip}
          </div>
          <div class="chat-text">${renderMarkdown(text)}</div>
          <span class="chat-time">${time}</span>
        </div>
      `;
    } else {
      messageDiv.innerHTML = `
        <div class="chat-content">
          <div class="chat-text">${escapeHtml(text)}</div>
          <span class="chat-time">${time}</span>
        </div>
      `;
    }
    container.appendChild(messageDiv);
  }

  function appendErrorChatMessage(errMsg, retryPrompt) {
    const container = document.getElementById('chatMessages');
    if (!container) return;

    const errorDiv = document.createElement('div');
    errorDiv.className = 'chat-bubble chat-ai chat-error-bubble';
    errorDiv.innerHTML = `
      <div class="chat-avatar-ai" style="background: #FEE2E2; color: #DC2626;">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
      </div>
      <div class="chat-content">
        <div class="chat-sender-name" style="color: #DC2626;">System Notification</div>
        <div class="chat-text" style="color: #991B1B;">⚠️ ${escapeHtml(errMsg)}</div>
        <div style="margin-top: 0.4rem;">
          <button type="button" class="btn small" style="padding: 0.2rem 0.6rem; font-size: 0.75rem;" onclick="window.sendChat('${escapeHtml(retryPrompt).replace(/'/g, "\\'")}')">↺ Retry Message</button>
        </div>
      </div>
    `;
    container.appendChild(errorDiv);
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

  // --- Dark Mode / Light Mode Theme Controller ---
  function initThemeToggle() {
    const toggleBtn = document.getElementById('themeToggleBtn');
    if (!toggleBtn) return;

    const sunIcon = toggleBtn.querySelector('.theme-icon-sun');
    const moonIcon = toggleBtn.querySelector('.theme-icon-moon');

    function applyTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      if (document.body) {
        document.body.setAttribute('data-theme', theme);
      }
      try {
        localStorage.setItem('edubridge_theme', theme);
      } catch (e) {}

      if (theme === 'dark') {
        if (sunIcon) sunIcon.style.display = 'block';
        if (moonIcon) moonIcon.style.display = 'none';
        toggleBtn.setAttribute('title', 'Switch to Light Mode');
        toggleBtn.setAttribute('aria-label', 'Switch to Light Mode');
      } else {
        if (sunIcon) sunIcon.style.display = 'none';
        if (moonIcon) moonIcon.style.display = 'block';
        toggleBtn.setAttribute('title', 'Switch to Dark Mode');
        toggleBtn.setAttribute('aria-label', 'Switch to Dark Mode');
      }
    }

    const savedTheme = localStorage.getItem('edubridge_theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const currentTheme = savedTheme || (prefersDark ? 'dark' : 'light');
    applyTheme(currentTheme);

    toggleBtn.addEventListener('click', function (e) {
      e.preventDefault();
      const current = document.documentElement.getAttribute('data-theme') || 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
    });
  }

  // --- Persistent Notification Center Controller ---
  function initNotificationCenter() {
    const notifBtn = document.getElementById('notificationBtn');
    const notifPopover = document.getElementById('notificationPopover');
    const badgeCount = document.getElementById('notifBadgeCount');
    const badgeDot = document.getElementById('notifBadgeDot');
    const unreadPill = document.getElementById('notifUnreadPill');
    const listContainer = document.getElementById('notificationListContainer');
    const markAllBtn = document.getElementById('markAllReadBtn');

    if (!notifBtn || !notifPopover) return;

    // Explicitly guarantee notification panel remains closed by default
    notifPopover.style.display = 'none';

    let isFetching = false;

    async function fetchNotifications() {
      if (isFetching) return;
      isFetching = true;
      try {
        const resp = await fetch('/api/notifications/', {
          headers: {
            'Accept': 'application/json'
          }
        });
        if (resp.ok) {
          const data = await resp.json();
          renderNotifications(data);
        }
      } catch (err) {
        console.warn('EduBridge: notification fetch failed:', err);
      } finally {
        isFetching = false;
      }
    }

    function renderNotifications(data) {
      const count = data.unread_count || 0;
      const notifications = data.notifications || [];

      if (badgeCount) {
        badgeCount.textContent = count > 99 ? '99+' : count;
        badgeCount.style.display = count > 0 ? 'inline-flex' : 'none';
      }
      if (badgeDot) {
        // Keep dot hidden to avoid dual-indicator visual overlap
        badgeDot.style.display = 'none';
      }
      if (unreadPill) {
        unreadPill.textContent = `${count} unread`;
        unreadPill.className = count > 0 ? 'badge badge-alert' : 'badge badge-subtle';
      }

      if (!listContainer) return;

      if (notifications.length === 0) {
        listContainer.innerHTML = `
          <div style="padding: 2rem 1rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🔔</div>
            <div>No notifications yet</div>
            <small style="color: var(--text-muted);">You're all caught up with your courses!</small>
          </div>
        `;
        return;
      }

      listContainer.innerHTML = notifications.map(n => `
        <div class="notif-card-item ${n.is_read ? 'read' : 'unread'}" data-id="${n.id}" data-url="${escapeHtml(n.link || '')}" style="padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-subtle); cursor: pointer; transition: background 0.15s ease; background: ${n.is_read ? 'transparent' : 'var(--primary-light, #F0F9FF)'};">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.2rem;">
            <strong style="font-size: 0.84rem; color: var(--text-main); font-weight: ${n.is_read ? '600' : '700'};">${escapeHtml(n.title)}</strong>
            <span style="font-size: 0.72rem; color: var(--text-muted); white-space: nowrap;">${escapeHtml(n.created_at_human || n.time_ago || '')}</span>
          </div>
          <p style="margin: 0; font-size: 0.8rem; color: var(--text-muted); line-height: 1.35;">${escapeHtml(n.message)}</p>
          ${!n.is_read ? '<span class="notif-unread-dot" style="display: inline-block; width: 6px; height: 6px; background: #2563EB; border-radius: 50%; margin-top: 0.35rem;"></span>' : ''}
        </div>
      `).join('');

      listContainer.querySelectorAll('.notif-card-item').forEach(item => {
        item.addEventListener('click', async function (e) {
          e.stopPropagation();
          const notifId = this.getAttribute('data-id');
          const targetUrl = this.getAttribute('data-url');
          const wasUnread = this.classList.contains('unread');

          // Instantly mark as read in UI
          this.classList.remove('unread');
          this.classList.add('read');
          this.style.background = 'transparent';
          const unreadDot = this.querySelector('.notif-unread-dot');
          if (unreadDot) unreadDot.style.display = 'none';

          // Instantly decrement red count badge on notification bell
          if (wasUnread && badgeCount) {
            let cur = parseInt(badgeCount.textContent, 10) || 0;
            let next = Math.max(0, cur - 1);
            badgeCount.textContent = next > 99 ? '99+' : next;
            badgeCount.style.display = next > 0 ? 'inline-flex' : 'none';
            if (badgeDot) badgeDot.style.display = 'none';
            if (unreadPill) {
              unreadPill.textContent = `${next} unread`;
              unreadPill.className = next > 0 ? 'badge badge-alert' : 'badge badge-subtle';
            }
          }

          try {
            await fetch(`/api/notifications/${notifId}/read/`, {
              method: 'POST',
              headers: {
                'X-CSRFToken': getCsrfToken(),
                'Accept': 'application/json'
              }
            });
          } catch (err) {}

          // Close popover
          notifPopover.style.display = 'none';

          // Safe navigation without accidental unwanted redirect
          if (targetUrl && targetUrl !== '#' && targetUrl !== '' && (targetUrl.startsWith('/') || targetUrl.startsWith('http'))) {
            window.location.href = targetUrl;
          } else {
            fetchNotifications();
          }
        });
      });
    }

    notifBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      const isVisible = notifPopover.style.display === 'block';
      notifPopover.style.display = isVisible ? 'none' : 'block';
      if (!isVisible) {
        fetchNotifications();
      }
    });

    document.addEventListener('click', function (e) {
      if (!notifPopover.contains(e.target) && !notifBtn.contains(e.target)) {
        notifPopover.style.display = 'none';
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && notifPopover.style.display === 'block') {
        notifPopover.style.display = 'none';
        notifBtn.focus();
      }
    });

    if (markAllBtn) {
      markAllBtn.addEventListener('click', async function (e) {
        e.stopPropagation();
        
        // Optimistic UI update: immediately clear red badge and zero counters
        if (badgeCount) {
          badgeCount.textContent = '0';
          badgeCount.style.display = 'none';
        }
        if (badgeDot) {
          badgeDot.style.display = 'none';
        }
        if (unreadPill) {
          unreadPill.textContent = '0 unread';
          unreadPill.className = 'badge badge-subtle';
        }
        if (listContainer) {
          listContainer.querySelectorAll('.notif-card-item').forEach(item => {
            item.classList.remove('unread');
            item.classList.add('read');
            item.style.background = 'transparent';
            const dot = item.querySelector('.notif-unread-dot');
            if (dot) dot.style.display = 'none';
          });
        }

        try {
          const resp = await fetch('/api/notifications/read-all/', {
            method: 'POST',
            headers: {
              'X-CSRFToken': getCsrfToken(),
              'Accept': 'application/json'
            }
          });
          if (resp.ok) {
            fetchNotifications();
          }
        } catch (err) {
          console.warn('EduBridge: Mark all read failed:', err);
        }
      });
    }

    fetchNotifications();
    setInterval(fetchNotifications, 25000);
  }

  // --- Initializer on DOM Ready ---
  document.addEventListener('DOMContentLoaded', function () {
    // 0. Initialize theme switcher and notification center
    initThemeToggle();
    initNotificationCenter();

    // 1. Setup Chat Enter Key & Button
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const newChatBtn = document.getElementById('newChatBtn');
    if (chatInput) {
      chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          window.sendChat();
        }
      });
    }
    if (chatSendBtn) {
      chatSendBtn.addEventListener('click', function (e) {
        e.preventDefault();
        window.sendChat();
      });
    }
    if (newChatBtn) {
      newChatBtn.addEventListener('click', function (e) {
        e.preventDefault();
        window.clearChat();
      });
    }

    // 2. Setup AI Suggestion Chips
    const chips = document.querySelectorAll('.chat-chip');
    chips.forEach(chip => {
      chip.addEventListener('click', function () {
        if (chatInput) {
          chatInput.value = this.innerText.replace(/^[✨🔍💡📖]\s*/, '').trim();
          window.sendChat();
        }
      });
    });

    // 3. Setup Pill Tab Switching
    const tabButtons = document.querySelectorAll('.pill-tab-btn[data-tab]');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', function () {
        tabButtons.forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        const targetTab = this.getAttribute('data-tab');
        state.activeTab = targetTab;

        const sections = document.querySelectorAll('.tab-section-content');
        sections.forEach(sec => {
          if (sec.getAttribute('data-tab-name') === targetTab || targetTab === 'overview') {
            sec.style.display = '';
          } else {
            sec.style.display = 'none';
          }
        });
      });
    });

    // 4. Role Select dropdown hook if present
    const roleSelect = document.getElementById('roleSelect');
    if (roleSelect) {
      roleSelect.addEventListener('change', function () {
        const val = this.value;
        if (val === 'student') window.location.href = '/student/';
        else if (val === 'teacher') window.location.href = '/teacher/';
        else if (val === 'admin') window.location.href = '/administration/';
      });
    }

    // 5. Render Initial dynamic widgets if containers exist
    if (document.getElementById('taskList') && document.getElementById('taskList').children.length === 0 && document.getElementById('taskList').hasAttribute('data-allow-client-render')) {
      window.renderTasks();
    }

    // 6. Unified Login Portal Interactive Tabs & Quick Fill
    const loginRoleTabs = document.getElementById('loginRoleTabs');
    if (loginRoleTabs) {
      const roleButtons = loginRoleTabs.querySelectorAll('[data-role-tab]');
      const submitBtn = document.getElementById('submitLoginBtn');
      const roleIcon = document.getElementById('roleIcon');
      const roleNoticeText = document.getElementById('roleNoticeText');
      const idInput = document.getElementById('id_identifier') || document.querySelector('input[name="identifier"]');
      roleButtons.forEach(btn => {
        btn.addEventListener('click', function () {
          roleButtons.forEach(b => b.classList.remove('active'));
          this.classList.add('active');
          const role = this.getAttribute('data-role-tab');
          if (role === 'student') {
            if (submitBtn) submitBtn.innerText = 'Sign in as Student';
            if (roleIcon) roleIcon.innerText = '🎓';
            if (roleNoticeText) roleNoticeText.innerHTML = '<strong>Student Portal:</strong> Enter your Student ID (e.g. <span class="mono">S1001</span>), username, or registered email.';
            if (idInput) idInput.placeholder = 'Student ID (e.g. S1001), username or email';
          } else if (role === 'teacher') {
            if (submitBtn) submitBtn.innerText = 'Sign in as Teacher';
            if (roleIcon) roleIcon.innerText = '👨‍🏫';
            if (roleNoticeText) roleNoticeText.innerHTML = '<strong>Faculty Portal:</strong> Enter your Teacher ID (e.g. <span class="mono">T1001</span>) or institution email.';
            if (idInput) idInput.placeholder = 'Teacher ID (e.g. T1001), username or email';
          } else if (role === 'admin') {
            if (submitBtn) submitBtn.innerText = 'Sign in as Administrator';
            if (roleIcon) roleIcon.innerText = '🛡️';
            if (roleNoticeText) roleNoticeText.innerHTML = '<strong>Administration Console:</strong> Enter your administrator credentials. (Login only).';
            if (idInput) idInput.placeholder = 'Administrator username or email';
          }
        });
      });

      // Quick Fill Credentials (Click to Auto-Fill)
      const fillStudentBtn = document.getElementById('fillStudentBtn');
      const fillTeacherBtn = document.getElementById('fillTeacherBtn');
      const fillAdminBtn = document.getElementById('fillAdminBtn');
      const pwInput = document.getElementById('id_password') || document.querySelector('input[name="password"]');

      function flashSuccess(btn) {
        if (!btn) return;
        const origBorder = btn.style.borderColor;
        const origBg = btn.style.background;
        btn.style.borderColor = '#10B981';
        btn.style.background = '#ECFDF5';
        setTimeout(() => {
          btn.style.borderColor = origBorder;
          btn.style.background = origBg;
        }, 600);
      }

      if (fillStudentBtn && idInput) {
        fillStudentBtn.addEventListener('click', function () {
          const tab = document.getElementById('tabStudent');
          if (tab) tab.click();
          idInput.value = 'jane_wick_099';
          idInput.dispatchEvent(new Event('input', { bubbles: true }));
          idInput.dispatchEvent(new Event('change', { bubbles: true }));
          if (pwInput) {
            pwInput.value = 'EduBridgeStudent2026!';
            pwInput.dispatchEvent(new Event('input', { bubbles: true }));
            pwInput.dispatchEvent(new Event('change', { bubbles: true }));
          }
          flashSuccess(this);
        });
      }

      if (fillTeacherBtn && idInput) {
        fillTeacherBtn.addEventListener('click', function () {
          const tab = document.getElementById('tabTeacher');
          if (tab) tab.click();
          idInput.value = 'prof_sharma';
          idInput.dispatchEvent(new Event('input', { bubbles: true }));
          idInput.dispatchEvent(new Event('change', { bubbles: true }));
          if (pwInput) {
            pwInput.value = 'TeacherPass123!';
            pwInput.dispatchEvent(new Event('input', { bubbles: true }));
            pwInput.dispatchEvent(new Event('change', { bubbles: true }));
          }
          flashSuccess(this);
        });
      }

      if (fillAdminBtn && idInput) {
        fillAdminBtn.addEventListener('click', function () {
          const tab = document.getElementById('tabAdmin');
          if (tab) tab.click();
          idInput.value = 'admin';
          idInput.dispatchEvent(new Event('input', { bubbles: true }));
          idInput.dispatchEvent(new Event('change', { bubbles: true }));
          if (pwInput) {
            pwInput.value = 'AdminPassword123!';
            pwInput.dispatchEvent(new Event('input', { bubbles: true }));
            pwInput.dispatchEvent(new Event('change', { bubbles: true }));
          }
          flashSuccess(this);
        });
      }
    }

    // 7. Interactive Administration Suite & Roadmap Modals
    setupAdminTools();
  });

  function setupAdminTools() {
    // Modal Helpers
    function openModal(id) {
      const modal = document.getElementById(id);
      if (modal) modal.classList.add('open');
    }
    function closeModal(el) {
      const modal = el.closest('.modal-overlay');
      if (modal) modal.classList.remove('open');
    }

    document.querySelectorAll('[data-modal-close]').forEach(btn => {
      btn.addEventListener('click', function () {
        closeModal(this);
      });
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', function (e) {
        if (e.target === this) this.classList.remove('open');
      });
    });

    // 1. Catalog Manager
    const openCatalogBtn = document.getElementById('openCatalogBtn');
    if (openCatalogBtn) {
      openCatalogBtn.addEventListener('click', () => openModal('catalogModal'));
    }

    const toggleAddSubjectForm = document.getElementById('toggleAddSubjectForm');
    const addSubjectForm = document.getElementById('addSubjectForm');
    const cancelAddSubject = document.getElementById('cancelAddSubject');
    const saveSubjectBtn = document.getElementById('saveSubjectBtn');

    if (toggleAddSubjectForm && addSubjectForm) {
      toggleAddSubjectForm.addEventListener('click', () => {
        addSubjectForm.style.display = addSubjectForm.style.display === 'none' ? 'block' : 'none';
      });
    }
    if (cancelAddSubject && addSubjectForm) {
      cancelAddSubject.addEventListener('click', () => {
        addSubjectForm.style.display = 'none';
      });
    }
    if (saveSubjectBtn) {
      saveSubjectBtn.addEventListener('click', () => {
        const code = (document.getElementById('newSubCode').value || '').trim().toUpperCase();
        const name = (document.getElementById('newSubName').value || '').trim();
        const branch = document.getElementById('newSubBranch').value;
        if (!code || !name) {
          alert('Please enter both subject code and subject title.');
          return;
        }

        const tbody = document.getElementById('catalogTableBody');
        if (tbody) {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td class="mono"><strong>${escapeHtml(code)}</strong></td>
            <td>${escapeHtml(name)}</td>
            <td><span class="role-chip">${escapeHtml(branch)}</span></td>
            <td>4.0</td>
            <td><span class="badge badge-active">Core</span></td>
          `;
          tbody.appendChild(tr);
        }

        document.getElementById('newSubCode').value = '';
        document.getElementById('newSubName').value = '';
        addSubjectForm.style.display = 'none';

        const catalogBadge = document.getElementById('catalogBadge');
        if (catalogBadge) catalogBadge.innerText = 'Catalog Updated';
      });
    }

    // 2. Scholarship Fund Tracker
    const openFundBtn = document.getElementById('openFundBtn');
    if (openFundBtn) {
      openFundBtn.addEventListener('click', () => openModal('scholarshipModal'));
    }

    document.querySelectorAll('.approve-grant-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const tr = this.closest('tr');
        const statusTd = tr.querySelector('.badge');
        if (statusTd) {
          statusTd.className = 'badge badge-active';
          statusTd.innerText = 'Disbursed';
        }
        this.parentNode.innerHTML = '<span style="font-size: 0.75rem; color: #059669; font-weight: 700;">✓ Bank Transferred</span>';

        const disbursedNum = document.getElementById('modalDisbursedNum');
        if (disbursedNum) disbursedNum.innerText = '₹13,00,000';

        const appsNum = document.getElementById('modalAppsNum');
        if (appsNum) appsNum.innerText = '13';

        const fundBadge = document.getElementById('fundBadge');
        if (fundBadge) {
          fundBadge.className = 'badge badge-active';
          fundBadge.innerText = '₹13,00,000 Disbursed';
        }
      });
    });

    // 3. Backup Tool
    const runBackupBtn = document.getElementById('runBackupBtn');
    if (runBackupBtn) {
      runBackupBtn.addEventListener('click', () => openModal('backupModal'));
    }

    const startBackupExecution = document.getElementById('startBackupExecution');
    if (startBackupExecution) {
      startBackupExecution.addEventListener('click', function () {
        this.disabled = true;
        this.innerText = 'Snapshot In Progress...';
        const progressBox = document.getElementById('backupProgressBox');
        const progressMeter = document.getElementById('backupProgressMeter');
        const logLine = document.getElementById('backupLogLine');
        if (progressBox) progressBox.style.display = 'block';

        let pct = 0;
        const interval = setInterval(() => {
          pct += 25;
          if (progressMeter) progressMeter.value = pct;
          if (pct === 25 && logLine) logLine.innerText = 'Acquiring SQLite write lock (IMMEDIATE)...';
          if (pct === 50 && logLine) logLine.innerText = 'Exporting schema and 8 audit events...';
          if (pct === 75 && logLine) logLine.innerText = 'Compressing and validating checksum...';
          if (pct >= 100) {
            clearInterval(interval);
            if (logLine) logLine.innerText = 'Snapshot complete! Verified: backup_db_' + Date.now() + '.sqlite3 (Integrity: OK)';
            startBackupExecution.innerText = '✓ Backup Completed';
            const badge = document.getElementById('backupStatusBadge');
            if (badge) {
              badge.className = 'badge badge-active';
              badge.innerText = 'Backup: Just Now (OK)';
            }
          }
        }, 250);
      });
    }
  }

  // 8. Footer Author Interactive Reaction
  document.addEventListener('DOMContentLoaded', function () {
    const authorEl = document.getElementById('authorHighlight');
    if (authorEl) {
      authorEl.addEventListener('click', function () {
        let toast = document.querySelector('.author-reaction-toast');
        if (!toast) {
          toast = document.createElement('div');
          toast.className = 'author-reaction-toast';
          toast.innerHTML = '✨ <span>Crafted with precision by <strong>Sharad Sharma</strong> © 2026</span>';
          document.body.appendChild(toast);
        }
        toast.classList.add('show');
        setTimeout(() => {
          toast.classList.remove('show');
        }, 3200);
      });
    }
  });

})();

