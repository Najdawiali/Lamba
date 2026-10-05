/**
 * Login Screen — sign in with email (or phone, when PHONE_AUTH_ENABLED is on).
 * All users navigate to the customer home after sign in.
 * Merchants access their store dashboard via Profile -> "إدارة متجري".
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, Image, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';

import { Ionicons } from '@expo/vector-icons';
import { signIn } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors, useTheme } from '../../context/ThemeContext';
import { t, toggleLanguage, i18n } from '../../services/i18n';
import { PHONE_AUTH_ENABLED } from '../../constants/features';
import KeyboardForm from '../../components/KeyboardForm';
import { localizeServerMessage } from '../../utils/serverMessage';

export default function LoginScreen() {
  const Colors = useThemeColors();
  const { isDark, setMode } = useTheme();
  const router = useRouter();
  const { width: screenWidth } = Dimensions.get('window');
  const iconSize = screenWidth * 0.22; // smaller on login since there's a form below
  const searchParams = useLocalSearchParams();
  const isAr = i18n.locale?.startsWith('ar');

  // Get prefilled username if redirected from verify screen
  const prefill = searchParams.prefill as string;

  const [emailOrPhone, setEmailOrPhone] = useState('');
  const [password, setPassword] = useState('');
  const passwordRef = useRef<TextInput>(null);
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

  // Determine input icon dynamically
  const getUsernameIcon = (): any => {
    if (!PHONE_AUTH_ENABLED) return 'mail-outline';
    const val = emailOrPhone.trim();
    if (!val) return 'person-outline';
    if (val.includes('@')) return 'mail-outline';
    if (/^\+?\d+$/.test(val.replace(/[\s\-()]/g, ''))) return 'phone-portrait-outline';
    return 'person-outline';
  };

  const handleLogin = async () => {
    setErrorMessage(null);
    setUnverifiedDetails(null);

    if (!emailOrPhone.trim() || !password.trim()) {
      setErrorMessage(t('login.fill_fields', 'Please fill in all fields'));
      return;
    }

    setLoading(true);
    try {
      await signIn(emailOrPhone.trim(), password);

      // Always route to customer search home for all accounts
      router.replace('/(customer)/search');
    } catch (err: any) {
      if (err.response?.status === 403) {
        const detail = err.response.data?.detail;
        if (detail && detail.user_id) {
          router.push({
            pathname: '/(auth)/verify',
            params: {
              user_id: detail.user_id,
              channel: detail.channel,
              contact: detail.contact,
              user_type: detail.user_type,
              from_signin: 'true',
            },
          });
          return;
        }
      }

      // Show a translated message for the expected failures rather than the
      // server's raw English text (e.g. "Invalid Credentials").
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (!err?.response) {
        setErrorMessage(t('login.network_error', "Couldn't reach the server. Check your internet connection and try again."));
      } else if (status === 401) {
        setErrorMessage(
          PHONE_AUTH_ENABLED
            ? t('login.invalid_credentials', 'Invalid email/phone or password. Please try again.')
            : t('login.invalid_credentials_email', 'Incorrect email or password. Please try again.')
        );
      } else if (status === 429) {
        setErrorMessage(t('login.too_many_attempts', 'Too many attempts. Please wait a minute and try again.'));
      } else {
        setErrorMessage(localizeServerMessage(detail, !!isAr, t('common.error', 'Something went wrong. Please try again.')));
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

  const styles = useMemo(() => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    scrollContent: {
      flexGrow: 1,
      justifyContent: 'center',
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.xxl,
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
      bottom: '10%',
      right: '-15%',
      width: 250,
      height: 250,
      borderRadius: 125,
      backgroundColor: 'rgba(255, 143, 0, 0.06)',
    },
    header: {
      alignItems: 'center',
      marginBottom: Spacing.xl,
    },
    title: {
      ...Typography.h1,
      fontSize: 26,
      color: Colors.textPrimary,
      marginBottom: Spacing.xs,
      fontWeight: '800',
    },
    headerTitle: {
      ...Typography.h1,
      fontSize: 26,
      color: Colors.textPrimary,
      marginBottom: Spacing.xs,
      fontWeight: '800',
    },
    subtitle: {
      ...Typography.body,
      color: Colors.textSecondary,
    },
    card: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.xl,
      padding: Spacing.xl,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    cardTitle: {
      ...Typography.h3,
      color: Colors.textPrimary,
      marginBottom: Spacing.lg,
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
      backgroundColor: '#FF8F00',
      paddingVertical: Spacing.xs,
      paddingHorizontal: Spacing.sm,
      marginTop: Spacing.sm,
      alignSelf: 'flex-start',
    },
    verifyActionBtnText: {
      ...Typography.caption,
      color: '#FFFFFF',
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
      marginHorizontal: Spacing.xs,
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
      color: '#FF8F00',
    },
    button: {
      backgroundColor: '#FF8F00',
      borderRadius: BorderRadius.xl,
      height: 54,
      justifyContent: 'center',
      alignItems: 'center',
      marginTop: Spacing.md,
      ...Shadows.glow,
    },
    buttonDisabled: {
      opacity: 0.6,
    },
    buttonText: {
      ...Typography.button,
      color: '#FFFFFF',
      fontSize: 16,
      fontWeight: '800',
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
      color: '#FF8F00',
      fontWeight: '700',
    },
  }), [Colors]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background }} edges={['top']}>
      <View style={{ flex: 1 }}>
        <View style={styles.glowOrb1} />
        <View style={styles.glowOrb2} />

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

        <KeyboardForm contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
        <TouchableOpacity
          onPress={() => {
            setMode(isDark ? 'light' : 'dark');
          }}
          activeOpacity={0.8}
          style={{ alignItems: 'center', marginBottom: Spacing.md }}
        >
          <Image
            source={
              isDark
                ? require('../../assets/images/lamba-icon-off.png')
                : require('../../assets/images/lamba-icon.png')
            }
            style={{ width: iconSize, height: iconSize }}
            resizeMode="contain"
          />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1} adjustsFontSizeToFit>
          {t('auth.sign_in', 'Sign In')}
        </Text>
        <Text style={styles.subtitle}>{t('login.shopper_subtitle', 'Discover products near you')}</Text>
      </View>

      {/* Login Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{t('login.welcome_back', 'Enter your credentials')}</Text>

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
                style={styles.verifyActionBtn}
                onPress={handleVerifyNow}
                activeOpacity={0.8}
              >
                <Text style={styles.verifyActionBtnText}>{t('login.verify_now', 'Verify Now')}</Text>
                <Ionicons name="arrow-forward" size={14} color={Colors.textOnPrimary} />
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Email (or Phone) Input */}
        <View style={styles.inputContainer}>
          <Ionicons
            name={getUsernameIcon()}
            size={20}
            color={Colors.textMuted}
            style={styles.inputIcon}
          />
          <TextInput
            style={styles.input}
            placeholder={
              PHONE_AUTH_ENABLED
                ? t('auth.email_or_phone', 'Email or phone number')
                : t('auth.email', 'Email')
            }
            placeholderTextColor={Colors.textMuted}
            value={emailOrPhone}
            onChangeText={(val) => {
              setEmailOrPhone(val);
              if (errorMessage) setErrorMessage(null);
            }}
            keyboardType={PHONE_AUTH_ENABLED ? 'default' : 'email-address'}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="username"
            textContentType="username"
            returnKeyType="next"
            onSubmitEditing={() => passwordRef.current?.focus()}
            submitBehavior="submit"
          />
        </View>

        {/* Password */}
        <View style={styles.inputContainer}>
          <Ionicons name="lock-closed-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
          <TextInput
            ref={passwordRef}
            style={styles.input}
            placeholder={t('auth.password_placeholder', 'Password')}
            placeholderTextColor={Colors.textMuted}
            value={password}
            onChangeText={(val) => {
              setPassword(val);
              if (errorMessage) setErrorMessage(null);
            }}
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="current-password"
            textContentType="password"
            returnKeyType="done"
            onSubmitEditing={handleLogin}
          />
          <TouchableOpacity onPress={() => setShowPassword(!showPassword)} activeOpacity={0.6}>
            <Ionicons name={showPassword ? 'eye-off' : 'eye'} size={20} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Forgot Password Link */}
        <TouchableOpacity
          style={styles.forgotPassword}
          activeOpacity={0.7}
          onPress={() => router.push('/(auth)/forgot-password')}
        >
          <Text style={styles.forgotPasswordText}>{t('auth.forgot_password', 'Forgot Password?')}</Text>
        </TouchableOpacity>

        {/* Login Button */}
        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={loading}
          activeOpacity={0.85}
        >
          {loading ? (
            <ActivityIndicator color={Colors.textOnPrimary} />
          ) : (
            <Text style={styles.buttonText}>{t('auth.sign_in_button', 'Sign In')}</Text>
          )}
        </TouchableOpacity>

        {/* Register Link */}
        <TouchableOpacity
          style={styles.linkContainer}
          onPress={() => router.push('/(auth)/register')}
          activeOpacity={0.7}
        >
          <Text style={styles.linkText}>
            {t('auth.no_account', "Don't have an account?")}{' '}
            <Text style={styles.linkHighlight}>{t('auth.sign_up_title', 'Sign Up')}</Text>
          </Text>
        </TouchableOpacity>
      </View>
      </KeyboardForm>
    </View>
  </SafeAreaView>
  );
}
