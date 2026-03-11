import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BottomTabBarProps, createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';

import { useAuth } from '../context/AuthContext';
import { colors, gradients } from '../constants/theme';
import { staticUrl } from '../constants/config';
import { RootStackParamList, MainTabParamList } from '../types/navigation';
import { AuthScreen } from '../screens/AuthScreen';
import { HomeScreen } from '../screens/HomeScreen';
import { CheckScreen } from '../screens/CheckScreen';
import { VerdictsScreen } from '../screens/VerdictsScreen';
import { AccountScreen } from '../screens/AccountScreen';
import { VerdictDetailScreen } from '../screens/VerdictDetailScreen';
import { PaymentScreen } from '../screens/PaymentScreen';
import { useWebRem } from '../utils/rem';
import { RemoteAsset } from '../components/RemoteAsset';

const RootStack = createNativeStackNavigator<RootStackParamList>();
const MainTab = createBottomTabNavigator<MainTabParamList>();

function CustomTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  const { r } = useWebRem();

  return (
    <View style={[styles.tabWrapper, { bottom: r(1) + insets.bottom, paddingHorizontal: r(1) }]}>
      <LinearGradient
        colors={['rgba(29,36,48,0.85)', 'rgba(14,17,21,0.85)']}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={[
          styles.tabContainer,
          {
            borderRadius: r(99),
            paddingHorizontal: r(1),
            paddingVertical: r(0.55),
          },
        ]}
      >
        {state.routes.map((route, index) => {
          const isFocused = state.index === index;
          const isCenter = route.name === 'Check';

          if (isCenter) {
            return (
              <Pressable key={route.key} onPress={() => navigation.navigate(route.name)} style={styles.centerTouch}>
                <LinearGradient
                  colors={gradients.success}
                  style={{
                    minWidth: r(3.6),
                    minHeight: r(3.6),
                    borderRadius: r(1.8),
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingHorizontal: r(1.25),
                    paddingVertical: r(1),
                    borderWidth: r(0.12),
                    borderColor: 'rgba(255,255,255,0.22)',
                  }}
                >
                  <Text style={{ color: '#fff', fontSize: r(1.15), fontWeight: '800' }}>GO</Text>
                </LinearGradient>
              </Pressable>
            );
          }

          const iconUri = route.name === 'Home'
            ? staticUrl(isFocused ? 'home_active.svg' : 'home.svg')
            : staticUrl(isFocused ? 'verdicts_active.svg' : 'verdicts.svg');

          const label = route.name === 'Home' ? 'Главная' : 'Вердикты';

          return (
            <Pressable
              key={route.key}
              onPress={() => navigation.navigate(route.name)}
              style={[styles.tabButton, { minWidth: r(5.6), paddingVertical: r(0.15) }]}
            >
              <RemoteAsset uri={iconUri} width={r(1.5)} height={r(1.5)} />
              <Text style={{ color: isFocused ? '#fff' : '#9aa3b2', fontSize: r(0.9), marginTop: r(0.2) }}>{label}</Text>
            </Pressable>
          );
        })}
      </LinearGradient>
    </View>
  );
}

function MainTabs() {
  return (
    <MainTab.Navigator
      tabBar={(props) => <CustomTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <MainTab.Screen name="Home" component={HomeScreen} />
      <MainTab.Screen name="Check" component={CheckScreen} />
      <MainTab.Screen name="Verdicts" component={VerdictsScreen} />
    </MainTab.Navigator>
  );
}

export function RootNavigator() {
  const { user, restoring } = useAuth();

  if (restoring) {
    return (
      <View style={styles.loadingRoot}>
        <ActivityIndicator size="large" color={colors.success} />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <RootStack.Navigator screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
        {!user ? (
          <RootStack.Screen name="Auth" component={AuthScreen} />
        ) : (
          <>
            <RootStack.Screen name="MainTabs" component={MainTabs} />
            <RootStack.Screen name="Account" component={AccountScreen} />
            <RootStack.Screen name="VerdictDetail" component={VerdictDetailScreen} />
            <RootStack.Screen name="Payment" component={PaymentScreen} />
          </>
        )}
      </RootStack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingRoot: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabWrapper: {
    position: 'absolute',
    left: 0,
    right: 0,
  },
  tabContainer: {
    borderWidth: 1,
    borderColor: colors.border,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  tabButton: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  centerTouch: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
