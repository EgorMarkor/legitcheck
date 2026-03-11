import React, { useMemo, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import * as WebBrowser from 'expo-web-browser';

import { createYookassaPayment } from '../api/client';
import { AppHeader } from '../components/AppHeader';
import { RemoteAsset } from '../components/RemoteAsset';
import { staticUrl } from '../constants/config';
import { colors } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { useWebRem } from '../utils/rem';

export function PaymentScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { user, refreshUser } = useAuth();
  const { r, width } = useWebRem();

  const suggested = route.params?.topUpAmount as number | undefined;

  const [amount, setAmount] = useState(suggested ? String(Math.ceil(suggested)) : '');
  const [processing, setProcessing] = useState(false);

  const amountNumber = useMemo(() => {
    const cleaned = amount.replace(/\s/g, '').replace('₽', '').replace(',', '.');
    const parsed = Number(cleaned);
    if (Number.isNaN(parsed)) {
      return 0;
    }
    return parsed;
  }, [amount]);

  const proceed = async () => {
    if (!user) {
      return;
    }

    if (amountNumber < 10) {
      Alert.alert('Слишком маленькая сумма', 'Минимум 10 ₽');
      return;
    }

    setProcessing(true);
    try {
      const payload = await createYookassaPayment(user.tgId, amountNumber);
      await WebBrowser.openBrowserAsync(payload.url);
      await refreshUser();
      navigation.goBack();
    } catch (error) {
      Alert.alert('Ошибка', error instanceof Error ? error.message : 'Не удалось создать платеж');
    } finally {
      setProcessing(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <View style={styles.root}>
      <AppHeader
        user={user}
        onBalancePress={() => {}}
        onAvatarPress={() => navigation.navigate('Account')}
      />

      <View style={{ paddingHorizontal: r(4), marginTop: r(0.7), alignItems: 'center' }}>
        <RemoteAsset uri={staticUrl('moneta_yookassa.png')} width={width - r(8)} height={r(13)} resizeMode="contain" />
      </View>

      <View style={{ paddingHorizontal: r(2.5), marginTop: r(0.5) }}>
        <Text style={{ color: '#fff', fontSize: r(1.6), fontWeight: '700' }}>Способы оплаты</Text>
        <Text style={{ color: '#464F5D', fontSize: r(1.2), marginTop: r(0.3), lineHeight: r(1.3) }}>
          В скором времени мы добавим{"\n"}еще больше методов пополнения баланса
        </Text>
      </View>

      <View style={{ paddingHorizontal: r(1.5), marginTop: r(0.6) }}>
        <View
          style={{
            borderRadius: r(1.46),
            padding: r(1.5),
            backgroundColor: '#11151a',
          }}
        >
          <Text style={{ color: '#464F5D', fontSize: r(1), fontWeight: '500' }}>Сумма пополнения</Text>
          <TextInput
            value={amount}
            onChangeText={setAmount}
            keyboardType="decimal-pad"
            placeholder="250 ₽"
            placeholderTextColor={'rgba(255,255,255,0.5)'}
            style={{
              color: '#fff',
              fontSize: r(1.6),
              fontWeight: '700',
              marginTop: r(0.3),
              paddingVertical: 0,
            }}
          />
        </View>

        <Pressable
          onPress={() => void proceed()}
          disabled={processing}
          style={{
            marginTop: r(1),
            borderRadius: r(0.75),
            minHeight: r(4),
            backgroundColor: '#268BFF',
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'center',
            gap: r(0.25),
          }}
        >
          <Text style={{ color: '#fff', fontSize: r(1.2), fontWeight: '700' }}>
            {processing ? 'Создание платежа...' : 'Перейти в Ю-касса'}
          </Text>
        </Pressable>

        {suggested ? (
          <Text style={{ color: '#464F5D', fontSize: r(0.9), marginTop: r(0.5), textAlign: 'center' }}>
            Рекомендуем пополнить минимум на {Math.ceil(suggested)} ₽
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
});
