(function () {
  "use strict";

  if (window.PageTransitions && window.PageTransitions.__active) return;

  var SHELL_SELECTOR = "#app-shell";
  var SCREEN_SELECTOR = "[data-app-screen]";
  var CONTENT_SELECTOR = "#page-content";
  var PERSISTENT_SELECTOR = "[data-persistent-shell]";
  var READY_EVENT = "app:page-ready";
  var DESTROY_EVENT = "app:page-destroy";
  var STATE_INDEX = "__pageTransitionIndex";
  var SCROLL_PREFIX = "page-transition:scroll:";
  var VERSION = "20260601-2";

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

  var FILE_PATH_RE = /\.(?:pdf|zip|xlsx?|docx?|png|jpe?g|webp|gif|svg|mp4|mp3|mov|webm)(?:$|[?#])/i;

  var root = document.documentElement;
  var shell = null;
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
  var loadedStylesheets = new Set(
    Array.prototype.slice.call(document.querySelectorAll('link[rel~="stylesheet"][href]'))
      .map(function (link) { return absoluteUrl(link.href); })
  );

  window.PageTransitions = {
    __active: true,
    version: VERSION,
    navigateTo: navigateTo,
    initPageComponents: initPageComponents,
    destroyPage: destroyPage,
    addCleanup: addCleanup
  };

  window.AppRouter = window.AppRouter || {};
  window.AppRouter.__active = true;
  window.AppRouter.version = VERSION;
  window.AppRouter.go = function (href, options) {
    options = options || {};
      return navigateTo(href, {
        direction: options.direction || "forward",
        push: options.push !== false,
        replace: options.replace === true,
        scrollY: options.scrollY || 0,
        skipTransition: options.skipTransition === true
      });
  };
  window.AppRouter.reload = function () {
    return navigateTo(window.location.href, { replace: true, scrollY: getScrollY() });
  };
  window.AppRouter.initPage = initPageComponents;
  window.AppRouter.destroyPage = destroyPage;
  window.AppRouter.addCleanup = addCleanup;

  window.initPageComponents = initPageComponents;

  installTelegramBackButtonProxy();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  function boot() {
    shell = ensureShell();
    if (!shell || !document.querySelector(CONTENT_SELECTOR)) return;

    ensurePersistentLayout();
    ensureHistoryState();
    updateActiveNavigation(window.location.href);
    initPageComponents(document.querySelector(CONTENT_SELECTOR));

    if ("scrollRestoration" in history) {
      history.scrollRestoration = "manual";
    }

    document.addEventListener("click", handleDocumentClick, true);
    window.addEventListener("popstate", handlePopState);
    window.addEventListener("beforeunload", saveScrollPosition);
    window.addEventListener("scroll", queueScrollSave, { passive: true });

    markDebug("boot");
    dispatchPageReady(document.querySelector(CONTENT_SELECTOR));
  }

  function ensureShell() {
    var existingShell = document.querySelector(SHELL_SELECTOR);
    var content = document.querySelector(CONTENT_SELECTOR);

    if (!content && !existingShell) return null;

    if (!existingShell && content) {
      existingShell = document.createElement("main");
      existingShell.id = "app-shell";
      existingShell.className = "app-shell";
      existingShell.setAttribute("data-app-shell", "");
      content.parentNode.insertBefore(existingShell, content);
      existingShell.appendChild(content);
    }

    return existingShell;
  }

  function ensurePersistentLayout() {
    var content = document.querySelector(CONTENT_SELECTOR);
    if (!content) return;

    var host = content.closest(SCREEN_SELECTOR) || shell || content.parentNode;
    var persistents = Array.prototype.slice.call(content.querySelectorAll(PERSISTENT_SELECTOR));

    persistents.forEach(function (element) {
      var key = element.getAttribute("data-persistent-shell");
      if (!key) return;

      var existing = findPersistentRegion(key, content);
      if (existing && existing !== element) {
        element.remove();
        return;
      }

      if (key === "header") {
        host.insertBefore(element, content);
      } else {
        host.insertBefore(element, content.nextSibling);
      }
    });
  }

  function findPersistentRegion(key, excludedContent) {
    var regions = Array.prototype.slice.call(document.querySelectorAll(PERSISTENT_SELECTOR));
    for (var i = 0; i < regions.length; i += 1) {
      var region = regions[i];
      if (region.getAttribute("data-persistent-shell") !== key) continue;
      if (excludedContent && excludedContent.contains(region)) continue;
      return region;
    }
    return null;
  }

  function stripPersistentRegions(content) {
    Array.prototype.slice.call(content.querySelectorAll(PERSISTENT_SELECTOR)).forEach(function (element) {
      element.remove();
    });
  }

  function handleDocumentClick(event) {
    if (!shell) return;
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

    navigateTo(url.href, { direction: "forward", push: true });
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
    if (isBlockedUrl(url)) return false;

    if (url.hash && url.pathname === window.location.pathname && url.search === window.location.search) {
      return false;
    }

    if (target.closest && target.closest("form")) return false;
    if (target.closest && target.closest("[data-no-transition], [data-no-router]")) return false;

    var link = target.matches && target.matches("a[href]")
      ? target
      : target.closest && target.closest("a[href]");

    if (link) {
      var targetAttr = (link.getAttribute("target") || "").toLowerCase();
      if (targetAttr && targetAttr !== "_self") return false;
      if (link.hasAttribute("download")) return false;
      if (link.closest("form")) return false;
      if (link.hasAttribute("data-no-transition")) return false;
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

  function isBlockedUrl(url) {
    if (BLOCKED_EXACT_PATHS[url.pathname]) return true;
    if (FILE_PATH_RE.test(url.pathname)) return true;
    if (/(^|\/)logout\/?$/i.test(url.pathname)) return true;

    return BLOCKED_PREFIXES.some(function (prefix) {
      return url.pathname.indexOf(prefix) === 0;
    });
  }

  async function navigateTo(value, options) {
    options = options || {};
    var url = safeUrl(value);

    if (!url || isBlockedUrl(url)) {
      hardNavigate(value);
      return;
    }

    if (isNavigating) return;

    saveScrollPosition();
    isNavigating = true;
    root.classList.add("is-page-loading");

    if (activeController) activeController.abort();
    activeController = new AbortController();

    try {
      var page = await fetchPage(url, activeController.signal);
      var shouldReplace = options.replace === true;
      var shouldPush = options.push !== false && !shouldReplace;
      var nextIndex = shouldPush ? currentIndex + 1 : currentIndex;
      var historyCommitted = false;

      function commitHistory() {
        if (historyCommitted) return;
        historyCommitted = true;

        if (shouldReplace) {
          history.replaceState(makeHistoryState(nextIndex, page.url.href, Number(options.scrollY || 0)), "", page.url.href);
        } else if (shouldPush) {
          history.pushState(makeHistoryState(nextIndex, page.url.href, 0), "", page.url.href);
        }

        currentIndex = nextIndex;
      }

      await transitionTo(page, {
        direction: normalizeDirection(options.direction),
        scrollY: Number(options.scrollY || 0),
        skipTransition: options.skipTransition === true,
        commitHistory: commitHistory
      });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      markDebug("fallback", error && error.message);
      hardNavigate(url.href);
    } finally {
      isNavigating = false;
      activeController = null;
      root.classList.remove("is-page-loading");
    }
  }

  async function handlePopState(event) {
    if (!shell || !document.querySelector(CONTENT_SELECTOR)) return;

    if (activeController) activeController.abort();
    isNavigating = false;

    var nextIndex = getHistoryIndex(event.state);
    var direction = nextIndex < currentIndex ? "backward" : "forward";
    currentIndex = nextIndex;

    var restoreY = getSavedScrollY(window.location.href, event.state && event.state.scrollY);
    await navigateTo(window.location.href, {
      direction: direction,
      push: false,
      scrollY: restoreY,
      skipTransition: isIOS()
    });
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
    var oldContent = document.querySelector(CONTENT_SELECTOR);
    if (!oldContent) throw new Error("Current page content is missing");

    var newContent = page.content;
    var direction = normalizeDirection(options.direction);
    var restoreY = Math.max(0, Number(options.scrollY || 0));

    stripPersistentRegions(newContent);
    await loadPageStylesheets(page.doc);

    var updateDOM = function () {
      preparePageStyles(page.doc);
      destroyPage(oldContent);
      oldContent.replaceWith(newContent);

      document.title = page.title;
      if (document.body) document.body.className = page.bodyClass;

      if (typeof options.commitHistory === "function") {
        options.commitHistory();
      }

      updateActiveNavigation(page.url.href);
      commitPageStyles();
      scrollToTargetOrPosition(page.url, restoreY);
    };

    if (!options.skipTransition && canUseViewTransitions()) {
      root.dataset.transition = direction;

      try {
        var transition = document.startViewTransition(updateDOM);
        await transition.finished;
      } finally {
        delete root.dataset.transition;
      }
    } else {
      updateDOM();
    }

    await hydratePage(newContent);
  }

  function canUseViewTransitions() {
    return typeof document.startViewTransition === "function";
  }

  async function hydratePage(content) {
    await runPageScripts(content);
    initPageComponents(content);
    dispatchPageReady(content);
  }

  function initPageComponents(rootNode) {
    rootNode = rootNode || document;

    try {
      if (window.Swiper) {
        rootNode.querySelectorAll(".myPromoSwiper").forEach(function (swiperEl) {
          if (swiperEl.swiper) return;
          swiperEl.dataset.initialized = "true";
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
      console.error("PageTransitions Swiper init failed", error);
    }

    try {
      if (window.Fancybox && rootNode.querySelector('[data-fancybox="gallery"]')) {
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
      console.error("PageTransitions Fancybox init failed", error);
    }

    rootNode.querySelectorAll("img[loading='lazy']").forEach(function (img) {
      img.decoding = "async";
    });
  }

  function destroyPage(rootNode) {
    if (!rootNode) return;

    document.dispatchEvent(new CustomEvent(DESTROY_EVENT, {
      detail: { container: rootNode, url: window.location.href }
    }));

    try {
      rootNode.querySelectorAll(".swiper").forEach(function (swiperEl) {
        if (swiperEl.swiper && typeof swiperEl.swiper.destroy === "function") {
          swiperEl.swiper.destroy(true, true);
        }
      });
    } catch (error) {
      console.error("PageTransitions Swiper destroy failed", error);
    }

    try {
      if (window.Fancybox && typeof window.Fancybox.close === "function") {
        window.Fancybox.close();
        window.Fancybox.unbind("[data-fancybox]");
      }
    } catch (error) {
      console.error("PageTransitions Fancybox destroy failed", error);
    }

    document.querySelectorAll("[data-check-runtime]").forEach(function (element) {
      element.remove();
    });

    runCleanups(rootNode);
  }

  function addCleanup(rootNode, cleanup) {
    if (!rootNode || typeof cleanup !== "function") return;
    rootNode.__pageTransitionCleanups = rootNode.__pageTransitionCleanups || [];
    rootNode.__pageTransitionCleanups.push(cleanup);
  }

  function runCleanups(rootNode) {
    var cleanups = rootNode.__pageTransitionCleanups || [];
    while (cleanups.length) {
      var cleanup = cleanups.pop();
      try {
        cleanup();
      } catch (error) {
        console.error("PageTransitions cleanup failed", error);
      }
    }
  }

  async function runPageScripts(content) {
    var scripts = Array.prototype.slice.call(content.querySelectorAll("script"));

    for (var i = 0; i < scripts.length; i += 1) {
      var script = scripts[i];
      if (!isExecutableScript(script)) continue;

      if (script.src) {
        await loadExternalScript(script);
      } else {
        runInlineScript(content, script.textContent || "", i);
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

  function loadPageStylesheets(doc) {
    var links = Array.prototype.slice.call(doc.querySelectorAll('link[rel~="stylesheet"][href]'));
    return Promise.all(links.map(function (link) {
      return loadStylesheet(link).catch(function (error) {
        console.error("PageTransitions stylesheet load failed", error);
      });
    }));
  }

  function loadStylesheet(sourceLink) {
    var href = absoluteUrl(sourceLink.href);
    if (loadedStylesheets.has(href)) return Promise.resolve();

    return new Promise(function (resolve, reject) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;

      ["media", "crossorigin", "integrity", "referrerpolicy"].forEach(function (attr) {
        if (sourceLink.hasAttribute(attr)) {
          link.setAttribute(attr, sourceLink.getAttribute(attr));
        }
      });

      link.onload = function () {
        loadedStylesheets.add(href);
        resolve();
      };
      link.onerror = function () {
        reject(new Error("Failed to load stylesheet: " + href));
      };
      document.head.appendChild(link);
    });
  }

  function runInlineScript(content, code, index) {
    if (!code || !code.trim()) return;

    withPageRuntime(content, function () {
      try {
        new Function(code + "\n//# sourceURL=page-transition-inline-" + index + ".js")();
      } catch (error) {
        console.error("PageTransitions inline script failed", error);
      }
    });
  }

  function withPageRuntime(content, callback) {
    var originalTargetAdd = EventTarget.prototype.addEventListener;
    var originalTargetRemove = EventTarget.prototype.removeEventListener;
    var originalDocumentAdd = document.addEventListener;
    var originalWindowAdd = window.addEventListener;
    var originalSetTimeout = window.setTimeout;
    var originalSetInterval = window.setInterval;

    EventTarget.prototype.addEventListener = function (type, listener, options) {
      originalTargetAdd.call(this, type, listener, options);
      if (shouldTrackRuntimeTarget(content, this)) {
        addCleanup(content, function () {
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
      addCleanup(content, function () {
        document.removeEventListener(type, listener, options);
      });
    };

    window.addEventListener = function (type, listener, options) {
      if (type === "load") {
        callReadyListener(listener, window, type);
        return;
      }
      originalWindowAdd.call(window, type, listener, options);
      addCleanup(content, function () {
        window.removeEventListener(type, listener, options);
      });
    };

    window.setTimeout = function () {
      var id = originalSetTimeout.apply(window, arguments);
      addCleanup(content, function () { window.clearTimeout(id); });
      return id;
    };

    window.setInterval = function () {
      var id = originalSetInterval.apply(window, arguments);
      addCleanup(content, function () { window.clearInterval(id); });
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

  function shouldTrackRuntimeTarget(content, target) {
    if (target === window || target === document) return true;
    if (!target || !target.nodeType) return false;
    if (target === content) return true;
    return typeof content.contains === "function" && content.contains(target);
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
    document.querySelectorAll("style[data-page-transition-next]").forEach(function (style) {
      style.remove();
    });

    doc.querySelectorAll("style").forEach(function (style) {
      var clone = style.cloneNode(true);
      clone.setAttribute("data-page-transition-next", "");
      document.head.appendChild(clone);
    });
  }

  function commitPageStyles() {
    document.querySelectorAll("style[data-page-transition-style]").forEach(function (style) {
      style.remove();
    });

    document.querySelectorAll("style[data-page-transition-next]").forEach(function (style) {
      style.removeAttribute("data-page-transition-next");
      style.setAttribute("data-page-transition-style", "");
    });
  }

  function updateActiveNavigation(url) {
    var currentUrl = safeUrl(url);
    if (!currentUrl) return;

    var currentPath = normalizePath(currentUrl.pathname);
    var links = document.querySelectorAll('[data-persistent-shell="bottom-nav"] a[href], nav[aria-label="Bottom Navigation"] a[href]');

    links.forEach(function (link) {
      var linkUrl = safeUrl(link.getAttribute("href"));
      if (!linkUrl || linkUrl.origin !== window.location.origin) return;

      var isActive = normalizePath(linkUrl.pathname) === currentPath;
      link.classList.toggle("is-active", isActive);

      if (isActive) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }

      var img = link.querySelector("img[src]");
      if (img) {
        setSvgActive(img, isActive);
      }
    });
  }

  function setSvgActive(img, isActive) {
    var src = img.getAttribute("src") || "";
    if (src.indexOf(".svg") === -1) return;

    var parts = src.split("?");
    var path = parts[0].replace(/_active\.svg$/i, ".svg");
    if (isActive) {
      path = path.replace(/\.svg$/i, "_active.svg");
    }
    img.setAttribute("src", path + (parts[1] ? "?" + parts[1] : ""));
  }

  function dispatchPageReady(content) {
    document.dispatchEvent(new CustomEvent(READY_EVENT, {
      detail: {
        container: content,
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

  function scrollToTargetOrPosition(url, fallbackY) {
    var y = Math.max(0, Number(fallbackY || 0));

    if (url && url.hash) {
      var id = decodeURIComponent(url.hash.slice(1));
      var target = document.getElementById(id) || document.querySelector('[name="' + cssStringEscape(id) + '"]');
      if (target && typeof target.getBoundingClientRect === "function") {
        y = target.getBoundingClientRect().top + getScrollY();
      }
    }

    window.scrollTo(0, y);
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
      __pageTransitions: true,
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
    if (!backButton || backButton.__pageTransitionsBackButtonProxyInstalled) return;

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

    backButton.__pageTransitionsBackButtonProxyInstalled = true;
  }

  function normalizeDirection(value) {
    return value === "back" || value === "backward" ? "backward" : "forward";
  }

  function normalizePath(pathname) {
    if (pathname.length > 1 && pathname.slice(-1) === "/") {
      return pathname.slice(0, -1);
    }
    return pathname;
  }

  function isIOS() {
    var ua = navigator.userAgent || "";
    var platform = navigator.platform || "";
    return /iPad|iPhone|iPod/.test(ua) || (platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function hardNavigate(href) {
    window.location.href = href;
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

  function getScrollY() {
    return window.scrollY || window.pageYOffset || 0;
  }

  function cssStringEscape(value) {
    return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function isDebugEnabled() {
    try {
      return window.localStorage && window.localStorage.getItem("page_transitions_debug") === "1";
    } catch (error) {
      return false;
    }
  }

  function markDebug(eventName, detail) {
    if (!debug || !window.console) return;
    console.log("[page-transitions]", eventName, detail || "");
  }
})();
