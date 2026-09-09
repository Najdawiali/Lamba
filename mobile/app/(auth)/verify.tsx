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
import { verifyCode, resendCode } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';

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
    backgroundColor: 'rgba(255, 179, 0, 0.08)',
  },
  glowOrb2: {
    position: 'absolute',
    bottom: '15%',
    right: '-15%',
    width: 250,
    height: 250,
    borderRadius: 125,
    backgroundColor: 'rgba(255, 143, 0, 0.06)',
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
    color: '#FF8F00',
    marginTop: Spacing.xs,
  },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
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
    borderColor: 'rgba(255, 143, 0, 0.4)',
  },
  boxFocused: {
    borderColor: '#FF8F00',
    backgroundColor: Colors.surfaceElevated,
  },
  boxText: {
    ...Typography.h2,
    color: Colors.textPrimary,
  },
  cursor: {
    position: 'absolute',
    width: 2,
    height: 20,
    backgroundColor: '#FF8F00',
  },
  hiddenInput: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
  },
  button: {
    backgroundColor: '#FF8F00',
    borderRadius: BorderRadius.xl,
    height: 54,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.lg,
    ...Shadows.glow,
  },
  verifyButton: {
    backgroundColor: '#FF8F00',
    borderRadius: BorderRadius.xl,
    height: 54,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.lg,
    ...Shadows.glow,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    ...Typography.button,
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
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
    color: '#FF8F00',
    fontWeight: '700',
  },
  resendText: {
    ...Typography.bodySmall,
    color: '#FF8F00',
    fontWeight: '700',
  },
  }), [Colors]);
  const router = useRouter();
  const { user_id: queryUserId, userId: legacyUserId, channel: queryChannel, contact: queryContact, user_type: queryUserType, userType: legacyUserType } = useLocalSearchParams<{
    user_id?: string;
    userId?: string;
    channel?: string;
    contact?: string;
    user_type?: string;
    userType?: string;
  }>();

  // Route params passed from registration or login
  const userId = (queryUserId || legacyUserId) as string;
  const contact = (queryContact as string) || '';
  const channel = (queryChannel as string) || 'email';
  const userType = (queryUserType || legacyUserType as string) || 'customer';

  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [verified, setVerified] = useState(false);
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
    if (loading || verified) return; // prevent double-tap

    const fullCode = Array.isArray(code) ? code.join('') : code;
    if (fullCode.length !== 6) {
      Alert.alert(t('common.error', 'Error'), t('auth.enter_code', 'Please enter the 6-digit code'));
      return;
    }

    setLoading(true);
    try {
      const response = await verifyCode({
        user_id: userId,
        verification_code: fullCode,
      });

      if (response.verified) {
        // Inside the success block, BEFORE showing the alert:
        setVerified(true);
        setLoading(false);
        Alert.alert(
          t('common.success', 'Success'),
          t('auth.account_verified', 'Account verified successfully!'),
          [
            {
              text: t('common.ok', 'OK'),
              onPress: () => {
                if (contact) {
                  router.replace({
                    pathname: '/(auth)/login',
                    params: { prefill: contact }
                  });
                } else {
                  router.replace('/(auth)/login');
                }
              }
            }
          ]
        );
        return; // don't fall through to finally
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
  }, [code, loading, verified, userId, contact, router]);

  // Trigger verify automatically when all 6 digits are typed
  useEffect(() => {
    if (code.length === CODE_LENGTH && !loading && !verified) {
      handleVerify();
    }
  }, [code, handleVerify, loading, verified]);

  const handleResendCode = async () => {
    if (resendTimer > 0) return;
    setResendTimer(60);
    try {
      await resendCode(userId);
      Alert.alert(
        t('auth.code_sent', 'Code Sent'),
        t('auth.code_resent_msg', 'A new verification code has been sent.'),
      );
    } catch (err: any) {
      Alert.alert(
        t('common.error', 'Error'),
        err?.response?.data?.detail || t('auth.resend_failed', 'Failed to resend code. Please try again.'),
      );
    }
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
        <Ionicons name={i18n.locale?.startsWith('ar') ? "arrow-forward" : "arrow-back"} size={24} color={Colors.textSecondary} />
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
          style={[styles.verifyButton, (loading || verified) && { opacity: 0.5 }]}
          onPress={handleVerify}
          disabled={loading || verified}
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
            <TouchableOpacity
              onPress={handleResendCode}
              disabled={resendTimer > 0 || loading || verified}
              activeOpacity={0.7}
            >
              <Text style={[styles.resendText, (loading || verified) && { opacity: 0.5 }]}>
                {t('verify.resend')}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </KeyboardAvoidingView>
  );

}
