(function () {
  "use strict";

  var SHELL_SELECTOR = "#app-shell";
  var SCREEN_SELECTOR = "[data-app-screen]";
  var CONTENT_SELECTOR = "#page-content";
  var READY_EVENT = "app:page-ready";
  var DESTROY_EVENT = "app:page-destroy";
  var STATE_INDEX = "__appRouterIndex";
  var SCROLL_PREFIX = "app-router:scroll:";
  var VERSION = "20260531-2";
  var TRANSITION_MS = 360;

  var BLOCKED_EXACT_PATHS = {
    "/": true,
    "/email-login": true,
    "/email-login/": true
  };

  var BLOCKED_PREFIXES = [
    "/admin/",
    "/api/",
    "/payment/create/",
    "/payment/success/",
    "/email/",
    "/checkout",
    "/login",
    "/logout",
    "/yookassa/",
    "/static/",
    "/media/"
  ];

  var root = document.documentElement;
  var shell = null;
  var activeScreen = null;
  var currentIndex = getHistoryIndex(history.state);
  var isNavigating = false;
  var activeController = null;
  var scrollSaveQueued = false;
  var debug = isDebugEnabled();
  var loadedExternalScripts = new Set(
    Array.prototype.slice.call(document.scripts)
      .filter(function (script) { return script.src; })
      .map(function (script) { return absoluteUrl(script.src); })
  );

  window.AppRouter = {
    version: VERSION,
    go: go,
    reload: function () { return go(window.location.href, { replace: true }); },
    initPage: initPage,
    destroyPage: destroyPage,
    addCleanup: addCleanup,
    currentScreen: function () { return activeScreen; }
  };

  installTelegramBackButtonProxy();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  function boot() {
    shell = ensureShell();
    if (!shell || !activeScreen) return;

    ensureHistoryState();
    initPage(activeScreen);

    if ("scrollRestoration" in history) {
      history.scrollRestoration = "manual";
    }

    document.addEventListener("click", handleDocumentClick, true);
    window.addEventListener("popstate", handlePopState);
    window.addEventListener("beforeunload", saveScrollPosition);
    window.addEventListener("scroll", queueScrollSave, { passive: true });

    markDebug("boot");
    dispatchPageReady(activeScreen);
  }

  function ensureShell() {
    var existingShell = document.querySelector(SHELL_SELECTOR);
    var content = document.querySelector(CONTENT_SELECTOR);

    if (!content && !existingShell) return null;

    if (!existingShell) {
      var parent = content.parentNode;
      var nextSibling = content.nextSibling;
      existingShell = document.createElement("main");
      existingShell.id = "app-shell";
      existingShell.className = "app-shell";
      existingShell.setAttribute("data-app-shell", "");

      var screen = createScreen(content);
      screen.classList.add("is-active");
      parent.insertBefore(existingShell, nextSibling);
      existingShell.appendChild(screen);
    }

    existingShell.classList.add("app-shell");
    activeScreen =
      existingShell.querySelector(SCREEN_SELECTOR + ".is-active") ||
      (content && content.closest(SCREEN_SELECTOR));

    if (!activeScreen && content) {
      activeScreen = createScreen(content);
      activeScreen.classList.add("is-active");
      existingShell.appendChild(activeScreen);
    }

    return existingShell;
  }

  function handleDocumentClick(event) {
    if (!shell || !activeScreen) return;
    if (event.defaultPrevented) return;
    if (typeof event.button === "number" && event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    var target = event.target.closest
      ? event.target.closest("a[href], [data-router-href], [data-spa-href], [onclick*=\"location\"]")
      : null;

    if (!target) return;

    var url = getNavigationUrl(target);
    if (!url || !shouldHandleNavigation(target, url)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    if (isNavigating) return;
    go(url.href, { direction: "forward" });
  }

  function getNavigationUrl(target) {
    if (target.matches && target.matches("a[href]")) {
      return safeUrl(target.href);
    }

    var routerHref = target.getAttribute("data-router-href") || target.getAttribute("data-spa-href");
    if (routerHref) {
      return safeUrl(routerHref);
    }

    var onclick = target.getAttribute("onclick") || "";
    var match = onclick.match(/(?:window\.)?location(?:\.href)?\s*=\s*(['"])(.*?)\1/);
    return match ? safeUrl(match[2]) : null;
  }

  function shouldHandleNavigation(target, url) {
    if (!url || url.origin !== window.location.origin) return false;
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    if (isBlockedPath(url.pathname)) return false;

    if (url.hash) {
      return !(url.pathname === window.location.pathname && url.search === window.location.search);
    }

    if (target.closest && target.closest("form")) return false;
    if (target.closest && target.closest("[data-no-router]")) return false;

    var link = target.matches && target.matches("a[href]")
      ? target
      : target.closest && target.closest("a[href]");

    if (link) {
      var targetAttr = (link.getAttribute("target") || "").toLowerCase();
      if (targetAttr && targetAttr !== "_self") return false;
      if (link.hasAttribute("download")) return false;
      if (link.closest("form")) return false;
      if (link.getAttribute("data-no-router") === "true") return false;
      if (link.getAttribute("data-no-spa") === "true" || link.getAttribute("data-spa") === "false") return false;
      if (link.hasAttribute("hx-post") || link.hasAttribute("hx-put") || link.hasAttribute("hx-delete")) return false;
      var method = (link.getAttribute("data-method") || link.getAttribute("formmethod") || "get").toLowerCase();
      if (method !== "get") return false;
    }

    if (url.pathname === window.location.pathname && url.search === window.location.search && !url.hash) {
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

  async function go(value, options) {
    options = options || {};
    var url = safeUrl(value);
    if (!url || isBlockedPath(url.pathname)) {
      window.location.href = value;
      return;
    }

    if (isNavigating) return;

    saveScrollPosition();
    isNavigating = true;

    if (activeController) activeController.abort();
    activeController = new AbortController();

    try {
      var page = await fetchPage(url, activeController.signal);
      var nextIndex = options.replace ? currentIndex : currentIndex + 1;
      var nextUrl = page.url.href;

      if (options.replace) {
        history.replaceState(makeHistoryState(nextIndex, nextUrl, 0), "", nextUrl);
      } else {
        history.pushState(makeHistoryState(nextIndex, nextUrl, 0), "", nextUrl);
      }

      currentIndex = nextIndex;

      await transitionTo(page, {
        direction: options.direction || "forward",
        scrollY: Number(options.scrollY || 0)
      });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      markDebug("fallback", error && error.message);
      window.location.href = url.href;
    } finally {
      isNavigating = false;
      activeController = null;
    }
  }

  async function handlePopState(event) {
    if (!shell || !activeScreen) return;

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

      await transitionTo(page, {
        direction: direction,
        scrollY: restoreY
      });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      markDebug("popstate-fallback", error && error.message);
      window.location.reload();
    } finally {
      isNavigating = false;
      activeController = null;
    }
  }

  async function fetchPage(url, signal) {
    var fetchUrl = new URL(url.href);
    fetchUrl.searchParams.set("__spa_fetch", String(Date.now()));

    var response = await fetch(fetchUrl.href, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
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
    var content = doc.querySelector(CONTENT_SELECTOR);

    if (!content) {
      throw new Error("Page content is missing");
    }

    return {
      doc: doc,
      content: content,
      title: doc.title || document.title,
      bodyClass: doc.body ? doc.body.className : "",
      url: cleanNavigationUrl(response.url || url.href)
    };
  }

  async function transitionTo(page, options) {
    var direction = options.direction === "back" ? "back" : "forward";
    var restoreY = Math.max(0, Number(options.scrollY || 0));
    var oldScreen = activeScreen;
    var newScreen = createScreen(page.content);
    var oldScrollY = getScrollY();
    var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    preparePageStyles(page.doc);
    document.title = page.title;
    if (document.body) document.body.className = page.bodyClass;

    if (prefersReducedMotion) {
      destroyPage(oldScreen);
      oldScreen.replaceWith(newScreen);
      activeScreen = newScreen;
      newScreen.classList.add("is-active");
      window.scrollTo(0, restoreY);
      commitPageStyles();
      await hydratePage(newScreen);
      return;
    }

    root.classList.add("app-router-transitioning");
    shell.classList.add("is-transitioning");

    var newTop = oldScrollY - restoreY;
    newScreen.setAttribute("aria-hidden", "true");
    newScreen.classList.add(direction === "back" ? "enter-from-left" : "enter-from-right");
    shell.appendChild(newScreen);

    var minHeight = Math.max(
      document.documentElement.scrollHeight,
      oldScreen.scrollHeight,
      newTop + newScreen.scrollHeight,
      oldScrollY + window.innerHeight,
      window.innerHeight
    );

    shell.style.minHeight = minHeight + "px";
    oldScreen.style.top = "0px";
    newScreen.style.top = newTop + "px";

    forceReflow(newScreen);

    requestAnimationFrame(function () {
      oldScreen.classList.add(direction === "back" ? "leave-to-right" : "leave-to-left");
      newScreen.classList.add("enter-active");
    });

    await waitForScreenTransition(newScreen);

    destroyPage(oldScreen);
    oldScreen.remove();

    newScreen.removeAttribute("aria-hidden");
    newScreen.classList.remove("enter-from-right", "enter-from-left", "enter-active");
    newScreen.classList.add("is-active");
    newScreen.style.top = "";
    shell.classList.remove("is-transitioning");
    shell.style.minHeight = "";
    root.classList.remove("app-router-transitioning");
    activeScreen = newScreen;

    window.scrollTo(0, restoreY);
    commitPageStyles();
    await hydratePage(newScreen);
  }

  function createScreen(content) {
    var screen = document.createElement("section");
    screen.className = "app-screen";
    screen.setAttribute("data-app-screen", "");
    screen.appendChild(content);
    return screen;
  }

  async function hydratePage(screen) {
    await runPageScripts(screen);
    initPage(screen);
    dispatchPageReady(screen);
  }

  function initPage(screen) {
    if (!screen) return;
    screen.__appRouterCleanups = screen.__appRouterCleanups || [];

    try {
      if (window.Swiper) {
        screen.querySelectorAll(".myPromoSwiper").forEach(function (swiperEl) {
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
    } catch (error) {
      console.error("AppRouter Swiper init failed", error);
    }

    try {
      if (window.Fancybox && screen.querySelector('[data-fancybox="gallery"]')) {
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
    } catch (error) {
      console.error("AppRouter Fancybox init failed", error);
    }

    screen.querySelectorAll("img[loading='lazy']").forEach(function (img) {
      img.decoding = "async";
    });
  }

  function destroyPage(screen) {
    if (!screen) return;

    document.dispatchEvent(new CustomEvent(DESTROY_EVENT, {
      detail: { screen: screen, url: window.location.href }
    }));

    try {
      screen.querySelectorAll(".swiper").forEach(function (swiperEl) {
        if (swiperEl.swiper && typeof swiperEl.swiper.destroy === "function") {
          swiperEl.swiper.destroy(true, true);
        }
      });
    } catch (error) {
      console.error("AppRouter Swiper destroy failed", error);
    }

    try {
      if (window.Fancybox && typeof window.Fancybox.close === "function") {
        window.Fancybox.close();
        window.Fancybox.unbind("[data-fancybox]");
      }
    } catch (error) {
      console.error("AppRouter Fancybox destroy failed", error);
    }

    document.querySelectorAll("[data-check-runtime]").forEach(function (element) {
      element.remove();
    });

    runCleanups(screen);
  }

  function addCleanup(screen, cleanup) {
    if (!screen || typeof cleanup !== "function") return;
    screen.__appRouterCleanups = screen.__appRouterCleanups || [];
    screen.__appRouterCleanups.push(cleanup);
  }

  function runCleanups(screen) {
    var cleanups = screen.__appRouterCleanups || [];
    while (cleanups.length) {
      var cleanup = cleanups.pop();
      try {
        cleanup();
      } catch (error) {
        console.error("AppRouter cleanup failed", error);
      }
    }
  }

  async function runPageScripts(screen) {
    var scripts = Array.prototype.slice.call(screen.querySelectorAll("script"));

    for (var i = 0; i < scripts.length; i += 1) {
      var script = scripts[i];
      if (!isExecutableScript(script)) continue;

      if (script.src) {
        await loadExternalScript(script);
      } else {
        runInlineScript(screen, script.textContent || "", i);
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

  function runInlineScript(screen, code, index) {
    if (!code || !code.trim()) return;

    withPageRuntime(screen, function () {
      try {
        new Function(code + "\n//# sourceURL=app-router-inline-" + index + ".js")();
      } catch (error) {
        console.error("AppRouter inline script failed", error);
      }
    });
  }

  function withPageRuntime(screen, callback) {
    var originalTargetAdd = EventTarget.prototype.addEventListener;
    var originalTargetRemove = EventTarget.prototype.removeEventListener;
    var originalDocumentAdd = document.addEventListener;
    var originalWindowAdd = window.addEventListener;
    var originalSetTimeout = window.setTimeout;
    var originalSetInterval = window.setInterval;

    EventTarget.prototype.addEventListener = function (type, listener, options) {
      originalTargetAdd.call(this, type, listener, options);
      if (shouldTrackRuntimeTarget(screen, this)) {
        addCleanup(screen, function () {
          originalTargetRemove.call(this, type, listener, options);
        }.bind(this));
      }
    };

    document.addEventListener = function (type, listener, options) {
      if (type === "DOMContentLoaded") {
        callReadyListener(listener, document, type);
        return;
      }
      originalDocumentAdd.call(document, type, listener, options);
      addCleanup(screen, function () {
        document.removeEventListener(type, listener, options);
      });
    };

    window.addEventListener = function (type, listener, options) {
      if (type === "load") {
        callReadyListener(listener, window, type);
        return;
      }
      originalWindowAdd.call(window, type, listener, options);
      addCleanup(screen, function () {
        window.removeEventListener(type, listener, options);
      });
    };

    window.setTimeout = function () {
      var id = originalSetTimeout.apply(window, arguments);
      addCleanup(screen, function () { window.clearTimeout(id); });
      return id;
    };

    window.setInterval = function () {
      var id = originalSetInterval.apply(window, arguments);
      addCleanup(screen, function () { window.clearInterval(id); });
      return id;
    };

    try {
      callback();
    } finally {
      EventTarget.prototype.addEventListener = originalTargetAdd;
      EventTarget.prototype.removeEventListener = originalTargetRemove;
      document.addEventListener = originalDocumentAdd;
      window.addEventListener = originalWindowAdd;
      window.setTimeout = originalSetTimeout;
      window.setInterval = originalSetInterval;
    }
  }

  function shouldTrackRuntimeTarget(screen, target) {
    if (target === window || target === document) return true;
    if (!target || !target.nodeType) return false;
    if (target === screen) return true;
    return typeof screen.contains === "function" && screen.contains(target);
  }

  function callReadyListener(listener, target, type) {
    var event = new Event(type);
    if (typeof listener === "function") {
      listener.call(target, event);
    } else if (listener && typeof listener.handleEvent === "function") {
      listener.handleEvent(event);
    }
  }

  function preparePageStyles(doc) {
    document.querySelectorAll("style[data-app-next-style]").forEach(function (style) {
      style.remove();
    });

    doc.querySelectorAll("style").forEach(function (style) {
      var clone = style.cloneNode(true);
      clone.setAttribute("data-app-next-style", "");
      document.head.appendChild(clone);
    });
  }

  function commitPageStyles() {
    document.querySelectorAll("style[data-app-page-style]").forEach(function (style) {
      style.remove();
    });

    document.querySelectorAll("style[data-app-next-style]").forEach(function (style) {
      style.removeAttribute("data-app-next-style");
      style.setAttribute("data-app-page-style", "");
    });
  }

  function dispatchPageReady(screen) {
    document.dispatchEvent(new CustomEvent(READY_EVENT, {
      detail: {
        screen: screen,
        container: screen ? screen.querySelector(CONTENT_SELECTOR) : null,
        url: window.location.href
      }
    }));
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
    var y = getScrollY();
    var url = window.location.href;

    try {
      sessionStorage.setItem(SCROLL_PREFIX + url, String(y));
    } catch (error) {}

    var state = history.state;
    if (state && Object.prototype.hasOwnProperty.call(state, STATE_INDEX)) {
      history.replaceState(Object.assign({}, state, { scrollY: y, url: url }), "", url);
    }
  }

  function getSavedScrollY(url, fallback) {
    var stored = null;
    try {
      stored = sessionStorage.getItem(SCROLL_PREFIX + url);
    } catch (error) {}

    var value = stored !== null ? Number(stored) : Number(fallback || 0);
    return Number.isFinite(value) ? Math.max(0, value) : 0;
  }

  function ensureHistoryState() {
    var state = history.state || {};
    var index = getHistoryIndex(state);
    currentIndex = index;

    if (!Object.prototype.hasOwnProperty.call(state, STATE_INDEX)) {
      history.replaceState(makeHistoryState(index, window.location.href, getScrollY(), state), "", window.location.href);
    }
  }

  function makeHistoryState(index, url, scrollY, baseState) {
    return Object.assign({}, baseState || {}, {
      __appRouter: true,
      url: url,
      scrollY: Number(scrollY || 0),
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
    if (!backButton || backButton.__appRouterBackButtonProxyInstalled) return;

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

    backButton.__appRouterBackButtonProxyInstalled = true;
  }

  function waitForScreenTransition(screen) {
    return new Promise(function (resolve) {
      var done = false;
      var timer = window.setTimeout(finish, TRANSITION_MS + 120);

      function finish() {
        if (done) return;
        done = true;
        window.clearTimeout(timer);
        screen.removeEventListener("transitionend", onTransitionEnd);
        resolve();
      }

      function onTransitionEnd(event) {
        if (event.target === screen && event.propertyName === "transform") {
          finish();
        }
      }

      screen.addEventListener("transitionend", onTransitionEnd);
    });
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

  function cleanNavigationUrl(value) {
    var cleaned = new URL(value, window.location.href);
    cleaned.searchParams.delete("__spa_fetch");
    return cleaned;
  }

  function forceReflow(element) {
    return element.offsetHeight;
  }

  function getScrollY() {
    return window.scrollY || window.pageYOffset || 0;
  }

  function isDebugEnabled() {
    try {
      return window.localStorage && window.localStorage.getItem("app_router_debug") === "1";
    } catch (error) {
      return false;
    }
  }

  function markDebug(eventName, detail) {
    if (!debug || !window.console) return;
    console.log("[app-router]", eventName, detail || "");
  }
})();
