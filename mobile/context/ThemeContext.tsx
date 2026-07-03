/**
 * ThemeContext — System / Light / Dark theme provider.
 *
 * Persists user preference ("system" | "light" | "dark") to SecureStore.
 * When mode is "system", resolves scheme via useColorScheme() and follows
 * OS appearance live.
 *
 * Consumers use `useThemeColors()` to grab the resolved palette object
 * (shape identical to the legacy `Colors` export from constants/theme.ts),
 * enabling live theme switching when stylesheets are memoized on `colors`.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useCallback,
} from 'react';
import { useColorScheme } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import {
  ColorsType,
  ColorScheme,
  getColors,
} from '../constants/palettes';

export type ThemeMode = 'system' | 'light' | 'dark';

export const THEME_PREF_KEY = 'lamba_theme_pref';
export const DEFAULT_THEME_MODE: ThemeMode = 'system';

interface ThemeContextValue {
  mode: ThemeMode;
  scheme: ColorScheme;
  colors: ColorsType;
  isDark: boolean;
  setMode: (mode: ThemeMode) => void;
  ready: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme() as ColorScheme | null | undefined;
  const [mode, setModeState] = useState<ThemeMode>(DEFAULT_THEME_MODE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const stored = await SecureStore.getItemAsync(THEME_PREF_KEY);
        if (mounted && (stored === 'system' || stored === 'light' || stored === 'dark')) {
          setModeState(stored);
        }
      } catch {
        // ignore — fall back to default
      } finally {
        if (mounted) setReady(true);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    SecureStore.setItemAsync(THEME_PREF_KEY, next).catch(() => {});
  }, []);

  const scheme: ColorScheme = useMemo(() => {
    if (mode === 'system') {
      return systemScheme === 'light' ? 'light' : 'dark';
    }
    return mode;
  }, [mode, systemScheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      scheme,
      isDark: scheme === 'dark',
      colors: getColors(scheme),
      setMode,
      ready,
    }),
    [mode, scheme, setMode, ready],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return ctx;
}

/** Convenience hook — returns the resolved palette (same shape as `Colors`). */
export function useThemeColors(): ColorsType {
  return useTheme().colors;
}