/**
 * PWA Navigation
 * Tracks page direction for native shells without delaying browser navigation.
 */
(function () {
  'use strict';

  var TAB_PATHS = ['/home/', '/verdicts/'];
  var STORAGE_KEY = 'pwa_nav_dir';

  function tabIndex(pathname) {
    var clean = pathname.replace(/\?.*$/, '').replace(/#.*$/, '');
    return TAB_PATHS.indexOf(clean);
  }

  function storeDir(dir) {
    try { sessionStorage.setItem(STORAGE_KEY, dir); } catch (_) {}
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

  function linkUrl(anchor) {
    if (!anchor) return null;
    if (anchor.target && anchor.target !== '_self') return null;
    if (anchor.hasAttribute('download')) return null;
    if (anchor.hasAttribute('data-no-transition')) return null;
    if (anchor.hasAttribute('data-fancybox') || anchor.closest('[data-fancybox]')) return null;

    var href = anchor.getAttribute('href');
    if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0) return null;

    var url;
    try { url = new URL(href, location.origin); } catch (_) { return null; }

    if (url.origin !== location.origin) return null;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return null;
    if (url.pathname.indexOf('/media/') === 0 || url.pathname.indexOf('/static/') === 0) return null;

    return url;
  }

  document.addEventListener('click', function (event) {
    if (event.defaultPrevented) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    var anchor = event.target.closest('a[href]');
    var url = linkUrl(anchor);
    if (!url) return;

    storeDir(directionFor(url));
  }, true);
})();
