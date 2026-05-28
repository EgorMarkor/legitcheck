/**
 * PWA Navigation
 * Keeps direction for native shells and adds lightweight web page transitions.
 */
(function () {
  'use strict';

  var TAB_PATHS = ['/home/', '/verdicts/'];
  var STORAGE_KEY = 'pwa_nav_dir';
  var LEAVE_MS = 230;
  var reduceMotion = false;

  try {
    reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (_) {}

  function tabIndex(pathname) {
    var clean = pathname.replace(/\?.*$/, '').replace(/#.*$/, '');
    return TAB_PATHS.indexOf(clean);
  }

  function storeDir(dir) {
    try { sessionStorage.setItem(STORAGE_KEY, dir); } catch (_) {}
  }

  function readDir() {
    try { return sessionStorage.getItem(STORAGE_KEY) || 'fwd'; } catch (_) {}
    return 'fwd';
  }

  function clearDir() {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (_) {}
  }

  function directionFor(url) {
    var fromIdx = tabIndex(location.pathname);
    var toIdx = tabIndex(url.pathname);

    if (fromIdx !== -1 && toIdx !== -1) {
      return toIdx > fromIdx ? 'fwd' : 'back';
    }

    if (url.pathname === '/' || url.pathname === '/home/') {
      return 'back';
    }

    return 'fwd';
  }

  function injectStyles() {
    if (reduceMotion || document.getElementById('pwa-page-transitions-style')) return;

    var style = document.createElement('style');
    style.id = 'pwa-page-transitions-style';
    style.textContent = [
      'html.app-enter-fwd body{opacity:0;transform:translate3d(1.1rem,0,0) scale(.992);}',
      'html.app-enter-back body{opacity:0;transform:translate3d(-1.1rem,0,0) scale(.992);}',
      'html.app-enter-active body{opacity:1;transform:translate3d(0,0,0) scale(1);transition:opacity 220ms cubic-bezier(.22,1,.36,1),transform 260ms cubic-bezier(.22,1,.36,1);will-change:opacity,transform;}',
      'html.app-leave-fwd body{opacity:0;transform:translate3d(-.9rem,0,0) scale(.996);transition:opacity 180ms cubic-bezier(.4,0,1,1),transform 230ms cubic-bezier(.4,0,1,1);will-change:opacity,transform;}',
      'html.app-leave-back body{opacity:0;transform:translate3d(.9rem,0,0) scale(.996);transition:opacity 180ms cubic-bezier(.4,0,1,1),transform 230ms cubic-bezier(.4,0,1,1);will-change:opacity,transform;}',
      'html.app-transitioning body{pointer-events:none;}'
    ].join('');
    document.head.appendChild(style);
  }

  function prepareEnter() {
    if (reduceMotion) return;

    var dir = readDir();
    var root = document.documentElement;
    root.classList.add(dir === 'back' ? 'app-enter-back' : 'app-enter-fwd');

    window.addEventListener('DOMContentLoaded', function () {
      requestAnimationFrame(function () {
        root.classList.add('app-enter-active');
        window.setTimeout(function () {
          root.classList.remove('app-enter-fwd', 'app-enter-back', 'app-enter-active');
          clearDir();
        }, 300);
      });
    });
  }

  function shouldSkipLink(event, anchor) {
    if (!anchor) return true;
    if (event.defaultPrevented) return true;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return true;
    if (anchor.target && anchor.target !== '_self') return true;
    if (anchor.hasAttribute('download')) return true;
    if (anchor.hasAttribute('data-no-transition')) return true;
    if (anchor.hasAttribute('data-fancybox') || anchor.closest('[data-fancybox]')) return true;

    var href = anchor.getAttribute('href');
    if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0) return true;

    var url;
    try { url = new URL(href, location.origin); } catch (_) { return true; }

    if (url.origin !== location.origin) return true;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return true;
    if (url.pathname.indexOf('/media/') === 0 || url.pathname.indexOf('/static/') === 0) return true;

    anchor._pwaTransitionUrl = url;
    return false;
  }

  function navigateWithTransition(anchor) {
    var url = anchor._pwaTransitionUrl;
    if (!url) return;

    var dir = directionFor(url);
    storeDir(dir);

    if (reduceMotion) {
      location.href = url.href;
      return;
    }

    var root = document.documentElement;
    root.classList.remove('app-enter-fwd', 'app-enter-back', 'app-enter-active');
    root.classList.add('app-transitioning', dir === 'back' ? 'app-leave-back' : 'app-leave-fwd');

    window.setTimeout(function () {
      location.href = url.href;
    }, LEAVE_MS);
  }

  injectStyles();
  prepareEnter();

  document.addEventListener('click', function (event) {
    var anchor = event.target.closest('a[href]');
    if (shouldSkipLink(event, anchor)) return;

    event.preventDefault();
    navigateWithTransition(anchor);
  }, true);

  window.addEventListener('pageshow', function () {
    document.documentElement.classList.remove(
      'app-transitioning',
      'app-leave-fwd',
      'app-leave-back'
    );
  });
})();
