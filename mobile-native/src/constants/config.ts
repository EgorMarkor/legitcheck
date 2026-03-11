const envApiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
const envTelegramBotUrl = process.env.EXPO_PUBLIC_TELEGRAM_BOT_URL;

export const API_BASE_URL = (envApiBaseUrl ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
export const TELEGRAM_BOT_URL = envTelegramBotUrl ?? 'https://t.me/LegitLogisticsBot?start=login';

export const staticUrl = (name: string) => `${API_BASE_URL}/static/${name}`;
