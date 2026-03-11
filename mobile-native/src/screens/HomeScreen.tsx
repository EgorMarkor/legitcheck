import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import { AppHeader } from '../components/AppHeader';
import { RemoteAsset } from '../components/RemoteAsset';
import { useAuth } from '../context/AuthContext';
import { brandItems, promoImages } from '../constants/data';
import { colors } from '../constants/theme';
import { staticUrl } from '../constants/config';
import { useWebRem } from '../utils/rem';

function BrandRow({
  title,
  items,
  onPress,
  r,
}: {
  title: string;
  items: { id: string; image: string }[];
  onPress: (brandId: string) => void;
  r: (value: number) => number;
}) {
  return (
    <>
      <Text style={{ color: '#9AA3AF', fontSize: r(0.875), marginTop: r(1.2), marginBottom: r(0.5), paddingHorizontal: r(1) }}>{title}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: r(0.5), paddingHorizontal: r(1) }}>
        {items.map((brand) => (
          <Pressable key={brand.id} onPress={() => onPress(brand.id)}>
            <RemoteAsset uri={brand.image} width={r(9)} height={r(9)} />
          </Pressable>
        ))}
      </ScrollView>
    </>
  );
}

export function HomeScreen() {
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const { r, width } = useWebRem();

  const groups = useMemo(() => ({
    sneakers: brandItems.filter((item) => item.category === 'sneakers'),
    clothes: brandItems.filter((item) => item.category === 'clothes'),
    premium: brandItems.filter((item) => item.category === 'premium'),
    popular: brandItems.filter((item) => item.category === 'popular'),
  }), []);

  if (!user) {
    return null;
  }

  const goCheck = (brand?: string) => {
    navigation.navigate('Check', brand ? { brand } : undefined);
  };

  const halfCardWidth = (width - r(2) - r(0.75)) / 2;

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: r(8) }}>
      <AppHeader
        user={user}
        onBalancePress={() => navigation.getParent()?.navigate('Payment')}
        onAvatarPress={() => navigation.getParent()?.navigate('Account')}
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: r(0.5) }} contentContainerStyle={{ paddingHorizontal: r(1), gap: r(0.5) }}>
        {promoImages.map((uri, idx) => (
          <RemoteAsset key={`${uri}-${idx}`} uri={uri} width={r(26.5)} height={r(9.8)} style={{ borderRadius: r(1.2) }} resizeMode="cover" />
        ))}
      </ScrollView>

      <View style={{ flexDirection: 'row', gap: r(0.75), paddingHorizontal: r(1), marginTop: r(1) }}>
        <Pressable onPress={() => goCheck()} style={{ flex: 1 }}>
          <RemoteAsset uri={staticUrl('start_prov.png')} width={halfCardWidth} height={r(9)} resizeMode="cover" style={{ borderRadius: r(0.8) }} />
        </Pressable>
        <Pressable onPress={() => goCheck()} style={{ flex: 1 }}>
          <RemoteAsset uri={staticUrl('find_brend.png')} width={halfCardWidth} height={r(9)} resizeMode="cover" style={{ borderRadius: r(0.8) }} />
        </Pressable>
      </View>

      <BrandRow title="Кроссовки" items={groups.sneakers} onPress={goCheck} r={r} />
      <BrandRow title="Одежда" items={groups.clothes} onPress={goCheck} r={r} />
      <BrandRow title="Премиальная обувь" items={groups.premium} onPress={goCheck} r={r} />

      <View style={{ flexDirection: 'row', gap: r(0.75), paddingHorizontal: r(1), marginTop: r(1) }}>
        <Pressable style={{ flex: 1 }}>
          <RemoteAsset uri={staticUrl('our_garanties.png')} width={halfCardWidth} height={r(9)} resizeMode="cover" style={{ borderRadius: r(0.8) }} />
        </Pressable>
        <Pressable style={{ flex: 1 }}>
          <RemoteAsset uri={staticUrl('how_me_work.png')} width={halfCardWidth} height={r(9)} resizeMode="cover" style={{ borderRadius: r(0.8) }} />
        </Pressable>
      </View>

      <BrandRow title="Популярные бренды" items={groups.popular} onPress={goCheck} r={r} />

      <View style={{ flexDirection: 'row', gap: r(0.75), paddingHorizontal: r(1), marginTop: r(1) }}>
        <Pressable style={{ flex: 1 }}>
          <RemoteAsset uri={staticUrl('how_check.png')} width={halfCardWidth} height={r(9)} resizeMode="cover" style={{ borderRadius: r(0.8) }} />
        </Pressable>
        <Pressable style={{ flex: 1 }}>
          <RemoteAsset uri={staticUrl('full_finance.png')} width={halfCardWidth} height={r(9)} resizeMode="cover" style={{ borderRadius: r(0.8) }} />
        </Pressable>
      </View>

      <Text style={{ color: '#fff', fontSize: r(0.9), fontWeight: '700', paddingHorizontal: r(1), marginTop: r(1.3), marginBottom: r(0.5) }}>
        🔥 Самые популярные позиции
      </Text>

      <View style={{ paddingHorizontal: r(1), gap: r(0.7) }}>
        {[1, 2, 3, 4, 5].map((rank) => (
          <View
            key={rank}
            style={{
              borderRadius: r(1.2),
              padding: r(1),
              gap: r(0.8),
              flexDirection: 'row',
              backgroundColor: '#11151a',
            }}
          >
            <View style={{ position: 'relative' }}>
              <View
                style={{
                  position: 'absolute',
                  top: r(0.6),
                  left: r(0.6),
                  width: r(2.6),
                  height: r(2.6),
                  borderRadius: r(1.3),
                  backgroundColor: '#000',
                  alignItems: 'center',
                  justifyContent: 'center',
                  zIndex: 3,
                }}
              >
                <Text style={{ color: '#fff', fontSize: r(0.95), fontWeight: '700' }}>#{rank}</Text>
              </View>
              <RemoteAsset
                uri={staticUrl('balenciaga_track.png')}
                width={r(13)}
                height={r(13)}
                style={{ borderRadius: r(1.2) }}
                resizeMode="cover"
              />
            </View>

            <View style={{ flex: 1, paddingTop: r(0.5) }}>
              <Text style={{ color: '#fff', fontSize: r(1.5), lineHeight: r(1.6), fontWeight: '700' }}>
                Balenciaga Track{"\n"}"White Orange"
              </Text>

              <View style={{ flexDirection: 'row', gap: r(0.4), marginTop: r(0.7), alignItems: 'center' }}>
                <View style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: r(0.3),
                  paddingHorizontal: r(0.7),
                  paddingVertical: r(0.55),
                  borderRadius: r(99),
                  backgroundColor: '#000',
                }}>
                  <RemoteAsset uri={staticUrl('success_icon.svg')} width={r(1.5)} height={r(1.5)} />
                  <Text style={{ color: '#fff', fontSize: r(0.9), fontWeight: '600' }}>231</Text>
                </View>

                <View style={{ paddingHorizontal: r(0.7), paddingVertical: r(0.55), borderRadius: r(99), backgroundColor: 'rgba(19,205,144,0.15)' }}>
                  <Text style={{ color: '#13CD90', fontSize: r(0.9), fontWeight: '600' }}>43%</Text>
                </View>

                <View style={{ paddingHorizontal: r(0.7), paddingVertical: r(0.55), borderRadius: r(99), backgroundColor: 'rgba(255,65,65,0.15)' }}>
                  <Text style={{ color: '#FF3D41', fontSize: r(0.9), fontWeight: '600' }}>57%</Text>
                </View>
              </View>
            </View>
          </View>
        ))}
      </View>

      <View style={{ height: r(1.5) }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
});
