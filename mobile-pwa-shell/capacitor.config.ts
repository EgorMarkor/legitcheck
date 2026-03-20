import type { CapacitorConfig } from '@capacitor/cli';

const remoteUrl = process.env.PWA_URL || 'https://legitcheck.one';

const config: CapacitorConfig = {
  appId: 'com.markor.legitcheck',
  appName: 'Checker',
  webDir: 'www',
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
    contentInset: 'never',
    backgroundColor: '#0c0f16'
  }
};

export default config;
