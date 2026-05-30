(function () {
  "use strict";

  var CONTAINER_SELECTOR = "#page-content";
  var READY_EVENT = "app:page-ready";
  var STATE_INDEX = "__appNavIndex";
  var SCROLL_PREFIX = "app:scroll:";
  var BLOCKED_EXACT_PATHS = {
    "/": true,
    "/payment": true,
    "/payment/": true,
    "/email-login": true,
    "/email-login/": true
  };
  var BLOCKED_PREFIXES = [
    "/admin/",
    "/api/",
    "/payment/",
    "/email/",
    "/checkout",
    "/login",
    "/logout",
    "/yookassa/",
    "/static/",
    "/media/"
  ];

  var root = document.documentElement;
  var currentIndex = getHistoryIndex(history.state);
  var isNavigating = false;
  var activeController = null;
  var initialReadySent = false;
  var scrollSaveQueued = false;
  var loadedExternalScripts = new Set(
    Array.prototype.slice.call(document.scripts)
      .filter(function (script) { return script.src; })
      .map(function (script) { return absoluteUrl(script.src); })
  );

  installTelegramBackButtonProxy();
  ensureHistoryState();
  document.addEventListener("touchstart", function () {}, false);

  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }

  document.addEventListener("click", handleDocumentClick, true);
  window.addEventListener("popstate", handlePopState);
  window.addEventListener("beforeunload", saveScrollPosition);
  window.addEventListener("scroll", queueScrollSave, { passive: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", dispatchInitialReady, { once: true });
  } else {
    dispatchInitialReady();
  }

  function dispatchInitialReady() {
    if (initialReadySent) return;
    var container = document.querySelector(CONTAINER_SELECTOR);
    if (!container) return;
    initialReadySent = true;
    initKnownComponents(container);
    dispatchPageReady(container);
  }

  function handleDocumentClick(event) {
    if (!document.querySelector(CONTAINER_SELECTOR)) return;
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    var target = event.target.closest
      ? event.target.closest("a[href], [data-spa-href], [onclick*=\"location\"]")
      : null;
    if (!target) return;

    var url = getNavigationUrl(target);
    if (!url || !shouldHandleNavigation(target, url)) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    navigateTo(url, { direction: "forward", source: "click" });
  }

  function getNavigationUrl(target) {
    if (target.matches && target.matches("a[href]")) {
      return safeUrl(target.href);
    }

    var spaHref = target.getAttribute("data-spa-href");
    if (spaHref) {
      return safeUrl(spaHref);
    }

    var onclick = target.getAttribute("onclick") || "";
    var match = onclick.match(/(?:window\.)?location(?:\.href)?\s*=\s*(['"])(.*?)\1/);
    return match ? safeUrl(match[2]) : null;
  }

  function shouldHandleNavigation(target, url) {
    if (!url || url.origin !== window.location.origin) return false;
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    if (url.hash) return false;
    if (isBlockedPath(url.pathname)) return false;
    if (target.closest && target.closest("form")) return false;

    var link = target.matches && target.matches("a[href]") ? target : target.closest && target.closest("a[href]");
    if (link) {
      var targetAttr = (link.getAttribute("target") || "").toLowerCase();
      if (targetAttr && targetAttr !== "_self") return false;
      if (link.hasAttribute("download")) return false;
      if (link.closest("form")) return false;
      if (link.getAttribute("data-no-spa") === "true" || link.getAttribute("data-spa") === "false") return false;
      if (link.hasAttribute("hx-post") || link.hasAttribute("hx-put") || link.hasAttribute("hx-delete")) return false;
      var method = (link.getAttribute("data-method") || link.getAttribute("formmethod") || "get").toLowerCase();
      if (method !== "get") return false;
    }

    if (url.pathname === window.location.pathname && url.search === window.location.search) {
      return false;
    }

    return true;
  }

  function isBlockedPath(pathname) {
    if (BLOCKED_EXACT_PATHS[pathname]) return true;
    return BLOCKED_PREFIXES.some(function (prefix) {
      return pathname.indexOf(prefix) === 0;
    });
  }

  async function navigateTo(url, options) {
    if (isNavigating) return;
    saveScrollPosition();
    isNavigating = true;

    if (activeController) activeController.abort();
    activeController = new AbortController();

    try {
      var page = await fetchPage(url, activeController.signal);
      var nextIndex = currentIndex + 1;
      var finalUrl = page.url.href;

      history.pushState(makeHistoryState(nextIndex, 0), "", finalUrl);
      currentIndex = nextIndex;
      await swapPage(page, {
        direction: options.direction || "forward",
        scrollY: 0
      });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      window.location.href = url.href;
    } finally {
      isNavigating = false;
      activeController = null;
    }
  }

  async function handlePopState(event) {
    if (!document.querySelector(CONTAINER_SELECTOR)) return;

    if (activeController) activeController.abort();
    activeController = new AbortController();

    var nextIndex = getHistoryIndex(event.state);
    var direction = nextIndex < currentIndex ? "back" : "forward";
    currentIndex = nextIndex;
    isNavigating = true;

    try {
      var url = new URL(window.location.href);
      if (isBlockedPath(url.pathname)) {
        window.location.reload();
        return;
      }

      var page = await fetchPage(url, activeController.signal);
      var restoreY = getSavedScrollY(url.href, event.state && event.state.scrollY);
      await swapPage(page, {
        direction: direction,
        scrollY: restoreY
      });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      window.location.reload();
    } finally {
      isNavigating = false;
      activeController = null;
    }
  }

  async function fetchPage(url, signal) {
    var response = await fetch(url.href, {
      method: "GET",
      credentials: "same-origin",
      signal: signal,
      headers: {
        "Accept": "text/html",
        "X-Requested-With": "fetch"
      }
    });

    var contentType = response.headers.get("content-type") || "";
    if (!response.ok || contentType.indexOf("text/html") === -1) {
      throw new Error("Navigation response is not HTML");
    }

    var html = await response.text();
    var doc = new DOMParser().parseFromString(html, "text/html");
    var container = doc.querySelector(CONTAINER_SELECTOR);
    if (!container || !document.querySelector(CONTAINER_SELECTOR)) {
      throw new Error("Page container is missing");
    }

    return {
      doc: doc,
      container: container,
      title: doc.title || document.title,
      bodyClass: doc.body ? doc.body.className : "",
      url: new URL(response.url || url.href, window.location.href)
    };
  }

  async function swapPage(page, options) {
    var direction = options.direction === "back" ? "back" : "forward";
    var scrollY = Math.max(0, Number(options.scrollY || 0));

    root.classList.remove("forward", "back");
    root.classList.add(direction, "app-transitioning");
    cleanupRuntimeArtifacts();

    var update = async function () {
      var currentContainer = document.querySelector(CONTAINER_SELECTOR);
      var nextContainer = page.container;

      syncPageStyles(page.doc);
      document.title = page.title;
      if (document.body) document.body.className = page.bodyClass;
      currentContainer.replaceWith(nextContainer);
      window.scrollTo(0, scrollY);

      await runPageScripts(nextContainer);
      initKnownComponents(nextContainer);
      dispatchPageReady(nextContainer);
    };

    if (document.startViewTransition && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      var transition = document.startViewTransition(update);
      try {
        await transition.finished;
      } finally {
        root.classList.remove("forward", "back", "app-transitioning");
      }
      return;
    }

    try {
      await update();
    } finally {
      root.classList.remove("forward", "back", "app-transitioning");
    }
  }

  function syncPageStyles(doc) {
    document.querySelectorAll("style[data-spa-page-style]").forEach(function (style) {
      style.remove();
    });

    doc.querySelectorAll("style").forEach(function (style) {
      if (style.id === "app-transition-styles") return;
      var clone = style.cloneNode(true);
      clone.setAttribute("data-spa-page-style", "");
      document.head.appendChild(clone);
    });
  }

  async function runPageScripts(container) {
    var scripts = Array.prototype.slice.call(container.querySelectorAll("script"));

    for (var i = 0; i < scripts.length; i += 1) {
      var script = scripts[i];
      if (!isExecutableScript(script)) continue;

      if (script.src) {
        await loadExternalScript(script);
      } else {
        runInlineScript(script.textContent || "", i);
      }
    }
  }

  function isExecutableScript(script) {
    var type = (script.getAttribute("type") || "").trim().toLowerCase();
    return !type || type === "text/javascript" || type === "application/javascript";
  }

  function loadExternalScript(sourceScript) {
    var src = absoluteUrl(sourceScript.src);
    if (loadedExternalScripts.has(src)) return Promise.resolve();

    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = src;
      script.async = false;

      ["crossorigin", "integrity", "referrerpolicy", "nonce"].forEach(function (attr) {
        if (sourceScript.hasAttribute(attr)) {
          script.setAttribute(attr, sourceScript.getAttribute(attr));
        }
      });

      script.onload = function () {
        loadedExternalScripts.add(src);
        resolve();
      };
      script.onerror = function () {
        reject(new Error("Failed to load script: " + src));
      };
      document.head.appendChild(script);
    });
  }

  function runInlineScript(code, index) {
    if (!code || !code.trim()) return;

    withReadyEventPatches(function () {
      try {
        new Function(code + "\n//# sourceURL=spa-inline-" + index + ".js")();
      } catch (error) {
        console.error("SPA inline script failed", error);
      }
    });
  }

  function withReadyEventPatches(callback) {
    var originalDocumentAdd = document.addEventListener;
    var originalWindowAdd = window.addEventListener;

    // Existing templates register page widgets on DOMContentLoaded/load.
    // During SPA swaps those lifecycle events already happened, so run them now.
    document.addEventListener = function (type, listener, options) {
      if (type === "DOMContentLoaded") {
        callReadyListener(listener, document, type);
        return;
      }
      return originalDocumentAdd.call(document, type, listener, options);
    };

    window.addEventListener = function (type, listener, options) {
      if (type === "load") {
        callReadyListener(listener, window, type);
        return;
      }
      return originalWindowAdd.call(window, type, listener, options);
    };

    try {
      callback();
    } finally {
      document.addEventListener = originalDocumentAdd;
      window.addEventListener = originalWindowAdd;
    }
  }

  function callReadyListener(listener, target, type) {
    var event = new Event(type);
    if (typeof listener === "function") {
      listener.call(target, event);
    } else if (listener && typeof listener.handleEvent === "function") {
      listener.handleEvent(event);
    }
  }

  function initKnownComponents(container) {
    if (!container) return;

    if (window.htmx && typeof window.htmx.process === "function") {
      window.htmx.process(container);
    }

    if (window.Swiper) {
      container.querySelectorAll(".myPromoSwiper").forEach(function (swiperEl) {
        if (swiperEl.swiper) return;
        new window.Swiper(swiperEl, {
          loop: true,
          autoplay: { delay: 3000 },
          slidesPerView: 1,
          pagination: false,
          navigation: false
        });
      });
    }

    if (window.Fancybox && container.querySelector('[data-fancybox="gallery"]')) {
      window.Fancybox.unbind("[data-fancybox]");
      window.Fancybox.bind('[data-fancybox="gallery"]', {
        Toolbar: false,
        Thumbs: false,
        closeButton: false,
        dragToClose: true,
        click: "close",
        Image: { zoom: false },
        Carousel: { friction: 0.88 }
      });
    }
  }

  function dispatchPageReady(container) {
    document.dispatchEvent(new CustomEvent(READY_EVENT, {
      detail: {
        url: window.location.href,
        container: container || document.querySelector(CONTAINER_SELECTOR)
      }
    }));
  }

  function cleanupRuntimeArtifacts() {
    document.querySelectorAll("[data-check-runtime]").forEach(function (element) {
      element.remove();
    });

    if (window.Fancybox && typeof window.Fancybox.close === "function") {
      try {
        window.Fancybox.close();
        window.Fancybox.unbind("[data-fancybox]");
      } catch (error) {
        console.error("Fancybox cleanup failed", error);
      }
    }
  }

  function queueScrollSave() {
    if (scrollSaveQueued) return;
    scrollSaveQueued = true;
    window.requestAnimationFrame(function () {
      scrollSaveQueued = false;
      saveScrollPosition();
    });
  }

  function saveScrollPosition() {
    var y = window.scrollY || window.pageYOffset || 0;
    try {
      sessionStorage.setItem(SCROLL_PREFIX + window.location.href, String(y));
    } catch (error) {}

    var state = history.state;
    if (state && Object.prototype.hasOwnProperty.call(state, STATE_INDEX)) {
      history.replaceState(Object.assign({}, state, { scrollY: y }), "", window.location.href);
    }
  }

  function getSavedScrollY(url, fallback) {
    var stored = null;
    try {
      stored = sessionStorage.getItem(SCROLL_PREFIX + url);
    } catch (error) {}

    var value = stored !== null ? Number(stored) : Number(fallback || 0);
    return Number.isFinite(value) ? value : 0;
  }

  function ensureHistoryState() {
    var state = history.state || {};
    var index = getHistoryIndex(state);
    currentIndex = index;

    if (!Object.prototype.hasOwnProperty.call(state, STATE_INDEX)) {
      history.replaceState(makeHistoryState(index, window.scrollY || 0, state), "", window.location.href);
    }
  }

  function makeHistoryState(index, scrollY, baseState) {
    return Object.assign({}, baseState || history.state || {}, {
      __app: true,
      scrollY: Number(scrollY || 0),
      url: window.location.href,
      [STATE_INDEX]: Number(index || 0)
    });
  }

  function getHistoryIndex(state) {
    if (!state || !Number.isFinite(Number(state[STATE_INDEX]))) return 0;
    return Number(state[STATE_INDEX]);
  }

  function installTelegramBackButtonProxy() {
    var tg = window.Telegram && window.Telegram.WebApp;
    var backButton = tg && tg.BackButton;
    if (!backButton || backButton.__appBackButtonProxyInstalled) return;

    var originalOnClick = typeof backButton.onClick === "function" ? backButton.onClick.bind(backButton) : null;
    var originalOffClick = typeof backButton.offClick === "function" ? backButton.offClick.bind(backButton) : null;
    var activeCallback = null;

    if (!originalOnClick) return;

    backButton.onClick = function (callback) {
      if (activeCallback && originalOffClick) {
        originalOffClick(activeCallback);
      }
      activeCallback = callback;
      return originalOnClick(callback);
    };

    if (originalOffClick) {
      backButton.offClick = function (callback) {
        if (activeCallback === callback) activeCallback = null;
        return originalOffClick(callback);
      };
    }

    backButton.__appBackButtonProxyInstalled = true;
  }

  function safeUrl(value) {
    try {
      return new URL(value, window.location.href);
    } catch (error) {
      return null;
    }
  }

  function absoluteUrl(value) {
    return new URL(value, window.location.href).href;
  }
})();
