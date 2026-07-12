import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation, useRoute } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';

import { fetchVerdictByCode, uploadPhotoToVerdict } from '../api/client';
import { Verdict } from '../api/types';
import { colors, gradients } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { AppHeader } from '../components/AppHeader';
import { RemoteAsset } from '../components/RemoteAsset';
import { staticUrl } from '../constants/config';
import { resolveImageUrl, verdictStatusTitle } from '../utils/verdict';
import { useWebRem } from '../utils/rem';

export function VerdictDetailScreen() {
  const route = useRoute<any>();
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const { r, width } = useWebRem();

  const code = route.params?.code as string | undefined;

  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const photoItems = useMemo(() => {
    if (!verdict) {
      return [];
    }

    return verdict.photos
      .map((photo) => ({
        ...photo,
        image_url: resolveImageUrl(photo.image_url ?? photo.image),
      }))
      .filter((photo) => Boolean(photo.image_url));
  }, [verdict]);

  const load = async () => {
    if (!code) {
      setLoading(false);
      Alert.alert('Ошибка', 'Код вердикта не передан');
      return;
    }

    setLoading(true);
    try {
      const data = await fetchVerdictByCode(code);
      setVerdict(data);
    } catch (error) {
      Alert.alert('Ошибка', error instanceof Error ? error.message : 'Не удалось загрузить вердикт');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [code]);

  const addPhoto = async () => {
    if (!verdict || !user) {
      return;
    }

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Нет доступа', 'Разрешите доступ к галерее');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      allowsEditing: false,
      quality: 0.92,
    });

    if (result.canceled) {
      return;
    }

    const asset = result.assets[0];
    if (!asset) {
      return;
    }

    setUploading(true);
    try {
      const response = await uploadPhotoToVerdict(verdict.id, user.tgId, {
        uri: asset.uri,
        name: asset.fileName ?? `verdict-photo-${Date.now()}.jpg`,
        type: asset.mimeType ?? 'image/jpeg',
      });
      setVerdict(response.verdict);
    } catch (error) {
      Alert.alert('Ошибка', error instanceof Error ? error.message : 'Не удалось загрузить фото');
    } finally {
      setUploading(false);
    }
  };

  if (!user) {
    return null;
  }

  if (loading) {
    return (
      <View style={styles.loadingRoot}>
        <ActivityIndicator color={colors.success} size="large" />
      </View>
    );
  }

  if (!verdict) {
    return (
      <View style={styles.loadingRoot}>
        <Text style={{ color: '#fff', fontSize: r(1.3), fontWeight: '700' }}>Вердикт не найден</Text>
      </View>
    );
  }

  const status = verdict.status;
  const statusTitle = verdict.status_display ?? verdictStatusTitle(status);
  const statusGradient = status === 'fake'
    ? gradients.dangerSoft
    : status === 'legit'
      ? gradients.successSoft
      : gradients.warningSoft;
  const statusColor = status === 'fake' ? '#FF5151' : status === 'legit' ? '#10B781' : '#FFC107';

  const mainPhotoUrl = resolveImageUrl(verdict.first_photo_url ?? verdict.photos[0]?.image_url ?? verdict.photos[0]?.image);
  const codeChars = (() => {
    const values = verdict.code.split('').slice(0, 5);
    while (values.length < 5) {
      values.push('*');
    }
    return values;
  })();
  const gridGap = r(0.5);
  const photoCellSize = (width - r(3) - gridGap * 2) / 3;

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: r(2.5) }}>
      <AppHeader
        user={user}
        onBalancePress={() => navigation.navigate('Payment')}
        onAvatarPress={() => navigation.navigate('Account')}
      />

      <View style={{ paddingHorizontal: r(1.5), marginTop: r(1) }}>
        <Text style={{ color: '#fff', fontSize: r(1.6), fontWeight: '700' }}>Вердикты</Text>
        <Text style={{ color: '#464F5D', fontSize: r(1.2), marginTop: r(0.4) }}>
          Введите код вердикта, чтобы проверить оригинальность изделия
        </Text>

        <View style={{ flexDirection: 'row', gap: r(0.5), justifyContent: 'center', marginTop: r(2) }}>
          {Array.from({ length: 5 }).map((_, index) => (
            <View
              key={index}
              style={{
                width: r(5),
                height: r(3.6),
                borderRadius: r(0.5),
                borderWidth: 1,
                borderColor: 'rgba(179,214,255,0.08)',
                backgroundColor: '#11151A',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: '#fff', fontSize: r(1.5), fontWeight: '700' }}>{codeChars[index] ?? '*'}</Text>
            </View>
          ))}
        </View>

        <LinearGradient
          colors={statusGradient}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={{
            marginTop: r(1),
            borderRadius: r(1),
            paddingVertical: r(1.5),
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Text style={{ color: statusColor, fontSize: r(1.2), fontWeight: '700' }}>Отчёт найден</Text>
        </LinearGradient>

        <LinearGradient
          colors={['#171C24', '#11151A']}
          style={{
            marginTop: r(1),
            borderRadius: r(1.2),
            padding: r(1),
          }}
        >
          <View
            style={{
              borderRadius: r(1.2),
              backgroundColor: '#0B0D11',
              padding: r(1),
              flexDirection: 'row',
              alignItems: 'center',
              gap: r(0.8),
            }}
          >
            <View style={{ flex: 1 }}>
              <Text style={{ color: '#6B7280', fontSize: r(0.8) }}>Категория</Text>
              <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '600', marginBottom: r(0.3) }}>
                {verdict.category_display ?? verdict.category}
              </Text>

              <Text style={{ color: '#6B7280', fontSize: r(0.8) }}>Бренд</Text>
              <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '600', marginBottom: r(0.3) }}>{verdict.brand}</Text>

              <Text style={{ color: '#6B7280', fontSize: r(0.8) }}>Вердикт</Text>
              <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '600', marginBottom: r(0.3) }}>{statusTitle}</Text>

              <Text style={{ color: '#6B7280', fontSize: r(0.8) }}>Комментарий от Менеджера</Text>
              <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '600' }}>{verdict.comment || '—'}</Text>
            </View>

            {mainPhotoUrl ? (
              <RemoteAsset
                uri={mainPhotoUrl}
                width={r(8)}
                height={r(8)}
                style={{ borderRadius: r(0.6) }}
                resizeMode="cover"
              />
            ) : null}
          </View>
        </LinearGradient>

        <Text style={{ color: '#fff', fontSize: r(1.2), marginTop: r(1), marginBottom: r(0.5), paddingHorizontal: r(1.5) }}>
          Фотографии в отчете
        </Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: gridGap, marginTop: r(1), paddingBottom: r(1) }}>
          {photoItems.map((item) => (
            <View
              key={item.id}
              style={{
                width: photoCellSize,
                height: r(8),
                borderRadius: r(1.2),
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <RemoteAsset uri={item.image_url as string} width={photoCellSize} height={r(8)} resizeMode="cover" />
              <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.45)' }} />
              <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' }}>
                <RemoteAsset uri={staticUrl('check.png')} width={r(3)} height={r(3)} />
              </View>
            </View>
          ))}
          {!photoItems.length ? (
            <Text style={{ color: '#9CA3AF', fontSize: r(0.95), paddingHorizontal: r(0.2) }}>Фотографий нет.</Text>
          ) : null}
        </View>

        {verdict.status === 'todo' ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: gridGap, marginTop: r(0.5), paddingBottom: r(1.5) }}>
          <Pressable
            onPress={() => void addPhoto()}
            style={{
              width: photoCellSize,
              height: r(8),
              borderRadius: r(1.2),
              borderWidth: 1,
              borderStyle: 'dashed',
              borderColor: '#4B5563',
              backgroundColor: '#0B0D11',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ color: '#9CA3AF', fontSize: r(0.8) }}>{uploading ? 'Загрузка...' : '+ Добавить фото'}</Text>
          </Pressable>
        </View>
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  loadingRoot: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
