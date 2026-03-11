import React from 'react';
import { Pressable, StyleSheet, Text, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { gradients } from '../constants/theme';

type GradientButtonProps = {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  style?: ViewStyle;
};

export function GradientButton({ title, onPress, disabled, style }: GradientButtonProps) {
  return (
    <Pressable disabled={disabled} onPress={onPress} style={[styles.wrapper, style, disabled && styles.disabled]}>
      <LinearGradient colors={disabled ? ['#2b313c', '#20252f'] : gradients.success} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.gradient}>
        <Text style={styles.title}>{title}</Text>
      </LinearGradient>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    borderRadius: 18,
    overflow: 'hidden',
  },
  gradient: {
    minHeight: 54,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    paddingHorizontal: 16,
  },
  title: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  disabled: {
    opacity: 0.8,
  },
});
