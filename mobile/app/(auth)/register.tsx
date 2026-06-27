/**
 * Registration Screen — Unified with Role-Picker Step.
 * Step 1: Choose role (Shopper or Seller) — shown if no role query param
 * Step 2: Email/Phone signup form
 * Supports signup via Email or Phone Number.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, Alert, ActivityIndicator, ScrollView
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { signUp } from '../../services/api';
import { Colors, Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { t, i18n } from '../../services/i18n';

export default function RegisterScreen() {
  const router = useRouter();
  const searchParams = useLocalSearchParams();

  // Role can come from gateway query param, or be selected on step 1
  const presetRole = searchParams.role as 'customer' | 'merchant' | undefined;
  const [selectedRole, setSelectedRole] = useState<'customer' | 'merchant' | null>(presetRole || null);
  const isMerchant = selectedRole === 'merchant';

  const [activeTab, setActiveTab] = useState<'email' | 'phone'>('email');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Role-specific styling
  const accentColor = isMerchant ? Colors.secondary : Colors.primary;
  const roleIcon = isMerchant ? 'storefront-outline' : 'cart-outline';
  const roleTitle = selectedRole
    ? (isMerchant ? t('register.seller_title') : t('register.shopper_title'))
    : t('register.create_account');
  const roleSubtitle = selectedRole
    ? (isMerchant ? t('register.seller_subtitle') : t('register.shopper_subtitle'))
    : t('register.join_us');

  // Validation helpers
  const validateEmail = (val: string) => {
    const reg = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    return reg.test(val.trim());
  };

  const validatePhone = (val: string) => {
    const clean = val.replace(/\D/g, '');
    return clean.length >= 8 && clean.length <= 15;
  };

  const handleRegister = async () => {
    if (!selectedRole) return;

    // Validation
    if (activeTab === 'email') {
      if (!email.trim() || !password.trim()) {
        Alert.alert(t('common.error'), t('login.fill_fields'));
        return;
      }
      if (!validateEmail(email)) {
        Alert.alert(t('common.error'), t('register.invalid_email'));
        return;
      }
    } else {
      if (!phone.trim() || !password.trim()) {
        Alert.alert(t('common.error'), t('login.fill_fields'));
        return;
      }
      if (!validatePhone(phone)) {
        Alert.alert(t('common.error'), t('register.invalid_phone'));
        return;
      }
    }

    if (password.length < 8) {
      Alert.alert(t('common.error'), t('register.password_too_short'));
      return;
    }

    setLoading(true);
    try {
      const payload = {
        email: activeTab === 'email' ? email.trim() : undefined,
        phone_number: activeTab === 'phone' ? phone.trim() : undefined,
        password,
        user_type: selectedRole,
      };

      const response = await signUp(payload);

      // Redirect to verification screen
      router.push({
        pathname: '/(auth)/verify',
        params: {
          userId: response.user_id,
          contact: activeTab === 'email' ? email.trim() : phone.trim(),
          channel: response.channel,
          userType: selectedRole,
        },
      });
    } catch (err: any) {
      Alert.alert(
        t('register.registration_failed'),
        err?.response?.data?.detail || 'An error occurred during registration. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  };

  // ── Step 1: Role Picker ──────────────────────────────────
  if (!selectedRole) {
    return (
      <View style={styles.container}>
        {/* Glow effects */}
        <View style={[styles.glowOrb1, { backgroundColor: Colors.primary }]} />
        <View style={[styles.glowOrb2, { backgroundColor: Colors.secondary }]} />

        {/* Back Button */}
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => router.back()}
          activeOpacity={0.7}
        >
          <Ionicons name="arrow-back" size={22} color={Colors.textSecondary} />
        </TouchableOpacity>

        <ScrollView contentContainerStyle={styles.rolePickerScroll} keyboardShouldPersistTaps="handled">
          {/* Header */}
          <View style={styles.header}>
            <LinearGradient
              colors={[Colors.primary, Colors.secondary]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.logoContainer}
            >
              <Ionicons name="person-add-outline" size={32} color={Colors.textOnPrimary} />
            </LinearGradient>
            <Text style={styles.title}>{t('register.create_account')}</Text>
            <Text style={styles.subtitle}>{t('register.choose_role')}</Text>
          </View>

          {/* Role Cards */}
          <View style={styles.rolePickerCards}>
            {/* Shopper */}
            <TouchableOpacity
              style={styles.rolePickerCard}
              onPress={() => setSelectedRole('customer')}
              activeOpacity={0.85}
            >
              <View style={[styles.rolePickerIconCircle, { backgroundColor: Colors.primary }]}>
                <Ionicons name="cart-outline" size={28} color={Colors.textOnPrimary} />
              </View>
              <Text style={styles.rolePickerTitle}>{t('register.i_want_to_shop')}</Text>
              <Text style={styles.rolePickerDesc}>{t('register.i_want_to_shop_desc')}</Text>
            </TouchableOpacity>

            {/* Seller */}
            <TouchableOpacity
              style={styles.rolePickerCard}
              onPress={() => setSelectedRole('merchant')}
              activeOpacity={0.85}
            >
              <View style={[styles.rolePickerIconCircle, { backgroundColor: Colors.secondary }]}>
                <Ionicons name="storefront-outline" size={28} color={Colors.textOnPrimary} />
              </View>
              <Text style={styles.rolePickerTitle}>{t('register.i_want_to_sell')}</Text>
              <Text style={styles.rolePickerDesc}>{t('register.i_want_to_sell_desc')}</Text>
            </TouchableOpacity>
          </View>

          {/* Sign in link */}
          <TouchableOpacity
            style={styles.linkContainer}
            onPress={() => router.replace('/(auth)/gateway')}
          >
            <Text style={styles.linkText}>
              {t('register.have_account')}{' '}
              <Text style={[styles.linkHighlight, { color: Colors.primary }]}>{t('login.sign_in')}</Text>
            </Text>
          </TouchableOpacity>
        </ScrollView>
      </View>
    );
  }

  // ── Step 2: Registration Form ────────────────────────────
  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {/* Glow Effects — role-tinted */}
        <View style={[styles.glowOrb1, { backgroundColor: accentColor }]} />
        <View style={[styles.glowOrb2, { backgroundColor: isMerchant ? Colors.accent : Colors.secondary }]} />

        {/* Back Button — goes back to role picker if no preset */}
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => {
            if (presetRole) {
              router.back();
            } else {
              setSelectedRole(null);
            }
          }}
          activeOpacity={0.7}
        >
          <Ionicons name="arrow-back" size={22} color={Colors.textSecondary} />
        </TouchableOpacity>

        {/* Role-Branded Header */}
        <View style={styles.header}>
          <LinearGradient
            colors={isMerchant ? [Colors.secondary, '#33D4AB'] : [Colors.primary, '#8B83FF']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.logoContainer}
          >
            <Ionicons name={roleIcon as any} size={32} color={Colors.textOnPrimary} />
          </LinearGradient>
          <Text style={styles.title}>{roleTitle}</Text>
          <Text style={styles.subtitle}>{roleSubtitle}</Text>
        </View>

        <View style={[styles.card, { borderColor: `${accentColor}22` }]}>
          {/* Role Badge */}
          <View style={[styles.roleBadge, { backgroundColor: `${accentColor}15`, borderColor: `${accentColor}30` }]}>
            <Ionicons name={roleIcon as any} size={16} color={accentColor} />
            <Text style={[styles.roleBadgeText, { color: accentColor }]}>
              {isMerchant ? t('register.seller_account') : t('register.shopper_account')}
            </Text>
          </View>

          {/* Email/Phone Tabs */}
          <View style={styles.tabContainer}>
            <TouchableOpacity
              style={[styles.tabButton, activeTab === 'email' && [styles.tabButtonActive, { borderColor: `${accentColor}33` }]]}
              onPress={() => setActiveTab('email')}
              activeOpacity={0.7}
            >
              <Text style={[styles.tabText, activeTab === 'email' && styles.tabTextActive]}>
                {t('register.email_tab')}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.tabButton, activeTab === 'phone' && [styles.tabButtonActive, { borderColor: `${accentColor}33` }]]}
              onPress={() => setActiveTab('phone')}
              activeOpacity={0.7}
            >
              <Text style={[styles.tabText, activeTab === 'phone' && styles.tabTextActive]}>
                {t('register.phone_tab')}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Form Inputs */}
          {activeTab === 'email' ? (
            <View style={styles.inputContainer}>
              <Ionicons name="mail-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                placeholder={t('register.email_placeholder')}
                placeholderTextColor={Colors.textMuted}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
              />
            </View>
          ) : (
            <View style={styles.inputContainer}>
              <Ionicons name="phone-portrait-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                placeholder={t('register.phone_placeholder')}
                placeholderTextColor={Colors.textMuted}
                value={phone}
                onChangeText={setPhone}
                keyboardType="phone-pad"
                autoCapitalize="none"
              />
            </View>
          )}

          {/* Password */}
          <View style={styles.inputContainer}>
            <Ionicons name="lock-closed-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('register.password_placeholder')}
              placeholderTextColor={Colors.textMuted}
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
            />
            <TouchableOpacity onPress={() => setShowPassword(!showPassword)} activeOpacity={0.6}>
              <Ionicons name={showPassword ? 'eye-off' : 'eye'} size={20} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>

          {/* Create Button */}
          <TouchableOpacity
            style={[styles.button, { backgroundColor: accentColor }, loading && styles.buttonDisabled]}
            onPress={handleRegister}
            disabled={loading}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color={Colors.textOnPrimary} />
            ) : (
              <Text style={styles.buttonText}>{t('register.create_account')}</Text>
            )}
          </TouchableOpacity>

          {/* Sign In Link */}
          <TouchableOpacity
            style={styles.linkContainer}
            onPress={() => router.replace({ pathname: '/(auth)/login', params: { role: selectedRole } })}
          >
            <Text style={styles.linkText}>
              {t('register.have_account')}{' '}
              <Text style={[styles.linkHighlight, { color: accentColor }]}>{t('login.sign_in')}</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.xl,
  },
  rolePickerScroll: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.xl,
  },
  glowOrb1: {
    position: 'absolute',
    top: '10%',
    right: '-20%',
    width: 300,
    height: 300,
    borderRadius: 150,
    opacity: 0.05,
  },
  glowOrb2: {
    position: 'absolute',
    bottom: '5%',
    left: '-15%',
    width: 250,
    height: 250,
    borderRadius: 125,
    opacity: 0.04,
  },
  backButton: {
    position: 'absolute',
    top: 60,
    left: Spacing.xl,
    width: 44,
    height: 44,
    borderRadius: 22,
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
    marginTop: Spacing.xl,
  },
  logoContainer: {
    width: 72,
    height: 72,
    borderRadius: 36,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.lg,
    ...Shadows.glow,
  },
  title: {
    ...Typography.h1,
    color: Colors.textPrimary,
    marginBottom: Spacing.xs,
    textAlign: 'center',
  },
  subtitle: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
  },

  // ── Role Picker Step ──
  rolePickerCards: {
    gap: Spacing.lg,
    marginBottom: Spacing.xl,
  },
  rolePickerCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.xl,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.medium,
  },
  rolePickerIconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  rolePickerTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginBottom: Spacing.xs,
  },
  rolePickerDesc: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textAlign: 'center',
  },

  // ── Registration Form ──
  card: {
    backgroundColor: Colors.surfaceGlass,
    borderRadius: BorderRadius.xl,
    padding: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.medium,
  },
  roleBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    marginBottom: Spacing.lg,
  },
  roleBadgeText: {
    ...Typography.caption,
    fontWeight: '700',
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: 4,
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.xl,
  },
  tabButton: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.md - 2,
  },
  tabButtonActive: {
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  tabText: {
    ...Typography.label,
    color: Colors.textMuted,
  },
  tabTextActive: {
    color: Colors.textPrimary,
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
    marginEnd: Spacing.sm,
  },
  input: {
    flex: 1,
    color: Colors.textPrimary,
    ...Typography.body,
  },
  button: {
    borderRadius: BorderRadius.md,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.lg,
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
    minHeight: 44,
    justifyContent: 'center',
  },
  linkText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  linkHighlight: {
    fontWeight: '600',
  },
  surfaceGlass: {
    backgroundColor: 'rgba(18, 18, 42, 0.85)',
  },
});
