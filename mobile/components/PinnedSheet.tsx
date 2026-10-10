/**
 * PinnedSheet: a bottom sheet that is pinned to the bottom edge of a screen and slides in with an Animated
 * value (the scanner's two drawers). It solves, once, what each hand-made sheet got wrong on Android 16:
 *
 *  - Edge-to-edge: the app draws under the navigation bar, and the scanner hides the tab bar that normally
 *    keeps content clear of it. The sheet's bottom padding is the real bottom inset plus the usual space.
 *  - Keyboard: the old adjustResize no longer happens, and React Native's KeyboardAvoidingView does nothing on
 *    Android here, so the keyboard covered the whole sheet. KeyboardStickyView (react-native-keyboard-controller,
 *    which needs the KeyboardProvider in app/_layout.tsx) lifts the sheet with the keyboard.
 *  - Theme: the surface and border come from the theme, so the text colours of the content (also from the
 *    theme) are readable in the light and the dark theme. The sheet used to be a fixed dark colour.
 *
 * Use it for sheets laid over a screen. Sheets in a React Native <Modal> are a different case.
 */

import React from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { KeyboardStickyView } from 'react-native-keyboard-controller';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BorderRadius, Shadows, Spacing } from '../constants/theme';
import { useThemeColors } from '../context/ThemeContext';

type Props = {
  /** 0 = shown, a screen height = hidden below the screen. */
  translateY: Animated.Value;
  /** True once the sheet is open. While it is hidden it must not follow the keyboard (it would peek in). */
  open: boolean;
  /** Cap for tall content. */
  maxHeight?: number;
  children: React.ReactNode;
};

export default function PinnedSheet({ translateY, open, maxHeight, children }: Props) {
  const Colors = useThemeColors();
  const insets = useSafeAreaInsets();

  return (
    <Animated.View style={[styles.slot, { transform: [{ translateY }] }]}>
      {/*
        While the keyboard is up it already covers the navigation bar, so the inset part of the bottom padding
        is not needed: `opened: insets.bottom` lowers the sheet by exactly that much.
      */}
      <KeyboardStickyView enabled={open} offset={{ closed: 0, opened: insets.bottom }}>
        <View
          style={[
            styles.sheet,
            {
              backgroundColor: Colors.surface,
              borderColor: Colors.border,
              paddingBottom: insets.bottom + Spacing.xl,
              maxHeight,
            },
          ]}
        >
          {children}
        </View>
      </KeyboardStickyView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  slot: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 11,
  },
  sheet: {
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    borderWidth: 1,
    ...Shadows.large,
  },
});
