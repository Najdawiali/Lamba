/**
 * Verification Screen — enter the 6-digit code.
 * Uses the shared OtpInput (one real input over the boxes, with paste and autofill)
 * and a keyboard-aware container. 60-second countdown before a resend.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { verifyCode, resendCode } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import KeyboardForm from '../../components/KeyboardForm';
import OtpInput from '../../components/auth/OtpInput';
import { messageFromError } from '../../utils/serverMessage';

export default function VerifyScreen() {
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');

  const styles = useMemo(() => StyleSheet.create({
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
    paddingBottom: Spacing.xl,
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
  codeWrapper: {
    marginBottom: Spacing.xl,
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
        messageFromError(err, !!isAr, {
          network: t('login.network_error', "Couldn't reach the server. Check your internet connection and try again."),
          fallback: t('verify.invalid_code'),
        }),
      );
      // Clear code on failure to allow retry
      setCode('');
    } finally {
      setLoading(false);
    }
  }, [code, loading, verified, userId, contact, router, isAr]);

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
        messageFromError(err, !!isAr, {
          network: t('login.network_error', "Couldn't reach the server. Check your internet connection and try again."),
          fallback: t('auth.resend_failed', 'Failed to resend code. Please try again.'),
        }),
      );
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background }} edges={['top']}>
      {/* RTL-Safe Header */}
      <View style={{
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: Spacing.lg,
        paddingVertical: Spacing.md,
      }}>
        <TouchableOpacity onPress={() => router.back()} style={{ width: 40, height: 40, justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={22} color={Colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ width: 40 }} />
      </View>

      <View style={{ flex: 1 }}>
        {/* Background glow effects */}
        <View style={styles.glowOrb1} />
        <View style={styles.glowOrb2} />

      <KeyboardForm contentContainerStyle={styles.container}>

      <View style={styles.header}>
        <View style={styles.iconContainer}>
          <Ionicons
            name={channel === 'email' ? 'mail-open-outline' : 'chatbubble-ellipses-outline'}
            size={40}
            color={Colors.secondary}
          />
        </View>
        <Text style={styles.title}>{t('verify.title')}</Text>
        <Text style={styles.subtitle}>{t('verify.subtitle')}</Text>
        <Text style={styles.contactText}>{contact}</Text>
      </View>

      <View style={styles.card}>
        <View style={styles.codeWrapper}>
          <OtpInput
            value={code}
            onChange={setCode}
            length={CODE_LENGTH}
            autoFocus
            editable={!loading && !verified}
          />
        </View>

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
      </KeyboardForm>
      </View>
  </SafeAreaView>
  );

}
