/**
 * KeyboardForm: a scroll container that keeps the focused text field above the keyboard.
 *
 * Android 16 apps are always edge-to-edge, where the old automatic window resize no longer
 * happens when the keyboard opens. react-native-keyboard-controller tracks the real keyboard
 * position instead (requires <KeyboardProvider> in app/_layout.tsx). Use this for any screen
 * with text fields, so every form behaves the same way.
 */

import React from 'react';
import { StyleProp, ViewStyle } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';

type Props = {
  children: React.ReactNode;
  contentContainerStyle?: StyleProp<ViewStyle>;
  /** Space kept between the focused field and the top of the keyboard. */
  bottomOffset?: number;
};

export default function KeyboardForm({ children, contentContainerStyle, bottomOffset = 32 }: Props) {
  return (
    <KeyboardAwareScrollView
      bottomOffset={bottomOffset}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
      contentContainerStyle={contentContainerStyle}
    >
      {children}
    </KeyboardAwareScrollView>
  );
}
