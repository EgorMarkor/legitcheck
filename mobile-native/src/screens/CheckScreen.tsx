import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';

import { createMobileVerdict, uploadDraftPhotos } from '../api/client';
import { AppHeader } from '../components/AppHeader';
import { RemoteAsset } from '../components/RemoteAsset';
import { staticUrl } from '../constants/config';
import { colors } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { reasonPrice, tariffOptions } from '../constants/data';
import { useWebRem } from '../utils/rem';

type LocalPhoto = {
  uri: string;
  name: string;
  type: string;
};

type BrandTab = 'all' | 'basic' | 'luxury';

const LUXURY_BRANDS = new Set([
  'Balenciaga', 'Cartier', 'Celine', 'Chrome Hearts', 'Dior', 'Fendi',
  'Goyard', 'Gucci', 'Hermes', 'Jil Sander', 'Jimmy Choo', 'Loro Piana',
  'Louis Vuitton', 'Miu Miu', 'Moncler', 'Palm Angels', 'Prada', 'Rolex',
  'Rick Owens', 'Vetements',
]);

const ALL_BRANDS = [
  'Nike', 'Adidas', 'New Balance', 'Yeezy', 'Balenciaga', 'Dior', 'Gucci', 'Prada',
  'Moncler', 'Palm Angels', 'Stone Island', 'Supreme', 'Off-White', 'Louis Vuitton',
  'Asics', 'Puma', 'Reebok', 'Converse', 'Vans', 'Champion', 'Armani', 'Burberry',
  'Celine', 'Fendi', 'Hermes', 'Tommy Hilfiger', 'Lacoste', 'The North Face',
  'Canada Goose', 'Rolex', 'Casio', 'Tissot', 'Omega', 'Cartier', 'Balmain',
  'Bottega Veneta', 'MCM', 'Guess', 'Hugo Boss', 'Jacquemus', 'Maison Margiela',
];

const BRAND_LOGOS: Record<string, string> = {
  Nike: 'nike.png',
  'New Balance': 'newbalance.png',
  Yeezy: 'yeezy.png',
  Balenciaga: 'balenciaga.png',
  Dior: 'dior.png',
  Moncler: 'moncler.png',
  'Palm Angels': 'palmangels.png',
  'Stone Island': 'stoneisland.png',
  Supreme: 'supreme.png',
  'Louis Vuitton': 'louisvuitton.png',
  Champion: 'champion.png',
};

const CATEGORIES = [
  { id: 'sneakers', title: 'Кроссовки' },
  { id: 'clothes', title: 'Одежда' },
  { id: 'bags', title: 'Сумки' },
  { id: 'belts', title: 'Ремни' },
  { id: 'watch', title: 'Часы' },
  { id: 'cosmetics', title: 'Косметика' },
  { id: 'jewerly', title: 'Украшения' },
  { id: 'toys', title: 'Игрушки' },
  { id: 'accsesory', title: 'Аксессуары' },
  { id: 'others', title: 'Другое' },
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  sneakers: 'Кроссовки',
  clothes: 'Одежда',
  bags: 'Сумки',
  belts: 'Ремни',
  watch: 'Часы',
  cosmetics: 'Косметика',
  jewerly: 'Украшения',
  toys: 'Игрушки',
  accsesory: 'Аксессуары',
  others: 'Другое',
};

