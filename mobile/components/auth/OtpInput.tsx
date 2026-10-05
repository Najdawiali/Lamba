/**
 * One-time code entry, drawn as boxes.
 *
 * A single real TextInput is laid over the boxes (nearly transparent), so a tap anywhere on
 * the boxes lands on the input itself and Android always opens the keyboard. The previous
 * design used a 1x1 hidden input focused from code, which Android often won't focus, and
 * focus() does nothing on an input that is already focused (e.g. after the keyboard was
 * dismissed), so the keyboard could never come back.
 *
 * Supports paste and system code autofill. Digits always read left to right, also in Arabic.
 */

import React, { useState } from 'react';
import { View, Text, TextInput, StyleSheet, Platform } from 'react-native';
import { useThemeColors } from '../../context/ThemeContext';
import { BorderRadius, Typography } from '../../constants/theme';

type Props = {
  value: string;
  onChange: (code: string) => void;
  length?: number;
  autoFocus?: boolean;
  editable?: boolean;
};

export default function OtpInput({ value, onChange, length = 6, autoFocus = false, editable = true }: Props) {
  const Colors = useThemeColors();
  const [focused, setFocused] = useState(false);

  const handleChange = (text: string) => {
    // Paste and autofill can deliver spaces, dashes or the whole message text: keep the digits
    onChange(text.replace(/\D/g, '').slice(0, length));
  };

  return (
    <View style={styles.row}>
      {Array.from({ length }).map((_, i) => {
        const char = value[i] ?? '';
        const active = focused && i === Math.min(value.length, length - 1);
        return (
          <View
            key={i}
            style={[
              styles.box,
              { borderColor: Colors.border, backgroundColor: Colors.surface },
              char ? styles.boxFilled : null,
              active ? { borderColor: '#FF8F00', backgroundColor: Colors.surfaceElevated } : null,
            ]}
          >
            <Text style={[styles.digit, { color: Colors.textPrimary }]}>{char}</Text>
            {active && !char ? <View style={styles.cursor} /> : null}
          </View>
        );
      })}

      <TextInput
        style={styles.input}
        value={value}
        onChangeText={handleChange}
        maxLength={length}
        keyboardType="number-pad"
        textContentType="oneTimeCode"
        autoComplete={Platform.OS === 'android' ? 'sms-otp' : 'one-time-code'}
        importantForAutofill="yes"
        autoFocus={autoFocus}
        editable={editable}
        caretHidden
        selectionColor="transparent"
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        accessibilityLabel="Verification code"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    direction: 'ltr',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
    width: '100%',
  },
  box: {
    flex: 1,
    maxWidth: 52,
    height: 56,
    borderWidth: 1.5,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  boxFilled: { borderColor: 'rgba(255, 143, 0, 0.5)' },
  digit: { ...Typography.h2 },
  cursor: { position: 'absolute', width: 2, height: 22, backgroundColor: '#FF8F00' },
  // Covers all boxes so taps reach the real input. Opacity just above 0: some Android
  // versions skip fully transparent views when delivering touches.
  input: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.02,
    color: 'transparent',
    fontSize: 1,
  },
});
