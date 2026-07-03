/**
 * Login Screen — Role-aware premium dark UI with glassmorphism.
 * Accepts `role` query param from gateway to show role-specific branding.
 * Validates returned user_type matches selected role (mismatch guard).
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { signIn, logout as doLogout } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, toggleLanguage, i18n } from '../../services/i18n';

export default function LoginScreen() {
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
    opacity: 0.06,
  },
  glowOrb2: {
    position: 'absolute',
    bottom: '10%',
    right: '-15%',
    width: 250,
    height: 250,
    borderRadius: 125,
    opacity: 0.05,
  },
  langButton: {
    position: 'absolute',
    top: 60,
    right: Spacing.xl,
    zIndex: 10,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.full,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  langText: {
    fontSize: 14,
    color: Colors.textPrimary,
    fontWeight: '600',
  },
  backButton: {
    position: 'absolute',
    top: 60,
    left: Spacing.xl,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  header: {
    alignItems: 'center',
    marginBottom: Spacing.xxl,
  },
  logoContainer: {
    width: 76,
    height: 76,
    borderRadius: 38,
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
    ...Typography.body,
    color: Colors.textSecondary,
  },
  card: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.medium,
  },
  cardTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginBottom: Spacing.xl,
    textAlign: 'center',
  },
  errorBanner: {
    backgroundColor: Colors.errorBg,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.errorBorder,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
  },
  errorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  errorText: {
    ...Typography.bodySmall,
    color: Colors.error,
    flex: 1,
  },
  verifyActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    borderRadius: BorderRadius.sm,
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.sm,
    marginTop: Spacing.sm,
    alignSelf: 'flex-start',
  },
  verifyActionBtnText: {
    ...Typography.caption,
    color: Colors.textOnPrimary,
    fontWeight: '700',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.lg,
    marginBottom: Spacing.md,
    height: 52,
  },
  inputIcon: {
    marginRight: Spacing.sm,
  },
  input: {
    flex: 1,
    color: Colors.textPrimary,
    ...Typography.body,
  },
  forgotPassword: {
    alignSelf: 'flex-end',
    marginTop: Spacing.xs,
    marginBottom: Spacing.xs,
  },
  forgotPasswordText: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.primary,
  },
  button: {
    borderRadius: BorderRadius.md,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.md,
    ...Shadows.small,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    ...Typography.button,
    color: Colors.textOnPrimary,
  },
  linkContainer: {
    marginTop: Spacing.lg,
    alignItems: 'center',
  },
  linkText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  linkHighlight: {
    fontWeight: '600',
  },
  }), [Colors]);
  const router = useRouter();
  const searchParams = useLocalSearchParams();

  // Role from gateway ("customer" or "merchant")
  const role = (searchParams.role as string) || 'customer';
  const isMerchant = role === 'merchant';

  // Get prefilled username if redirected from verify screen
  const prefill = searchParams.prefill as string;

  const [emailOrPhone, setEmailOrPhone] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Custom interactive error states
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [unverifiedDetails, setUnverifiedDetails] = useState<{
    userId: string;
    contact: string;
    channel: string;
    userType: string;
  } | null>(null);

  // Apply prefill if present
  useEffect(() => {
    if (prefill) {
      setEmailOrPhone(prefill);
      setErrorMessage(null);
    }
  }, [prefill]);

  // Role-specific styling
  const accentColor = isMerchant ? Colors.secondary : Colors.primary;
  const accentDark = isMerchant ? '#00B88D' : Colors.primaryDark;
  const roleIcon = isMerchant ? 'storefront-outline' : 'cart-outline';
  const roleLabel = isMerchant ? t('login.seller_sign_in') : t('login.shopper_sign_in');
  const roleSubtitle = isMerchant ? t('login.seller_subtitle') : t('login.shopper_subtitle');

  // Determine input icon dynamically
  const getUsernameIcon = (): any => {
    const val = emailOrPhone.trim();
    if (!val) return 'mail-outline';
    if (val.includes('@')) return 'mail-outline';
    if (/^\+?\d+$/.test(val.replace(/[\s\-()]/g, ''))) return 'phone-portrait-outline';
    return 'person-outline';
  };

  const handleLogin = async () => {
    setErrorMessage(null);
    setUnverifiedDetails(null);

    if (!emailOrPhone.trim() || !password.trim()) {
      setErrorMessage(t('login.fill_fields'));
      return;
    }

    setLoading(true);
    try {
      const response = await signIn(emailOrPhone.trim(), password);

      // ── Role Mismatch Guard ──
      const returnedRole = response.user.user_type;
      if (returnedRole !== role) {
        setErrorMessage(
          returnedRole === 'merchant' ? t('login.role_mismatch_merchant') : t('login.role_mismatch_customer')
        );
        // Clear the stored token since we don't want them logged in on wrong side
        await doLogout();
        return;
      }

      // Route to correct app section
      if (returnedRole === 'merchant') {
        router.replace('/(merchant)/dashboard');
      } else {
        router.replace('/(customer)/search');
      }
    } catch (err: any) {
      const status = err?.response?.status;
      const data = err?.response?.data;

      if (status === 403 && data?.user_id) {
        // Account unverified — show banner with instant activation action
        setErrorMessage(t('login.unverified_account'));
        setUnverifiedDetails({
          userId: data.user_id,
          contact: data.contact,
          channel: data.channel,
          userType: data.user_type,
        });
      } else {
        setErrorMessage(data?.detail || 'Invalid email/phone or password. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyNow = () => {
    if (!unverifiedDetails) return;
    router.push({
      pathname: '/(auth)/verify',
      params: {
        userId: unverifiedDetails.userId,
        contact: unverifiedDetails.contact,
        channel: unverifiedDetails.channel,
        userType: unverifiedDetails.userType,
      },
    });
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Ambient Glow Orbs — role-tinted */}
      <View style={[styles.glowOrb1, { backgroundColor: accentColor }]} />
      <View style={[styles.glowOrb2, { backgroundColor: isMerchant ? Colors.accent : Colors.secondary }]} />

      {/* Language Toggle — text-only pill */}
      <TouchableOpacity style={styles.langButton} onPress={toggleLanguage} activeOpacity={0.7}>
        <Text style={styles.langText}>{i18n.locale.includes('ar') ? 'EN' : 'ع'}</Text>
      </TouchableOpacity>

      {/* Back Button */}
      <TouchableOpacity
        style={styles.backButton}
        onPress={() => router.back()}
        activeOpacity={0.7}
      >
        <Ionicons name="arrow-back" size={22} color={Colors.textSecondary} />
      </TouchableOpacity>

      {/* Logo & Header — role-branded */}
      <View style={styles.header}>
        <LinearGradient
          colors={isMerchant ? [Colors.secondary, '#33E4BC'] : [Colors.primary, '#8B83FF']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.logoContainer}
        >
          <Ionicons name={roleIcon as any} size={36} color={Colors.textOnPrimary} />
        </LinearGradient>
        <Text style={styles.title}>{roleLabel}</Text>
        <Text style={styles.subtitle}>{roleSubtitle}</Text>
      </View>

      {/* Login Card */}
      <View style={[styles.card, { borderColor: `${accentColor}22` }]}>
        <Text style={styles.cardTitle}>{t('login.welcome_back')}</Text>

        {/* Dynamic Error Banner */}
        {errorMessage && (
          <View style={styles.errorBanner}>
            <View style={styles.errorHeader}>
              <Ionicons name="alert-circle" size={20} color={Colors.error} />
              <Text style={styles.errorText}>{errorMessage}</Text>
              <TouchableOpacity onPress={() => setErrorMessage(null)} activeOpacity={0.6}>
                <Ionicons name="close" size={18} color={Colors.textMuted} />
              </TouchableOpacity>
            </View>

            {unverifiedDetails && (
              <TouchableOpacity
                style={[styles.verifyActionBtn, { backgroundColor: accentColor }]}
                onPress={handleVerifyNow}
                activeOpacity={0.8}
              >
                <Text style={styles.verifyActionBtnText}>{t('login.verify_now')}</Text>
                <Ionicons name="arrow-forward" size={14} color={Colors.textOnPrimary} />
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Email or Phone Input */}
        <View style={styles.inputContainer}>
          <Ionicons
            name={getUsernameIcon()}
            size={20}
            color={Colors.textMuted}
            style={styles.inputIcon}
          />
          <TextInput
            style={styles.input}
            placeholder={t('login.email_placeholder')}
            placeholderTextColor={Colors.textMuted}
            value={emailOrPhone}
            onChangeText={(val) => {
              setEmailOrPhone(val);
              if (errorMessage) setErrorMessage(null);
            }}
            keyboardType="email-address"
            autoCapitalize="none"
            autoComplete="username"
          />
        </View>

        {/* Password */}
        <View style={styles.inputContainer}>
          <Ionicons name="lock-closed-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
          <TextInput
            style={styles.input}
            placeholder={t('login.password_placeholder')}
            placeholderTextColor={Colors.textMuted}
            value={password}
            onChangeText={(val) => {
              setPassword(val);
              if (errorMessage) setErrorMessage(null);
            }}
            secureTextEntry={!showPassword}
            autoCapitalize="none"
          />
          <TouchableOpacity onPress={() => setShowPassword(!showPassword)} activeOpacity={0.6}>
            <Ionicons name={showPassword ? 'eye-off' : 'eye'} size={20} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Forgot Password Link */}
        <TouchableOpacity style={styles.forgotPassword} activeOpacity={0.7}>
          <Text style={styles.forgotPasswordText}>{t('login.forgot_password')}</Text>
        </TouchableOpacity>

        {/* Login Button */}
        <TouchableOpacity
          style={[styles.button, { backgroundColor: accentColor }, loading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator color={Colors.textOnPrimary} />
          ) : (
            <Text style={styles.buttonText}>{t('login.sign_in')}</Text>
          )}
        </TouchableOpacity>

        {/* Register Link */}
        <TouchableOpacity
          style={styles.linkContainer}
          onPress={() => router.push({ pathname: '/(auth)/register', params: { role } })}
        >
          <Text style={styles.linkText}>
            {t('login.no_account')}{' '}
            <Text style={[styles.linkHighlight, { color: accentColor }]}>{t('login.sign_up')}</Text>
          </Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );

}
