import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import * as WebBrowser from 'expo-web-browser';

import { fetchUserVerdicts } from '../api/client';
import { Verdict } from '../api/types';
import { AppHeader } from '../components/AppHeader';
import { RemoteAsset } from '../components/RemoteAsset';
import { API_BASE_URL, staticUrl } from '../constants/config';
import { colors } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { resolveImageUrl, verdictStatusColor, verdictStatusTitle } from '../utils/verdict';
import { useWebRem } from '../utils/rem';

const FILTERS = [
  { id: 'all', title: 'Все' },
  { id: 'processing', title: 'В обработке' },
  { id: 'todo', title: 'Требует действия' },
  { id: 'finish', title: 'Завершено' },
] as const;

export function AccountScreen() {
  const navigation = useNavigation<any>();
  const { user, signOut } = useAuth();
  const { r, width } = useWebRem();

  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['id']>('all');
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);

  const gridHorizontalPadding = r(1.25) * 2;
  const gridGap = r(0.5);
  const cardWidth = (width - gridHorizontalPadding - gridGap * 2) / 3;

  const load = async () => {
    if (!user) {
      return;
    }

    setLoading(true);
    try {
      const data = await fetchUserVerdicts(user.tgId);
      setVerdicts(data);
    } catch (error) {
      Alert.alert('Ошибка', error instanceof Error ? error.message : 'Не удалось загрузить профиль');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [user?.tgId]);

  const visibleVerdicts = useMemo(() => {
    if (filter === 'all') {
      return verdicts;
    }

    if (filter === 'processing') {
      return verdicts.filter((item) => item.status === 'inpending');
    }

    if (filter === 'todo') {
      return verdicts.filter((item) => item.status === 'todo');
    }

    return verdicts.filter((item) => item.status === 'legit' || item.status === 'fake');
  }, [filter, verdicts]);

  if (!user) {
    return null;
  }

  const profileAvatar = resolveImageUrl(user.img) ?? staticUrl('avatar.png');

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: r(3) }}>
      <AppHeader
        user={user}
        onBalancePress={() => navigation.navigate('Payment')}
        onAvatarPress={() => {}}
      />

      <View style={{ alignItems: 'center', marginTop: r(1) }}>
        <RemoteAsset uri={profileAvatar} width={r(10)} height={r(10)} style={{ borderRadius: r(5) }} resizeMode="cover" />
        <Text style={{ color: '#fff', fontSize: r(2), fontWeight: '700', marginTop: r(0.6) }}>{user.name}</Text>

        <View
          style={{
            marginTop: r(0.5),
            borderRadius: r(99),
            paddingHorizontal: r(1.7),
            paddingVertical: r(0.5),
            flexDirection: 'row',
            alignItems: 'center',
            gap: r(0.5),
            backgroundColor: '#11151a',
          }}
        >
          <RemoteAsset uri={staticUrl('calendar.svg')} width={r(1.2)} height={r(1.2)} />
          <Text style={{ color: '#464F5D', fontSize: r(1), fontWeight: '700' }}>21.03.2025</Text>
        </View>
      </View>

      <Text style={{ color: '#464F5D', fontSize: r(1.2), fontWeight: '500', marginTop: r(1.2), paddingHorizontal: r(2.5) }}>Ваш баланс</Text>

      <View style={{ marginTop: r(0.4), paddingHorizontal: r(1.5) }}>
        <View style={{ position: 'relative', borderRadius: r(1.2), overflow: 'hidden' }}>
          <RemoteAsset uri={staticUrl('balance_p.png')} width={width - r(3)} height={r(7.2)} resizeMode="cover" />
          <Text style={{ position: 'absolute', top: r(1.8), left: r(3.6), color: '#fff', fontSize: r(1.8), fontWeight: '700' }}>
            {user.balance} ₽
          </Text>
        </View>
      </View>

      <Text style={{ color: '#464F5D', fontSize: r(1.2), fontWeight: '500', marginTop: r(1.2), paddingHorizontal: r(2.5) }}>Заказы</Text>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: r(1.5), gap: r(0.5), paddingVertical: r(0.5) }}>
        {FILTERS.map((item) => {
          const active = filter === item.id;
          return (
            <Pressable
              key={item.id}
              onPress={() => setFilter(item.id)}
              style={{
                height: r(3),
                borderRadius: r(99),
                paddingHorizontal: r(1.5),
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: active ? '#fff' : '#11151a',
              }}
            >
              <Text style={{ color: active ? '#0B0E13' : '#464F5D', fontSize: r(1), fontWeight: active ? '700' : '500' }}>{item.title}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {loading ? (
        <ActivityIndicator style={{ marginTop: r(1) }} color={colors.success} />
      ) : (
        <View
          style={{
            marginHorizontal: r(1.25),
            marginTop: r(0.2),
            borderRadius: r(1.2),
            padding: r(1),
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: r(0.5),
            backgroundColor: 'rgba(23,28,36,0.75)',
            borderWidth: 1,
            borderColor: colors.border,
          }}
        >
          {visibleVerdicts.map((item) => {
            const preview = resolveImageUrl(item.photos?.[0]?.image_url ?? item.photos?.[0]?.image);
            const statusColor = verdictStatusColor(item.status);

            return (
              <Pressable
                key={item.id}
                onPress={() => navigation.navigate('VerdictDetail', { code: item.code })}
                style={{
                  width: cardWidth,
                  borderRadius: r(1.2),
                  marginBottom: r(0.5),
                  backgroundColor: '#0A0C11',
                  paddingBottom: r(0.5),
                }}
              >
                <View style={{ width: cardWidth, height: cardWidth, borderRadius: r(1.2), overflow: 'hidden', position: 'relative' }}>
                  {preview ? (
                    <RemoteAsset uri={preview} width={cardWidth} height={cardWidth} resizeMode="cover" />
                  ) : (
                    <View style={{ width: cardWidth, height: cardWidth, backgroundColor: '#1f2937' }} />
                  )}

                  <View
                    style={{
                      position: 'absolute',
                      top: r(0.55),
                      left: r(0.55),
                      width: cardWidth - r(1),
                      borderRadius: r(99),
                      backgroundColor: 'rgba(21,26,33,0.8)',
                      paddingVertical: r(0.24),
                      paddingHorizontal: r(0.45),
                      alignItems: 'center',
                    }}
                  >
                    <Text style={{ color: statusColor, fontSize: r(0.7), fontWeight: '700' }} numberOfLines={1}>
                      {item.status_display ?? verdictStatusTitle(item.status)}
                    </Text>
                  </View>
                </View>

                <View style={{ paddingHorizontal: r(0.5), paddingTop: r(0.25) }}>
                  <View
                    style={{
                      marginTop: r(0.4),
                      borderRadius: r(99),
                      paddingHorizontal: r(0.7),
                      paddingVertical: r(0.5),
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: r(0.25),
                      backgroundColor: '#11151a',
                    }}
                  >
                    <RemoteAsset uri={staticUrl('calendar.svg')} width={r(1.2)} height={r(1.2)} />
                    <Text style={{ color: '#464F5D', fontSize: r(0.8), fontWeight: '700' }}>
                      {new Date(item.created_at).toLocaleDateString('ru-RU')}
                    </Text>
                  </View>

                  <View
                    style={{
                      marginTop: r(0.4),
                      borderRadius: r(99),
                      paddingHorizontal: r(0.7),
                      paddingVertical: r(0.5),
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: '#11151a',
                    }}
                  >
                    <Text style={{ color: '#464F5D', fontSize: r(0.8), fontWeight: '700' }}>{item.code}</Text>
                  </View>
                </View>
              </Pressable>
            );
          })}

          {!visibleVerdicts.length && (
            <Text style={{ color: '#6B7280', fontSize: r(0.9) }}>У этого пользователя ещё нет вердиктов.</Text>
          )}
        </View>
      )}

      <View style={{ paddingHorizontal: r(1.5), marginTop: r(1) }}>
        <Pressable
          onPress={() => void WebBrowser.openBrowserAsync(`${API_BASE_URL}/license/`)}
          style={{
            backgroundColor: '#11151a',
            borderRadius: r(1.2),
            paddingHorizontal: r(1.5),
            paddingVertical: r(1),
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: r(0.5) }}>
            <RemoteAsset uri={staticUrl('file.svg')} width={r(1.2)} height={r(1.2)} />
            <Text style={{ color: '#fff', fontSize: r(1), fontWeight: '500' }}>Пользовательское соглашение</Text>
          </View>
          <RemoteAsset uri={staticUrl('arrow.svg')} width={r(3)} height={r(3)} />
        </Pressable>
      </View>

      <View style={{ paddingHorizontal: r(1.5), marginTop: r(0.8) }}>
        <Pressable
          onPress={() => void WebBrowser.openBrowserAsync(`${API_BASE_URL}/confident/`)}
          style={{
            backgroundColor: '#11151a',
            borderRadius: r(1.2),
            paddingHorizontal: r(1.5),
            paddingVertical: r(1),
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: r(0.5) }}>
            <RemoteAsset uri={staticUrl('file.svg')} width={r(1.2)} height={r(1.2)} />
            <Text style={{ color: '#fff', fontSize: r(1), fontWeight: '500' }}>Политика конфиденциональности</Text>
          </View>
          <RemoteAsset uri={staticUrl('arrow.svg')} width={r(3)} height={r(3)} />
        </Pressable>
      </View>

      <View style={{ paddingHorizontal: r(1.5), marginTop: r(1) }}>
        <Pressable
          onPress={() => void signOut()}
          style={{
            borderRadius: r(1.2),
            minHeight: r(3.3),
            backgroundColor: 'rgba(255,81,81,0.14)',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Text style={{ color: '#FF8B96', fontSize: r(1), fontWeight: '700' }}>Выйти</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
});
