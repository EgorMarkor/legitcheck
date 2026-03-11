/**
 * PWA Navigation — direction tracking for Capacitor transitions
 * Свайпы и анимации — только через Capacitor (нативный уровень)
 */
(function () {
  'use strict';

  var TAB_PATHS = ['/home/', '/verdicts/'];

  function tabIndex(pathname) {
    var clean = pathname.replace(/\?.*$/, '').replace(/#.*$/, '');
    return TAB_PATHS.indexOf(clean);
  }

  var SK = 'pwa_nav_dir';
  function storeDir(dir) {
    try { sessionStorage.setItem(SK, dir); } catch (e) {}
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href]');
    if (!a) return;
    if (a.target === '_blank') return;
    if (a.hasAttribute('data-no-transition')) return;

    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || href.startsWith('javascript')) return;

    var url;
    try { url = new URL(href, location.origin); } catch (_) { return; }
    if (url.origin !== location.origin) return;

    var fromIdx = tabIndex(location.pathname);
    var toIdx   = tabIndex(url.pathname);
    var dir;

    if (fromIdx !== -1 && toIdx !== -1) {
      dir = toIdx > fromIdx ? 'fwd' : 'back';
    } else if (url.pathname === '/' || url.pathname === '/home/') {
      dir = 'back';
    } else {
      dir = 'fwd';
    }

    storeDir(dir);
  }, true);

})();
