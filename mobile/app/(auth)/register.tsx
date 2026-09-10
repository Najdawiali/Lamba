/**
 * Registration Screen — Multi-channel Sign Up (Email / Phone).
 * All users sign up as customers; merchant privileges are granted upon store creation.
 */

import React, { useState, useMemo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, Alert, ActivityIndicator, ScrollView,
  Image, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { signUp } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors, useTheme } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';

export default function RegisterScreen() {
  const Colors = useThemeColors();
  const { isDark, setMode } = useTheme();
  const router = useRouter();
  const { width: screenWidth } = Dimensions.get('window');
  const iconSize = screenWidth * 0.22;
  const isAr = i18n.locale?.startsWith('ar');

  const [activeTab, setActiveTab] = useState<'email' | 'phone'>('email');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const validateEmail = (val: string) => {
    const reg = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    return reg.test(val.trim());
  };

  const validatePhone = (val: string) => {
    const clean = val.replace(/\D/g, '');
    return clean.length >= 8 && clean.length <= 15;
  };

  const handleRegister = async () => {
    // Validation
    if (activeTab === 'email') {
      if (!email.trim() || !password.trim()) {
        Alert.alert(t('common.error', 'Error'), t('login.fill_fields', 'Please fill in all fields'));
        return;
      }
      if (!validateEmail(email)) {
        Alert.alert(t('common.error', 'Error'), t('login.invalid_email', 'Please enter a valid email address'));
        return;
      }
    } else {
      if (!phone.trim() || !password.trim()) {
        Alert.alert(t('common.error', 'Error'), t('login.fill_fields', 'Please fill in all fields'));
        return;
      }
      if (!validatePhone(phone)) {
        Alert.alert(t('common.error', 'Error'), t('login.invalid_phone', 'Please enter a valid phone number'));
        return;
      }
    }

    if (password.length < 8) {
      Alert.alert(t('common.error', 'Error'), t('register.password_too_short', 'Password must be at least 8 characters'));
      return;
    }

    setLoading(true);
    try {
      const payload = {
        email: activeTab === 'email' ? email.trim() : undefined,
        phone_number: activeTab === 'phone' ? phone.trim() : undefined,
        password,
        user_type: 'customer' as const, // Always register as customer
      };

      const response = await signUp(payload);

      // Redirect to verification screen
      router.push({
        pathname: '/(auth)/verify',
        params: {
          user_id: response.user_id,
          userId: response.user_id,
          contact: activeTab === 'email' ? email.trim() : phone.trim(),
          channel: response.channel,
          userType: 'customer',
        },
      });
    } catch (err: any) {
      Alert.alert(
        t('register.registration_failed', 'Registration Failed'),
        err?.response?.data?.detail || t('common.error', 'An error occurred during registration. Please try again.')
      );
    } finally {
      setLoading(false);
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    scroll: {
      flexGrow: 1,
      justifyContent: 'center',
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.xxl,
    },
    glowOrb1: {
      position: 'absolute',
      top: '10%',
      right: '-20%',
      width: 300,
      height: 300,
      borderRadius: 150,
      backgroundColor: 'rgba(255, 179, 0, 0.08)',
    },
    glowOrb2: {
      position: 'absolute',
      bottom: '10%',
      left: '-15%',
      width: 260,
      height: 260,
      borderRadius: 130,
      backgroundColor: 'rgba(255, 143, 0, 0.06)',
    },
    header: {
      alignItems: 'center',
      marginBottom: Spacing.xl,
      marginTop: Spacing.lg,
    },
    title: {
      ...Typography.h1,
      fontSize: 26,
      color: Colors.textPrimary,
      marginBottom: Spacing.xs,
      textAlign: 'center',
      fontWeight: '800',
    },
    subtitle: {
      ...Typography.body,
      color: Colors.textSecondary,
      textAlign: 'center',
    },
    card: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.xl,
      padding: Spacing.xl,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    tabContainer: {
      flexDirection: 'row',
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.md,
      padding: 4,
      borderWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.lg,
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
      borderColor: 'rgba(255, 255, 255, 0.08)',
    },
    tabText: {
      ...Typography.label,
      color: Colors.textMuted,
      fontWeight: '600',
    },
    tabTextActive: {
      color: Colors.textPrimary,
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
      minHeight: 44,
      justifyContent: 'center',
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
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
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

        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity
            onPress={() => setMode(isDark ? 'light' : 'dark')}
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
          <Text style={styles.title}>{t('auth.sign_up_title', 'Create Account')}</Text>
          <Text style={styles.subtitle}>{t('welcome.subtitle', 'Join Lamba to discover local stores & products')}</Text>
        </View>

        <View style={styles.card}>
          {/* Email / Phone Tabs */}
          <View style={styles.tabContainer}>
            <TouchableOpacity
              style={[styles.tabButton, activeTab === 'email' && styles.tabButtonActive]}
              onPress={() => setActiveTab('email')}
              activeOpacity={0.7}
            >
              <Text style={[styles.tabText, activeTab === 'email' && styles.tabTextActive]}>
                {t('login.email_tab', 'Email')}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.tabButton, activeTab === 'phone' && styles.tabButtonActive]}
              onPress={() => setActiveTab('phone')}
              activeOpacity={0.7}
            >
              <Text style={[styles.tabText, activeTab === 'phone' && styles.tabTextActive]}>
                {t('auth.phone', 'Phone')}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Form Inputs */}
          {activeTab === 'email' ? (
            <View style={styles.inputContainer}>
              <Ionicons name="mail-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                placeholder={t('login.email_placeholder', 'name@example.com')}
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
                placeholder={t('auth.phone_placeholder', '07XXXXXXXX')}
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
              placeholder={t('auth.password_placeholder', 'Password')}
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

          {/* Submit Button */}
          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleRegister}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>{t('auth.sign_up_button', 'Create Account')}</Text>
            )}
          </TouchableOpacity>

          {/* Sign In Link */}
          <TouchableOpacity
            style={styles.linkContainer}
            onPress={() => router.replace('/(auth)/login')}
            activeOpacity={0.7}
          >
            <Text style={styles.linkText}>
              {t('auth.has_account', 'Already have an account?')}{' '}
              <Text style={styles.linkHighlight}>{t('auth.sign_in_button', 'Sign In')}</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>
  );
}
