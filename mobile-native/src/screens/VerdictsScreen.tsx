import React, { useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';

import { AppHeader } from '../components/AppHeader';
import { RemoteAsset } from '../components/RemoteAsset';
import { staticUrl } from '../constants/config';
import { colors, gradients } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { useWebRem } from '../utils/rem';

export function VerdictsScreen() {
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const [code, setCode] = useState('');
  const inputRef = useRef<TextInput | null>(null);
  const { r, width } = useWebRem();

  const codeChars = useMemo(() => {
    const values = code.split('').slice(0, 5);
    while (values.length < 5) {
      values.push('*');
    }
    return values;
  }, [code]);

  if (!user) {
    return null;
  }

  const onCheck = () => {
    if (code.length !== 5) {
      return;
    }

    navigation.getParent()?.navigate('VerdictDetail', { code });
  };

  const enabled = code.length === 5;

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ paddingBottom: r(2) }}>
      <AppHeader
        user={user}
        onBalancePress={() => navigation.getParent()?.navigate('Payment')}
        onAvatarPress={() => navigation.getParent()?.navigate('Account')}
      />

      <View style={{ marginTop: r(1.5), paddingHorizontal: r(1) }}>
        <RemoteAsset
          uri={staticUrl('phone.png')}
          width={width - r(2)}
          height={r(18)}
          resizeMode="contain"
          style={{ borderRadius: r(1.2) }}
        />
      </View>

      <View style={{ paddingHorizontal: r(1.5) }}>
        <Text style={{ color: '#fff', fontSize: r(1.6), fontWeight: '700' }}>Вердикты</Text>
        <Text style={{ color: '#464F5D', fontSize: r(1.2), marginTop: r(0.4), lineHeight: r(1.35) }}>
          Введите код вердикта, чтобы проверить оригинальность изделия
        </Text>

        <Pressable
          onPress={() => inputRef.current?.focus()}
          style={{ flexDirection: 'row', justifyContent: 'center', gap: r(0.5), marginTop: r(2) }}
        >
          {codeChars.map((char, idx) => (
            <View
              key={`${char}-${idx}`}
              style={{
                width: r(5),
                height: r(3.6),
                borderRadius: r(0.5),
                backgroundColor: '#11151A',
                alignItems: 'center',
                justifyContent: 'center',
                borderWidth: 1,
                borderColor: 'rgba(179,214,255,0.08)',
              }}
            >
              <Text style={{ color: '#fff', fontSize: r(1.5), fontWeight: '700' }}>{char}</Text>
            </View>
          ))}
        </Pressable>

        <TextInput
          ref={inputRef}
          keyboardType="numeric"
          maxLength={5}
          style={styles.hiddenInput}
          value={code}
          onChangeText={(value) => setCode(value.replace(/\D/g, ''))}
          autoFocus
        />

        <Pressable
          onPress={onCheck}
          disabled={!enabled}
          style={{ marginTop: r(1) }}
        >
          <LinearGradient
            colors={enabled ? gradients.success : gradients.card}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={{
              borderRadius: r(1.2),
              paddingVertical: r(1),
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ color: enabled ? '#fff' : '#464F5D', fontSize: r(1.2), fontWeight: '600' }}>
              Проверить
            </Text>
          </LinearGradient>
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
  hiddenInput: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
  },
});
