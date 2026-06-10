import React from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { AuthUser } from '../api/types';
import { staticUrl } from '../constants/config';
import { colors } from '../constants/theme';
import { resolveImageUrl } from '../utils/verdict';
import { useWebRem } from '../utils/rem';
import { RemoteAsset } from './RemoteAsset';

type AppHeaderProps = {
  user: AuthUser;
  onBalancePress?: () => void;
  onAvatarPress?: () => void;
};

export function AppHeader({ user, onAvatarPress, onBalancePress }: AppHeaderProps) {
  const { r } = useWebRem();
  const avatarUrl = resolveImageUrl(user.img) ?? staticUrl('avatar-placeholder.png');

  return (
    <View style={[styles.wrapper, { marginTop: r(1), paddingHorizontal: r(1), paddingVertical: r(0.5) }]}> 
      <Pressable
        onPress={() => {
          void Linking.openURL('https://t.me/legitcheck');
        }}
        style={({ pressed }) => [
          styles.channel,
          {
            paddingHorizontal: r(0.75),
            paddingVertical: r(0.75),
            borderRadius: r(99),
            gap: r(0.75),
          },
          pressed && styles.pressed,
        ]}
      >
        <RemoteAsset uri={staticUrl('telegram.svg')} width={r(2.5)} height={r(2.5)} />
        <View>
          <Text style={[styles.channelName, { fontSize: r(1), lineHeight: r(1.05) }]}>@legitcheck</Text>
          <Text style={[styles.channelSub, { fontSize: r(0.8), marginTop: r(0.2), lineHeight: r(0.82) }]}>Наш Telegram-канал</Text>
        </View>
      </Pressable>

      <View style={[styles.rightGroup, { marginLeft: r(0.7), gap: r(0.7) }]}> 
        <Pressable
          onPress={onBalancePress}
          style={({ pressed }) => [
            styles.balance,
            {
              paddingHorizontal: r(0.75),
              paddingVertical: r(0.75),
              borderRadius: r(99),
              gap: r(0.5),
            },
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.balanceText, { fontSize: r(1.2), lineHeight: r(1.22) }]}>{user.balance} ₽</Text>
          <RemoteAsset uri={staticUrl('balance.svg')} width={r(3.5)} height={r(2.5)} />
        </Pressable>

        <Pressable onPress={onAvatarPress} style={({ pressed }) => [pressed && styles.pressed]}>
          <RemoteAsset uri={avatarUrl} width={r(3)} height={r(3)} style={{ borderRadius: r(1.5), backgroundColor: '#1f2733' }} resizeMode="cover" />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  channel: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#11151a',
    borderWidth: 1,
    borderColor: colors.border,
    flexShrink: 1,
  },
  channelName: {
    color: '#fff',
    fontWeight: '700',
  },
  channelSub: {
    color: '#464F5D',
    fontWeight: '400',
  },
  rightGroup: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  balance: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#11151a',
    borderWidth: 1,
    borderColor: colors.border,
  },
  balanceText: {
    color: '#fff',
    fontWeight: '700',
  },
  pressed: {
    opacity: 0.9,
    transform: [{ scale: 0.98 }],
  },
});
