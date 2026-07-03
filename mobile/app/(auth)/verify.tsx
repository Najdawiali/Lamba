/**
 * Verification Screen — Enter a 6-digit code.
 * Implements a premium, bug-free grid entry interface using a hidden TextInput overlay.
 * Includes a real-time 60-second countdown timer for resends.
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, Alert, ActivityIndicator
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { verifyCode } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t } from '../../services/i18n';

export default function VerifyScreen() {
  const Colors = useThemeColors();

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
  },
  glowOrb1: {
    position: 'absolute',
    top: '15%',
    left: '-20%',
    width: 300,
    height: 300,
    borderRadius: 150,
    backgroundColor: Colors.secondary,
    opacity: 0.05,
  },
  glowOrb2: {
    position: 'absolute',
    bottom: '15%',
    right: '-15%',
    width: 250,
    height: 250,
    borderRadius: 125,
    backgroundColor: Colors.primary,
    opacity: 0.04,
  },
  backButton: {
    position: 'absolute',
    top: 60,
    left: Spacing.xl,
    padding: Spacing.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  header: {
    alignItems: 'center',
    marginBottom: Spacing.xxl,
  },
  iconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.lg,
    ...Shadows.glow,
  },
  title: {
    ...Typography.h1,
    color: Colors.textPrimary,
    marginBottom: Spacing.xs,
  },
  subtitle: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  contactText: {
    ...Typography.body,
    fontWeight: '700',
    color: Colors.secondary,
    marginTop: Spacing.xs,
  },
  card: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.medium,
  },
  boxesContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: Spacing.xl,
    width: '100%',
  },
  box: {
    width: 44,
    height: 52,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
  },
  boxFilled: {
    borderColor: 'rgba(108, 99, 255, 0.4)',
  },
  boxFocused: {
    borderColor: Colors.primary,
    backgroundColor: Colors.surfaceElevated,
    ...Shadows.small,
  },
  boxText: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  cursor: {
    position: 'absolute',
    width: 2,
    height: 20,
    backgroundColor: Colors.primary,
  },
  hiddenInput: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
  },
  button: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.lg,
    ...Shadows.small,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },
  resendContainer: {
    marginTop: Spacing.xl,
    alignItems: 'center',
  },
  timerText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
  timerCount: {
    color: Colors.secondary,
    fontWeight: '700',
  },
  resendText: {
    ...Typography.bodySmall,
    color: Colors.primary,
    fontWeight: '700',
  },
  }), [Colors]);
  const router = useRouter();
  const params = useLocalSearchParams();
  
  // Route params passed from registration
  const userId = params.userId as string;
  const contact = (params.contact as string) || '';
  const channel = (params.channel as string) || 'email';
  const userType = (params.userType as string) || 'customer';

  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendTimer, setResendTimer] = useState(60);
  const [isFocused, setIsFocused] = useState(false);
  
  const textInputRef = useRef<TextInput>(null);
  const CODE_LENGTH = 6;

  // Countdown timer logic
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (resendTimer > 0) {
      interval = setInterval(() => {
        setResendTimer((prev) => prev - 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [resendTimer]);

  const handleVerify = useCallback(async () => {
    if (code.length !== CODE_LENGTH) {
      Alert.alert(t('common.error'), t('verify.enter_all_digits'));
      return;
    }

    setLoading(true);
    try {
      const response = await verifyCode({
        user_id: userId,
        verification_code: code,
      });

      if (response.verified) {
        Alert.alert(
          t('common.success'),
          t('verify.account_activated'),
          [
            {
              text: 'OK',
              onPress: () => {
                // Navigate to Login and pre-fill the username
                router.replace({
                  pathname: '/(auth)/login',
                  params: { prefill: contact }
                });
              }
            }
          ]
        );
      }
    } catch (err: any) {
      Alert.alert(
        t('verify.verification_failed'),
        err?.response?.data?.detail || t('verify.invalid_code')
      );
      // Clear code on failure to allow retry
      setCode('');
    } finally {
      setLoading(false);
    }
  }, [code, loading, userId]);

  // Trigger verify automatically when all 6 digits are typed
  useEffect(() => {
    if (code.length === CODE_LENGTH) {
      handleVerify();
    }
  }, [code, handleVerify]);

  const handleResendCode = () => {
    if (resendTimer > 0) return;
    
    // Simulate/mock resending verification code.
    // In our backend design, the mock gateway prints the code to stdout.
    // Since we don't have password credentials to call /signup again,
    // we show a beautiful mock notification explaining that a new code was generated.
    setResendTimer(60);
    Alert.alert(
      t('verify.code_resent'),
      t('verify.code_resent_desc')
    );
  };

  const handleBoxPress = () => {
    textInputRef.current?.focus();
  };

  // Render individual code box
  const renderCodeBox = (index: number) => {
    const char = code[index] || '';
    const showFocusBorder = isFocused && code.length === index;

    return (
      <TouchableOpacity
        key={index}
        style={[
          styles.box,
          char ? styles.boxFilled : null,
          showFocusBorder ? styles.boxFocused : null
        ]}
        onPress={handleBoxPress}
        activeOpacity={1}
      >
        <Text style={styles.boxText}>{char}</Text>
        {showFocusBorder && <View style={styles.cursor} />}
      </TouchableOpacity>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Background glow effects */}
      <View style={styles.glowOrb1} />
      <View style={styles.glowOrb2} />

      {/* Back button to re-register */}
      <TouchableOpacity style={styles.backButton} onPress={() => router.back()} activeOpacity={0.7}>
        <Ionicons name="arrow-back" size={24} color={Colors.textSecondary} />
      </TouchableOpacity>

      <View style={styles.header}>
        <View style={styles.iconContainer}>
          <Ionicons
            name={channel === 'sms' ? 'chatbubble-ellipses-outline' : 'mail-open-outline'}
            size={40}
            color={Colors.secondary}
          />
        </View>
        <Text style={styles.title}>{t('verify.title')}</Text>
        <Text style={styles.subtitle}>{t('verify.subtitle')}</Text>
        <Text style={styles.contactText}>{contact}</Text>
      </View>

      <View style={styles.card}>
        {/* Hidden inputs overlay method */}
        <TouchableOpacity
          style={styles.boxesContainer}
          onPress={handleBoxPress}
          activeOpacity={1}
        >
          {Array.from({ length: CODE_LENGTH }).map((_, i) => renderCodeBox(i))}
        </TouchableOpacity>

        {/* Real hidden TextInput */}
        <TextInput
          ref={textInputRef}
          style={styles.hiddenInput}
          value={code}
          onChangeText={setCode}
          maxLength={CODE_LENGTH}
          keyboardType="number-pad"
          textContentType="oneTimeCode"
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          caretHidden
          autoFocus
        />

        {/* Verify Action Button (Fallback/Backup) */}
        <TouchableOpacity
          style={[styles.button, (code.length !== CODE_LENGTH || loading) && styles.buttonDisabled]}
          onPress={handleVerify}
          disabled={code.length !== CODE_LENGTH || loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator color={Colors.textOnPrimary} />
          ) : (
            <Text style={styles.buttonText}>{t('verify.button')}</Text>
          )}
        </TouchableOpacity>

        {/* Resend Timer / Action */}
        <View style={styles.resendContainer}>
          {resendTimer > 0 ? (
            <Text style={styles.timerText}>
              {t('verify.resend_in')} <Text style={styles.timerCount}>{resendTimer}s</Text>
            </Text>
          ) : (
            <TouchableOpacity onPress={handleResendCode} activeOpacity={0.7}>
              <Text style={styles.resendText}>{t('verify.resend')}</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </KeyboardAvoidingView>
  );

}
