import type { CapacitorConfig } from '@capacitor/cli';

const remoteUrl = process.env.PWA_URL || 'https://legitcheck.one';

const config: CapacitorConfig = {
  appId: 'one.legitcheck.app',
  appName: 'Checker',
  webDir: 'www',
  bundledWebRuntime: false,
  server: {
    url: remoteUrl,
    cleartext: remoteUrl.startsWith('http://'),
    allowNavigation: [
      '127.0.0.1',
      'localhost',
      'legitcheck.one',
      '*.legitcheck.one',
      't.me',
      'telegram.me',
      '*.yookassa.ru',
      'yookassa.ru'
    ]
  },
  ios: {
    contentInset: 'automatic',
    // Отключаем WKWebView-свайп (полноэкранный, дёрганый history.back).
    // Нативный edge-свайп от левого края остаётся работать через iOS UIGestureRecognizer.
    swipeBackEnabled: false
  }
};

export default config;
