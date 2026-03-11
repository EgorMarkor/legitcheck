import React from 'react';
import { Image, ImageResizeMode, ImageStyle, StyleProp, View, ViewStyle } from 'react-native';
import { SvgUri } from 'react-native-svg';

type RemoteAssetProps = {
  uri: string;
  width: number;
  height: number;
  resizeMode?: ImageResizeMode;
  style?: StyleProp<ImageStyle>;
  containerStyle?: StyleProp<ViewStyle>;
};

export function RemoteAsset({
  uri,
  width,
  height,
  resizeMode = 'contain',
  style,
  containerStyle,
}: RemoteAssetProps) {
  const isSvg = uri.toLowerCase().endsWith('.svg');

  if (isSvg) {
    return (
      <View style={[{ width, height }, containerStyle]}>
        <SvgUri width="100%" height="100%" uri={uri} />
      </View>
    );
  }

  return (
    <Image
      source={{ uri }}
      style={[{ width, height }, style]}
      resizeMode={resizeMode}
    />
  );
}
