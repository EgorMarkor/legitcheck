(function () {
  "use strict";

  var initialized = false;

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function apiPost(url, payload) {
    var response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error("Push API returned " + response.status);
    }
    return response.json();
  }

  function isInstalledPwa() {
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true;
  }

  function nativePushPlugin() {
    var capacitor = window.Capacitor;
    if (!capacitor || typeof capacitor.isNativePlatform !== "function" || !capacitor.isNativePlatform()) {
      return null;
    }
    return capacitor.Plugins && capacitor.Plugins.PushNotifications;
  }

  function safeNavigate(rawUrl) {
    try {
      var target = new URL(rawUrl || "/verdicts/", window.location.origin);
      if (target.origin === window.location.origin) {
        window.location.assign(target.pathname + target.search + target.hash);
      }
    } catch (_) {}
  }

  async function setupNativePush(plugin) {
    await plugin.addListener("registration", function (token) {
      var platform = window.Capacitor.getPlatform();
      apiPost("/api/push/native/register/", {
        platform: platform,
        token: token.value,
      }).catch(function () {});
    });
    await plugin.addListener("registrationError", function (error) {
      console.warn("Push registration failed", error);
    });
    await plugin.addListener("pushNotificationActionPerformed", function (action) {
      safeNavigate(action && action.notification && action.notification.data && action.notification.data.url);
    });

    var permission = await plugin.checkPermissions();
    if (permission.receive === "prompt" || permission.receive === "prompt-with-rationale") {
      permission = await plugin.requestPermissions();
    }
    if (permission.receive === "granted") {
      await plugin.register();
    }
  }

  function base64UrlToUint8Array(value) {
    var padding = "=".repeat((4 - value.length % 4) % 4);
    var base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
    var raw = window.atob(base64);
    return Uint8Array.from(raw, function (character) {
      return character.charCodeAt(0);
    });
  }

  async function subscribeWebPush(registration, vapidPublicKey) {
    var subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64UrlToUint8Array(vapidPublicKey),
      });
    }
    await apiPost("/api/push/web/subscribe/", subscription.toJSON());
  }

  function removePermissionPrompt() {
    var prompt = document.querySelector("[data-checker-push-prompt]");
    if (prompt) prompt.remove();
  }

  function showPermissionPrompt(onAccept) {
    if (document.querySelector("[data-checker-push-prompt]")) return;

    var prompt = document.createElement("section");
    prompt.dataset.checkerPushPrompt = "true";
    prompt.setAttribute("role", "dialog");
    prompt.setAttribute("aria-label", "Разрешить уведомления");
    prompt.innerHTML =
      '<div class="checker-push-prompt__copy">' +
        '<strong>Уведомления о проверке</strong>' +
        '<span>Сообщим, когда вердикт будет готов или понадобятся новые фото.</span>' +
      '</div>' +
      '<div class="checker-push-prompt__actions">' +
        '<button type="button" data-checker-push-later>Позже</button>' +
        '<button type="button" data-checker-push-enable>Разрешить</button>' +
      '</div>';
    document.body.appendChild(prompt);

    prompt.querySelector("[data-checker-push-later]").addEventListener("click", function () {
      sessionStorage.setItem("checker-push-prompt-dismissed", "1");
      removePermissionPrompt();
    });
    prompt.querySelector("[data-checker-push-enable]").addEventListener("click", async function () {
      removePermissionPrompt();
      await onAccept();
    });
  }

  async function setupWebPush(config) {
    if (
      !isInstalledPwa() ||
      !config.web_push_enabled ||
      !config.vapid_public_key ||
      !("serviceWorker" in navigator) ||
      !("PushManager" in window) ||
      !("Notification" in window)
    ) {
      return;
    }

    var registration = await navigator.serviceWorker.ready;
    var requestAndSubscribe = async function () {
      var permission = Notification.permission;
      if (permission === "default") {
        permission = await Notification.requestPermission();
      }
      if (permission === "granted") {
        removePermissionPrompt();
        await subscribeWebPush(registration, config.vapid_public_key);
      }
    };

    if (Notification.permission === "granted") {
      await subscribeWebPush(registration, config.vapid_public_key);
      return;
    }
    if (Notification.permission === "denied") return;

    // Ask on PWA open. Safari/iOS requires the fallback button's direct user gesture.
    try {
      await requestAndSubscribe();
    } catch (_) {}
    if (
      Notification.permission === "default" &&
      sessionStorage.getItem("checker-push-prompt-dismissed") !== "1"
    ) {
      showPermissionPrompt(function () {
        return requestAndSubscribe().catch(function () {});
      });
    }
  }

  async function initialize() {
    if (initialized) return;
    initialized = true;

    var plugin = nativePushPlugin();
    if (plugin) {
      await setupNativePush(plugin);
      return;
    }
    if (!isInstalledPwa()) return;

    var response = await fetch("/api/push/config/", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json" },
    });
    if (!response.ok) return;
    await setupWebPush(await response.json());
  }

  window.addEventListener("load", function () {
    initialize().catch(function (error) {
      console.warn("Push initialization failed", error);
    });
  });
})();
