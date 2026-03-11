import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { createLoginToken, pollLoginToken } from '../api/client';
import { TELEGRAM_BOT_URL } from '../constants/config';
import { colors } from '../constants/theme';
import { GradientButton } from '../components/GradientButton';
import { useAuth } from '../context/AuthContext';

export function AuthScreen() {
  const { setUser } = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusText, setStatusText] = useState('Готовим код авторизации...');

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const secondsLeft = useMemo(() => {
    if (!expiresAt) {
      return 0;
    }
    return Math.max(0, Math.round(expiresAt - Date.now() / 1000));
  }, [expiresAt]);

  const stopTimers = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }

    if (countdownTimer.current) {
      clearInterval(countdownTimer.current);
      countdownTimer.current = null;
    }
  };

  const initToken = async () => {
    stopTimers();
    setLoading(true);

    try {
      const payload = await createLoginToken();
      setToken(payload.token);
      setExpiresAt(payload.expires_at_ts);
      setStatusText('Откройте Telegram-бота и отправьте код из приложения.');

      countdownTimer.current = setInterval(() => {
        setExpiresAt((prev) => {
          if (!prev) {
            return prev;
          }

          if (prev <= Date.now() / 1000) {
            stopTimers();
            setStatusText('Код истёк. Выпустите новый код.');
          }

          return prev;
        });
      }, 1000);

      pollTimer.current = setInterval(async () => {
        try {
          const data = await pollLoginToken(payload.token);

          if (!('authenticated' in data) || !data.authenticated) {
            if ('expired' in data && data.expired) {
              stopTimers();
              setStatusText('Код истёк. Выпустите новый код.');
            }
            return;
          }

          stopTimers();
          await setUser(data.user);
        } catch {
          setStatusText('Проблема с сетью. Повторим проверку...');
        }
      }, 3000);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Ошибка инициализации';
      setStatusText(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void initToken();

    return () => {
      stopTimers();
    };
  }, []);

  return (
    <View style={styles.root}>
      <View style={styles.card}>
        <Text style={styles.title}>Вход через Telegram</Text>
        <Text style={styles.subtitle}>Нативная версия использует тот же способ авторизации, что и веб-приложение.</Text>

        <View style={styles.tokenBox}>
          {loading ? <ActivityIndicator color={colors.success} /> : <Text style={styles.tokenText}>{token ?? '------'}</Text>}
        </View>

        <Text style={styles.status}>{statusText}</Text>
        <Text style={styles.expire}>Код активен: {secondsLeft} сек.</Text>

        <GradientButton
          title="Открыть Telegram Бота"
          onPress={() => {
            void Linking.openURL(TELEGRAM_BOT_URL);
          }}
        />

        <Pressable onPress={() => void initToken()} style={styles.linkBtn}>
          <Text style={styles.linkBtnText}>Получить новый код</Text>
        </Pressable>

        <Pressable
          onPress={() => Alert.alert('Как войти', '1. Нажмите "Открыть Telegram Бота"\n2. Отправьте боту код с экрана\n3. Дождитесь автоматического входа')}
          style={styles.hintWrap}
        >
          <Text style={styles.hintText}>Как это работает?</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  card: {
    width: '100%',
    maxWidth: 520,
    borderRadius: 28,
    padding: 22,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 14,
  },
  title: {
    color: '#fff',
    fontSize: 28,
    fontWeight: '700',
  },
  subtitle: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 21,
  },
  tokenBox: {
    marginTop: 6,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 70,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0f131a',
  },
  tokenText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 34,
    letterSpacing: 6,
  },
  status: {
    color: '#fff',
    fontSize: 15,
  },
  expire: {
    color: colors.muted,
    fontSize: 13,
  },
  linkBtn: {
    alignSelf: 'center',
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  linkBtnText: {
    color: colors.success,
    fontSize: 14,
    fontWeight: '700',
  },
  hintWrap: {
    alignSelf: 'center',
    paddingVertical: 8,
    paddingHorizontal: 10,
  },
  hintText: {
    color: '#6f7e92',
    fontSize: 12,
  },
});
