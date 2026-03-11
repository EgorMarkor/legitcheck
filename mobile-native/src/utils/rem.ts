import { useCallback, useMemo } from 'react';
import { useWindowDimensions } from 'react-native';

const WEB_REM_VIEWPORT_RATIO = 0.033;

export function useWebRem() {
  const { width } = useWindowDimensions();

  const rem = useMemo(() => width * WEB_REM_VIEWPORT_RATIO, [width]);

  const r = useCallback(
    (value: number) => value * rem,
    [rem]
  );

  return {
    width,
    rem,
    r,
  };
}