export function CheckScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { user } = useAuth();
  const { r, width } = useWebRem();

  const initialBrand = route.params?.brand as string | undefined;
  const isCategoryFirst = route.params?.order === 'category-brand' && !initialBrand;

  const [step, setStep] = useState(initialBrand ? 2 : 1);
  const [brandTab, setBrandTab] = useState<BrandTab>('all');
  const [brandSearch, setBrandSearch] = useState('');
  const [selectedBrand, setSelectedBrand] = useState<string | null>(initialBrand ?? null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [photos, setPhotos] = useState<LocalPhoto[]>([]);
  const [comment, setComment] = useState('');
  const [speed, setSpeed] = useState<(typeof tariffOptions)[number]['id']>('24h');
  const [withReason, setWithReason] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const categoryCardWidth = (width - r(2) - r(1) * 2) / 3;
  const brandCardWidth = (width - r(2) - r(0.5) * 2) / 3;

  const filteredBrands = useMemo(() => {
    const query = brandSearch.trim().toLowerCase();

    let source = [...ALL_BRANDS];
    if (brandTab === 'basic') {
      source = source.filter((name) => !LUXURY_BRANDS.has(name));
    } else if (brandTab === 'luxury') {
      source = source.filter((name) => LUXURY_BRANDS.has(name));
    }

    return source.filter((name) => !query || name.toLowerCase().includes(query));
  }, [brandSearch, brandTab]);

  const selectedTariff = tariffOptions.find((item) => item.id === speed) ?? tariffOptions[0];
  const total = selectedTariff.price + (withReason ? reasonPrice : 0);
  const balance = Number(user?.balance ?? 0);
  const requiredTopUp = Math.max(0, total - balance);

  const pickPhotos = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Нет доступа', 'Разрешите доступ к галерее в настройках устройства.');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      allowsEditing: false,
      allowsMultipleSelection: true,
      quality: 0.92,
      selectionLimit: 10,
    });

    if (result.canceled) {
      return;
    }

    const mapped: LocalPhoto[] = result.assets.map((asset, idx) => ({
      uri: asset.uri,
      name: asset.fileName ?? `photo-${Date.now()}-${idx}.jpg`,
      type: asset.mimeType ?? 'image/jpeg',
    }));

    setPhotos((prev) => [...prev, ...mapped]);
  };

  const removePhoto = (index: number) => {
    setPhotos((prev) => prev.filter((_, idx) => idx !== index));
  };

  const goBackStep = () => {
    if (step > 1) {
      setStep((prev) => prev - 1);
      return;
    }
    navigation.goBack();
  };

  const submitVerdict = async () => {
    if (!user) {
      return;
    }

    if (!selectedBrand || !selectedCategory) {
      Alert.alert('Ошибка', 'Выберите бренд и категорию.');
      return;
    }

    if (!photos.length) {
      Alert.alert('Ошибка', 'Добавьте хотя бы одно фото.');
      return;
    }

    if (requiredTopUp > 0) {
      navigation.getParent()?.navigate('Payment', { topUpAmount: requiredTopUp });
      return;
    }

    setSubmitting(true);
    try {
      const uploaded = await uploadDraftPhotos(user.tgId, photos);

      const created = await createMobileVerdict({
        tgId: user.tgId,
        category: selectedCategory,
        brand: selectedBrand,
        comment,
        speed,
        with_reason: withReason,
        photo_ids: uploaded.photo_ids,
      });

      Alert.alert('Успешно', 'Заявка создана и отправлена на проверку.');
      navigation.getParent()?.navigate('VerdictDetail', { code: created.verdict.code });

      setStep(1);
      setBrandSearch('');
      setSelectedBrand(null);
      setSelectedCategory(null);
      setPhotos([]);
      setComment('');
      setSpeed('24h');
      setWithReason(false);
    } catch (error) {
      Alert.alert('Ошибка', error instanceof Error ? error.message : 'Не удалось создать заявку');
    } finally {
      setSubmitting(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ paddingBottom: r(6) }}>
      <AppHeader
        user={user}
        onBalancePress={() => navigation.getParent()?.navigate('Payment')}
        onAvatarPress={() => navigation.getParent()?.navigate('Account')}
      />

      <View style={{ paddingHorizontal: r(1), paddingVertical: r(0.5) }}>
        <Text style={{ color: '#fff', fontSize: r(1.5), fontWeight: '700' }}>
          {step === 1
            ? (isCategoryFirst ? 'Выберите тип вещи' : 'Выберите бренд')
            : step === 2
              ? (isCategoryFirst ? 'Выберите бренд' : 'Выберите тип вещи')
              : step === 3
                ? 'Загрузите фото'
                : 'Подтверждение'}
        </Text>
        <Text style={{ color: '#737a86', fontSize: r(1), marginTop: r(0.4), lineHeight: r(1.25) }}>
          Мы предоставляем широкий ценовой спектр, чтобы каждый смог найти, что подходит именно ему.
        </Text>

        <View style={{ width: '100%', marginTop: r(0.8), height: r(0.5), borderRadius: r(2), backgroundColor: '#171C23', overflow: 'hidden' }}>
          <View style={{ width: `${step * 20}%`, height: r(0.5), borderRadius: r(2), backgroundColor: '#13CD90' }} />
        </View>
      </View>

      {step === (isCategoryFirst ? 2 : 1) && (
        <View style={{ paddingHorizontal: r(1), paddingBottom: r(1) }}>
          <View style={{
            marginBottom: r(1),
            flexDirection: 'row',
            borderRadius: r(99),
            backgroundColor: '#0C0F14',
            padding: r(0.25),
          }}>
            {([
              ['all', 'Все'],
              ['basic', 'Обычные'],
              ['luxury', 'Люкс'],
            ] as const).map(([id, label]) => {
              const active = brandTab === id;
              return (
                <Pressable
                  key={id}
                  onPress={() => setBrandTab(id)}
                  style={{
                    flex: 1,
                    borderRadius: r(99),
                    paddingVertical: r(0.8),
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: active ? '#171C23' : 'transparent',
                  }}
                >
                  <Text style={{ color: active ? '#fff' : '#a3a9b4', fontSize: r(0.95), fontWeight: active ? '700' : '500' }}>{label}</Text>
                </Pressable>
              );
            })}
          </View>

          <View style={{ marginBottom: r(1) }}>
            <TextInput
              value={brandSearch}
              onChangeText={setBrandSearch}
              placeholder="Поиск бренда..."
              placeholderTextColor={'#6b7280'}
              style={{
                width: '100%',
                borderRadius: r(99),
                backgroundColor: '#0C0F14',
                paddingHorizontal: r(1.25),
                paddingVertical: r(0.8),
                color: '#fff',
                fontSize: r(1),
              }}
            />
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: r(0.5) }}>
            {filteredBrands.map((brand) => {
              const active = selectedBrand === brand;
              const logoFile = BRAND_LOGOS[brand];
              return (
                <Pressable
                  key={brand}
                  onPress={() => {
                    setSelectedBrand(brand);
                    setStep(isCategoryFirst ? 3 : 2);
                  }}
                  style={{
                    width: brandCardWidth,
                    borderRadius: r(0.9),
                    minHeight: r(3.2),
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderWidth: 1,
                    borderColor: active ? '#13CD90' : '#1f2937',
                    backgroundColor: active ? 'rgba(19,205,144,0.15)' : '#11151A',
                    paddingHorizontal: r(0.5),
                    paddingVertical: r(0.4),
                  }}
                >
                  {logoFile ? (
                    <RemoteAsset uri={staticUrl(logoFile)} width={r(3)} height={r(3)} resizeMode="contain" />
                  ) : null}
                  <Text
                    style={{
                      color: active ? '#fff' : '#c6d0df',
                      fontSize: r(0.85),
                      textAlign: 'center',
                      marginTop: logoFile ? r(0.2) : 0,
                    }}
                  >
                    {brand}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      )}

      {step === (isCategoryFirst ? 1 : 2) && (
        <View style={{ paddingHorizontal: r(1), paddingBottom: r(1) }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: r(0.5) }}>
            {CATEGORIES.map((item) => {
              const active = selectedCategory === item.id;
              return (
                <Pressable
                  key={item.id}
                  onPress={() => {
                    setSelectedCategory(item.id);
                    setStep(isCategoryFirst ? 2 : 3);
                  }}
                  style={{
                    width: categoryCardWidth,
                    alignItems: 'center',
                    gap: r(0.25),
                    borderRadius: r(1),
                    borderWidth: active ? 1 : 0,
                    borderColor: '#13CD90',
                    paddingVertical: r(0.4),
                  }}
                >
                  <RemoteAsset uri={staticUrl(`categories/${item.id}.png`)} width={categoryCardWidth} height={categoryCardWidth} resizeMode="cover" style={{ borderRadius: r(0.9) }} />
                  <Text style={{ color: '#fff', fontSize: r(0.85), textAlign: 'center' }}>{item.title}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      )}

      {step === 3 && (
        <View style={{ paddingHorizontal: r(1), paddingBottom: r(1), gap: r(0.8) }}>
          <Text style={{ color: '#fff', fontSize: r(1.25), fontWeight: '600' }}>Необходимые фотографии</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: r(0.5) }}>
            {Array.from({ length: 6 }).map((_, index) => (
              <View key={index} style={{ width: categoryCardWidth, alignItems: 'center', gap: r(0.2) }}>
                <RemoteAsset
                  uri={selectedCategory ? staticUrl(`categories/${selectedCategory}.png`) : staticUrl('categories/sneakers.png')}
                  width={categoryCardWidth}
                  height={categoryCardWidth}
                  style={{ borderRadius: r(0.8), opacity: 0.75 }}
                  resizeMode="cover"
                />
                <Text style={{ color: '#d1d5db', fontSize: r(0.72), textAlign: 'center' }}>Ракурс {index + 1}</Text>
              </View>
            ))}
          </View>

          <Text style={{ color: '#fff', fontSize: r(1.25), fontWeight: '600', marginTop: r(0.5) }}>Загрузите свои фото</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: r(0.5) }}>
            <Pressable
              onPress={() => void pickPhotos()}
              style={{
                width: r(6.8),
                height: r(6.8),
                borderRadius: r(1),
                borderWidth: 1,
                borderStyle: 'dashed',
                borderColor: '#4b5563',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: '#11151A',
              }}
            >
              <Text style={{ color: '#9ca3af', fontSize: r(0.8) }}>+ Фото</Text>
            </Pressable>

            {photos.map((photo, index) => (
              <Pressable key={`${photo.uri}-${index}`} onPress={() => removePhoto(index)}>
                <RemoteAsset uri={photo.uri} width={r(6.8)} height={r(6.8)} style={{ borderRadius: r(1) }} resizeMode="cover" />
              </Pressable>
            ))}
          </ScrollView>

          <TextInput
            value={comment}
            onChangeText={setComment}
            placeholder="Комментарий для менеджера"
            placeholderTextColor="#6b7280"
            style={{
              borderRadius: r(1),
              borderWidth: 1,
              borderColor: 'rgba(179,214,255,0.08)',
              backgroundColor: '#11151A',
              minHeight: r(4),
              paddingHorizontal: r(0.9),
              paddingVertical: r(0.7),
              color: '#fff',
              fontSize: r(0.95),
              textAlignVertical: 'top',
            }}
            multiline
          />

          <Pressable
            onPress={() => setStep(4)}
            disabled={!selectedCategory || !photos.length}
            style={{
              minHeight: r(3.8),
              borderRadius: r(1),
              backgroundColor: selectedCategory && photos.length ? '#13CD90' : '#1f2937',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '700' }}>Продолжить</Text>
          </Pressable>
        </View>
      )}

      {step === 4 && (
        <View style={{ paddingHorizontal: r(1), paddingBottom: r(1), gap: r(0.75) }}>
          <View style={{
            borderRadius: r(1.2),
            padding: r(1),
            backgroundColor: '#11151A',
            borderWidth: 1,
            borderColor: 'rgba(179,214,255,0.08)',
          }}>
            <Text style={{ color: '#6b7280', fontSize: r(0.8) }}>Категория</Text>
            <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '600' }}>{selectedCategory ? CATEGORY_LABELS[selectedCategory] : '-'}</Text>
            <Text style={{ color: '#6b7280', fontSize: r(0.8), marginTop: r(0.25) }}>Бренд</Text>
            <Text style={{ color: '#fff', fontSize: r(1.1), fontWeight: '600' }}>{selectedBrand ?? '-'}</Text>

            {photos[0] ? (
              <View style={{ marginTop: r(0.6), alignItems: 'flex-start' }}>
                <RemoteAsset uri={photos[0].uri} width={r(8)} height={r(8)} style={{ borderRadius: r(0.6) }} resizeMode="cover" />
              </View>
            ) : null}
          </View>

          {tariffOptions.map((tariff) => {
            const active = speed === tariff.id;
            return (
              <Pressable
                key={tariff.id}
                onPress={() => setSpeed(tariff.id)}
                style={{
                  borderRadius: r(1),
                  borderWidth: 1,
                  borderColor: active ? '#13CD90' : '#1f2937',
                  backgroundColor: active ? 'rgba(19,205,144,0.14)' : '#11151A',
                  minHeight: r(3.6),
                  paddingHorizontal: r(0.8),
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <Text style={{ color: '#fff', fontSize: r(1), fontWeight: '600' }}>{tariff.title}</Text>
                <Text style={{ color: '#fff', fontSize: r(1), fontWeight: '700' }}>{tariff.price} ₽</Text>
              </Pressable>
            );
          })}

          <View style={{
            borderRadius: r(1),
            paddingHorizontal: r(0.8),
            paddingVertical: r(0.5),
            backgroundColor: '#11151A',
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: r(0.8),
          }}>
            <Text style={{ color: '#fff', fontSize: r(0.95), flex: 1 }}>Письменное обоснование (+150 ₽)</Text>
            <Switch value={withReason} onValueChange={setWithReason} trackColor={{ true: '#13CD90', false: '#374151' }} />
          </View>

          <View style={{
            borderRadius: r(1),
            padding: r(0.8),
            backgroundColor: '#11151A',
            borderWidth: 1,
            borderColor: 'rgba(179,214,255,0.08)',
            gap: r(0.35),
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: '#6b7280', fontSize: r(0.9) }}>Тариф</Text>
              <Text style={{ color: '#fff', fontSize: r(0.95), fontWeight: '600' }}>{selectedTariff.price} ₽</Text>
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: '#6b7280', fontSize: r(0.9) }}>Обоснование</Text>
              <Text style={{ color: '#fff', fontSize: r(0.95), fontWeight: '600' }}>{withReason ? `${reasonPrice} ₽` : '0 ₽'}</Text>
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: r(0.2) }}>
              <Text style={{ color: '#6b7280', fontSize: r(1) }}>Итого</Text>
              <Text style={{ color: '#fff', fontSize: r(1.35), fontWeight: '700' }}>{total} ₽</Text>
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: '#6b7280', fontSize: r(0.9) }}>Баланс</Text>
              <Text style={{ color: '#fff', fontSize: r(0.95), fontWeight: '600' }}>{balance} ₽</Text>
            </View>
          </View>

          {requiredTopUp > 0 ? (
            <Pressable
              onPress={() => navigation.getParent()?.navigate('Payment', { topUpAmount: requiredTopUp })}
              style={{
                minHeight: r(3.8),
                borderRadius: r(1),
                backgroundColor: '#13CD90',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: '#fff', fontSize: r(1.05), fontWeight: '700' }}>Пополнить на {requiredTopUp} ₽</Text>
            </Pressable>
          ) : (
            <Pressable
              onPress={() => void submitVerdict()}
              disabled={submitting}
              style={{
                minHeight: r(3.8),
                borderRadius: r(1),
                backgroundColor: submitting ? '#1f2937' : '#13CD90',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: '#fff', fontSize: r(1.05), fontWeight: '700' }}>{submitting ? 'Отправляем...' : 'Создать заявку'}</Text>
            </Pressable>
          )}
        </View>
      )}

      <View style={{ paddingHorizontal: r(1) }}>
        <Pressable onPress={goBackStep} style={{ marginTop: r(0.8), alignSelf: 'flex-start' }}>
          <Text style={{ color: '#9ca3af', fontSize: r(0.9) }}>← Назад</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}
