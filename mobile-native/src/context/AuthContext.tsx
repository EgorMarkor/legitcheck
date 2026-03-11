import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

import { AuthUser } from '../api/types';
import { fetchUser } from '../api/client';

const USER_STORAGE_KEY = 'legitcheck_native_user';

type AuthContextValue = {
  user: AuthUser | null;
  restoring: boolean;
  setUser: (user: AuthUser | null) => Promise<void>;
  refreshUser: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    const restore = async () => {
      try {
        const raw = await AsyncStorage.getItem(USER_STORAGE_KEY);
        if (!raw) {
          return;
        }

        const parsed = JSON.parse(raw) as AuthUser;
        setUserState(parsed);
      } finally {
        setRestoring(false);
      }
    };

    void restore();
  }, []);

  const setUser = async (nextUser: AuthUser | null) => {
    setUserState(nextUser);
    if (nextUser) {
      await AsyncStorage.setItem(USER_STORAGE_KEY, JSON.stringify(nextUser));
      return;
    }
    await AsyncStorage.removeItem(USER_STORAGE_KEY);
  };

  const refreshUser = async () => {
    if (!user) {
      return;
    }

    try {
      const updated = await fetchUser(user.tgId);
      await setUser(updated);
    } catch {
      // Keep stale local user data if network temporarily fails.
    }
  };

  const signOut = async () => {
    await setUser(null);
  };

  const value = useMemo<AuthContextValue>(() => ({
    user,
    restoring,
    setUser,
    refreshUser,
    signOut,
  }), [restoring, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
