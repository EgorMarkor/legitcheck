(function () {
  const state = {
    conversations: [],
    selectedPeerId: null,
    config: null,
    pollTimer: null,
  };

  const shell = document.querySelector("[data-app-shell]");
  const connectionStatus = document.querySelector("[data-connection-status]");
  const conversationList = document.querySelector("[data-conversation-list]");
  const chatTitle = document.querySelector("[data-chat-title]");
  const chatLink = document.querySelector("[data-chat-link]");
  const chatAvatar = document.querySelector("[data-chat-avatar]");
  const messageList = document.querySelector("[data-message-list]");
  const composer = document.querySelector("[data-composer]");
  const messageInput = document.querySelector("[data-message-input]");
  const syncButton = document.querySelector("[data-sync-button]");
  const pushButton = document.querySelector("[data-push-button]");
  const pushStatus = document.querySelector("[data-push-status]");
  const backButton = document.querySelector("[data-back-button]");

  init();

  function init() {
    const url = new URL(window.location.href);
    const peerFromUrl = url.searchParams.get("peer_id");

    if (peerFromUrl) {
      state.selectedPeerId = Number(peerFromUrl);
    }

    composer.addEventListener("submit", handleSend);
    syncButton.addEventListener("click", handleSync);
    pushButton.addEventListener("click", handlePushSubscribe);
    backButton.addEventListener("click", () => shell.classList.remove("chat-open"));
    messageInput.addEventListener("input", autoGrowComposer);

    boot();
  }

  async function boot() {
    setConnectionStatus("Загрузка");
    setMessagePlaceholder("Загрузка");

    try {
      state.config = await apiGet("/vkchat/api/config/");
      updatePushStatus();
      await loadConversations();
      startPolling();
      setConnectionStatus("Онлайн");
    } catch (error) {
      handleApiError(error);
    }
  }

  function startPolling() {
    window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(async () => {
      try {
        await loadConversations(false);
        if (state.selectedPeerId) {
          await loadMessages(state.selectedPeerId, false);
        }
        setConnectionStatus("Онлайн");
      } catch (error) {
        setConnectionStatus("Нет связи");
      }
    }, 6000);
  }

  async function loadConversations(showLoading) {
    if (showLoading !== false) {
      conversationList.innerHTML = '<div class="loading-state">Загрузка</div>';
    }

    const data = await apiGet("/vkchat/api/conversations/");
    state.conversations = data.conversations || [];
    renderConversations();

    if (!state.selectedPeerId && state.conversations.length) {
      state.selectedPeerId = state.conversations[0].peer_id;
    }

    if (state.selectedPeerId) {
      await loadMessages(state.selectedPeerId, showLoading);
    } else {
      renderEmptyChat();
    }
  }

  async function loadMessages(peerId, showLoading) {
    if (showLoading !== false) {
      setMessagePlaceholder("Загрузка");
    }

    const data = await apiGet(`/vkchat/api/conversations/${peerId}/messages/`);
    state.selectedPeerId = Number(peerId);
    state.conversations = state.conversations.map((conversation) => {
      if (Number(conversation.peer_id) === Number(peerId)) {
        return { ...conversation, unread_count: 0 };
      }
      return conversation;
    });
    renderChatHeader(data.conversation);
    renderMessages(data.messages || []);
    renderConversations();

    apiPost(`/vkchat/api/conversations/${peerId}/read/`, {}).catch(() => {});
  }

  function renderConversations() {
    if (!state.conversations.length) {
      conversationList.innerHTML = '<div class="empty-state">Диалогов нет</div>';
      return;
    }

    conversationList.innerHTML = "";
    state.conversations.forEach((conversation) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "conversation-item";
      if (Number(conversation.peer_id) === Number(state.selectedPeerId)) {
        button.classList.add("is-active");
      }

      button.innerHTML = `
        ${avatarMarkup(conversation, "avatar")}
        <span class="conversation-main">
          <span class="conversation-top">
            <span class="conversation-title">${escapeHtml(conversation.title)}</span>
            <span class="conversation-time">${formatTime(conversation.last_message_at)}</span>
          </span>
          <span class="conversation-preview">${escapeHtml(conversation.last_message_text || "")}</span>
        </span>
        ${conversation.unread_count ? `<span class="unread-badge">${conversation.unread_count}</span>` : "<span></span>"}
      `;

      button.addEventListener("click", async () => {
        shell.classList.add("chat-open");
        await loadMessages(conversation.peer_id);
      });

      conversationList.appendChild(button);
    });
  }

  function renderChatHeader(conversation) {
    chatTitle.textContent = conversation.title || `id${conversation.from_id}`;
    chatLink.textContent = conversation.vk_url ? conversation.vk_url.replace("https://", "") : "";
    chatLink.href = conversation.vk_url || "#";
    chatLink.hidden = !conversation.vk_url;
    chatAvatar.innerHTML = avatarInnerMarkup(conversation);
    composer.classList.remove("is-hidden");
  }

  function renderMessages(messages) {
    if (!messages.length) {
      setMessagePlaceholder("Сообщений нет");
      return;
    }

    messageList.innerHTML = "";
    messages.forEach((message) => {
      const row = document.createElement("div");
      row.className = `message-row ${message.direction === "outgoing" ? "outgoing" : "incoming"}`;
      row.innerHTML = `
        <div class="message-bubble">
          ${message.text ? `<div class="message-text">${escapeHtml(message.text)}</div>` : ""}
          ${attachmentsMarkup(message.attachments || [])}
          <div class="message-time">${formatTime(message.created_at)}</div>
        </div>
      `;
      messageList.appendChild(row);
    });
    messageList.scrollTop = messageList.scrollHeight;
  }

  function renderEmptyChat() {
    chatTitle.textContent = "Выберите диалог";
    chatLink.hidden = true;
    chatAvatar.innerHTML = "";
    composer.classList.add("is-hidden");
    setMessagePlaceholder("Нет выбранного диалога");
  }

  function setMessagePlaceholder(text) {
    messageList.innerHTML = `<div class="empty-state">${escapeHtml(text)}</div>`;
  }

  async function handleSend(event) {
    event.preventDefault();
    const text = messageInput.value.trim();
    if (!text || !state.selectedPeerId) return;

    const submitButton = composer.querySelector("button");
    submitButton.disabled = true;

    try {
      await apiPost(`/vkchat/api/conversations/${state.selectedPeerId}/messages/`, { text });
      messageInput.value = "";
      autoGrowComposer();
      await loadMessages(state.selectedPeerId, false);
      await loadConversations(false);
    } catch (error) {
      alert(error.message || "Не удалось отправить сообщение");
    } finally {
      submitButton.disabled = false;
      messageInput.focus();
    }
  }

  async function handleSync() {
    syncButton.disabled = true;
    setConnectionStatus("Синхронизация");
    try {
      await apiPost("/vkchat/api/sync/", {});
      await loadConversations(false);
      setConnectionStatus("Онлайн");
    } catch (error) {
      handleApiError(error);
    } finally {
      syncButton.disabled = false;
    }
  }

  async function handlePushSubscribe() {
    if (!state.config || !state.config.vapid_public_key) {
      setPushStatus("Push не настроен на сервере", "error");
      return;
    }

    if (!window.isSecureContext) {
      setPushStatus("Push доступен только через HTTPS", "error");
      return;
    }

    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      setPushStatus("Push не поддерживается этим браузером", "error");
      return;
    }

    pushButton.disabled = true;
    try {
      const registration = await navigator.serviceWorker.register("/sw.js");
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setPushStatus("Уведомления выключены", "error");
        return;
      }

      const existingSubscription = await registration.pushManager.getSubscription();
      const subscription = existingSubscription || await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(state.config.vapid_public_key),
      });

      await apiPost("/vkchat/api/push/subscribe/", subscription.toJSON());
      setPushStatus("Уведомления включены", "success");
    } catch (error) {
      setPushStatus(error.message || "Не удалось включить уведомления", "error");
    } finally {
      pushButton.disabled = false;
    }
  }

  function updatePushStatus() {
    if (!window.isSecureContext) {
      setPushStatus("Push доступен только через HTTPS", "error");
      return;
    }
    if (!state.config || !state.config.push_configured) {
      setPushStatus("Push не настроен", "error");
      return;
    }
    if (!("Notification" in window)) {
      setPushStatus("Уведомления не поддерживаются", "error");
      return;
    }
    if (Notification.permission === "granted") {
      setPushStatus("Уведомления включены", "success");
    } else if (Notification.permission === "denied") {
      setPushStatus("Уведомления выключены", "error");
    } else {
      setPushStatus("");
    }
  }

  async function apiGet(url) {
    return apiFetch(url, { method: "GET" });
  }

  async function apiPost(url, payload) {
    return apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  }

  async function apiFetch(url, options) {
    const headers = {
      ...(options.headers || {}),
    };

    if ((options.method || "GET").toUpperCase() !== "GET") {
      headers["X-CSRFToken"] = getCsrfToken();
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function handleApiError(error) {
    if (error.status === 401 || error.status === 403) {
      window.location.href = `/admin/login/?next=${encodeURIComponent("/vkchat/")}`;
      return;
    }
    setConnectionStatus("Ошибка");
  }

  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function autoGrowComposer() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 132)}px`;
  }

  function setConnectionStatus(text) {
    connectionStatus.textContent = text;
  }

  function setPushStatus(text, type) {
    pushStatus.textContent = text || "";
    pushStatus.dataset.type = type || "";
    pushStatus.style.color = type === "success" ? "var(--success)" : type === "error" ? "var(--danger)" : "";
  }

  function avatarMarkup(conversation, className) {
    return `<span class="${className}">${avatarInnerMarkup(conversation)}</span>`;
  }

  function avatarInnerMarkup(conversation) {
    if (conversation.avatar_url) {
      return `<img src="${escapeAttribute(conversation.avatar_url)}" alt="">`;
    }
    return escapeHtml(initials(conversation.title || String(conversation.from_id || "")));
  }

  function initials(name) {
    return String(name || "VK")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0] || "")
      .join("")
      .toUpperCase() || "VK";
  }

  function attachmentsMarkup(attachments) {
    if (!attachments.length) return "";
    const items = attachments.map((attachment) => {
      const label = attachment.type || "attachment";
      if (attachment.type === "photo" && attachment.url) {
        return `<a href="${escapeAttribute(attachment.url)}" target="_blank" rel="noreferrer"><img class="attachment-image" src="${escapeAttribute(attachment.url)}" alt=""></a>`;
      }
      if (attachment.url) {
        return `<a class="attachment-link" href="${escapeAttribute(attachment.url)}" target="_blank" rel="noreferrer">${escapeHtml(attachment.title || label)}</a>`;
      }
      return `<span class="attachment-label">${escapeHtml(label)}</span>`;
    });
    return `<div class="attachment-list">${items.join("")}</div>`;
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
    }).format(date);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i += 1) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }
})();
