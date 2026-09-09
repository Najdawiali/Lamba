/**
 * Sign Up Screen — Single-page User Registration.
 * Captures Full Name, Email, optional Phone, Password, and Confirm Password.
 */

import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
  ScrollView,
  Image,
  Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { signUp } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors, useTheme } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';

export default function SignUpScreen() {
  const Colors = useThemeColors();
  const { isDark, setMode } = useTheme();
  const router = useRouter();
  const { width: screenWidth } = Dimensions.get('window');
  const iconSize = screenWidth * 0.22;
  const isAr = i18n.locale?.startsWith('ar');

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const validateEmail = (val: string) => {
    const reg = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    return reg.test(val.trim());
  };

  const validatePhone = (val: string) => {
    const clean = val.replace(/\D/g, '');
    return clean.length >= 8 && clean.length <= 15;
  };

  const handleSignUp = async () => {
    // 1. Validate full name
    if (!fullName.trim()) {
      Alert.alert(t('common.error', 'Error'), t('login.fill_fields', 'Please fill in all fields'));
      return;
    }

    // 2. Validate email if provided
    if (email.trim() && !validateEmail(email)) {
      Alert.alert(t('common.error', 'Error'), t('login.invalid_email', 'Please enter a valid email address'));
      return;
    }

    // 3. Validate phone if provided
    if (phone.trim() && !validatePhone(phone)) {
      Alert.alert(t('common.error', 'Error'), t('login.invalid_phone', 'Please enter a valid phone number'));
      return;
    }

    // 4. Validate password length
    if (password.length < 8) {
      Alert.alert(t('common.error', 'Error'), t('register.password_too_short', 'Password must be at least 8 characters'));
      return;
    }

    // 5. Validate password confirmation match (Line ~126)
    if (password !== confirmPassword) {
      Alert.alert(t('common.error', 'Error'), t('auth.password_mismatch', 'Passwords do not match'));
      return;
    }

    // 6. Validate at least one contact channel (Line ~132)
    if (!email.trim() && !phone.trim()) {
      Alert.alert(t('common.error', 'Error'), t('auth.email_or_phone_required', 'Please enter email or phone number'));
      return;
    }

    setLoading(true);
    try {
      const payload = {
        email: email.trim() || undefined,
        phone_number: phone.trim() || undefined,
        password,
        user_type: 'customer' as const,
      };

      const response = await signUp(payload);

      // Redirect to verification screen
      router.push({
        pathname: '/(auth)/verify',
        params: {
          user_id: response.user_id,
          userId: response.user_id,
          contact: email.trim() || phone.trim(),
          channel: response.channel,
          userType: 'customer',
        },
      });
    } catch (err: any) {
      Alert.alert(
        t('common.error', 'Error'),
        err?.response?.data?.detail || t('register.registration_failed', 'Registration Failed')
      );
    } finally {
      setLoading(false);
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    scroll: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: Spacing.xl, paddingVertical: Spacing.xxl },
    scrollContent: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: Spacing.xl, paddingVertical: Spacing.xxl },
    glowOrb1: { position: 'absolute', top: '10%', right: '-20%', width: 300, height: 300, borderRadius: 150, backgroundColor: 'rgba(255, 179, 0, 0.08)' },
    glowOrb2: { position: 'absolute', bottom: '10%', left: '-15%', width: 260, height: 260, borderRadius: 130, backgroundColor: 'rgba(255, 143, 0, 0.06)' },
    backButton: { position: 'absolute', top: 50, left: Spacing.xl, width: 42, height: 42, borderRadius: 21, backgroundColor: Colors.surface, justifyContent: 'center', alignItems: 'center', zIndex: 10, borderWidth: 1, borderColor: Colors.border },
    header: { alignItems: 'center', marginBottom: Spacing.xl, marginTop: Spacing.lg },
    welcomeText: { ...Typography.label, color: '#FF8F00', fontWeight: '700', marginBottom: Spacing.xs, textTransform: 'uppercase', letterSpacing: 1 },
    title: { ...Typography.h1, fontSize: 26, color: Colors.textPrimary, marginBottom: Spacing.xs, textAlign: 'center', fontWeight: '800' },
    subtitle: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center' },
    card: { backgroundColor: Colors.surface, borderRadius: BorderRadius.xl, padding: Spacing.xl, borderWidth: 1, borderColor: Colors.border },
    fieldLabel: { ...Typography.bodySmall, color: Colors.textSecondary, fontWeight: '600', marginBottom: Spacing.xs, marginTop: Spacing.xs },
    inputContainer: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: BorderRadius.md, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.lg, marginBottom: Spacing.md, height: 52 },
    inputIcon: { marginHorizontal: Spacing.xs },
    input: { flex: 1, color: Colors.textPrimary, ...Typography.body },
    button: { backgroundColor: '#FF8F00', borderRadius: BorderRadius.xl, height: 54, justifyContent: 'center', alignItems: 'center', marginTop: Spacing.md, ...Shadows.glow },
    buttonDisabled: { opacity: 0.6 },
    buttonText: { ...Typography.button, color: '#FFFFFF', fontSize: 16, fontWeight: '800' },
    linkContainer: { marginTop: Spacing.lg, alignItems: 'center', minHeight: 44, justifyContent: 'center' },
    linkText: { ...Typography.bodySmall, color: Colors.textSecondary },
    linkHighlight: { color: '#FF8F00', fontWeight: '700' },
  }), [Colors]);

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{ flex: 1, backgroundColor: Colors.background }}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 60 : 20}
    >
      <View style={styles.glowOrb1} />
      <View style={styles.glowOrb2} />

      <TouchableOpacity
        style={styles.backButton}
        onPress={() => router.back()}
        activeOpacity={0.7}
      >
        <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={22} color={Colors.textSecondary} />
      </TouchableOpacity>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Header Section */}
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

          {/* Welcome Text (Line ~183) */}
          <Text style={styles.welcomeText}>{t('auth.welcome', 'Welcome')}</Text>

          {/* Header Title (Line ~168) */}
          <Text style={styles.title}>{t('auth.create_account', 'Create Account')}</Text>

          {/* Subtitle (Line ~175) */}
          <Text style={styles.subtitle}>{t('auth.discover_nearby', 'Discover products near you')}</Text>
        </View>

        <View style={styles.card}>
          {/* Full Name Input (Line ~197) */}
          <View style={styles.inputContainer}>
            <Ionicons name="person-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('auth.full_name', 'Full Name')}
              placeholderTextColor={Colors.textMuted}
              value={fullName}
              onChangeText={setFullName}
              autoCapitalize="words"
            />
          </View>

          {/* Email Input (Line ~210) */}
          <View style={styles.inputContainer}>
            <Ionicons name="mail-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('auth.email', 'Email')}
              placeholderTextColor={Colors.textMuted}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
            />
          </View>

          {/* Phone Label (Line ~227) & Phone Placeholder (Line ~228) */}
          <Text style={styles.fieldLabel}>{t('auth.phone_optional', 'Phone Number (optional)')}</Text>
          <View style={styles.inputContainer}>
            <Ionicons name="phone-portrait-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder="07XXXXXXXX"
              placeholderTextColor={Colors.textMuted}
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              autoCapitalize="none"
            />
          </View>

          {/* Password Input (Line ~241) */}
          <View style={styles.inputContainer}>
            <Ionicons name="lock-closed-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('auth.password', 'Password')}
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

          {/* Confirm Password Input (Line ~253) */}
          <View style={styles.inputContainer}>
            <Ionicons name="shield-checkmark-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('auth.confirm_password', 'Confirm Password')}
              placeholderTextColor={Colors.textMuted}
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry={!showConfirmPassword}
              autoCapitalize="none"
            />
            <TouchableOpacity onPress={() => setShowConfirmPassword(!showConfirmPassword)} activeOpacity={0.6}>
              <Ionicons name={showConfirmPassword ? 'eye-off' : 'eye'} size={20} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>

          {/* Signup Button (Line ~270) */}
          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleSignUp}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>{t('auth.sign_up', 'Sign Up')}</Text>
            )}
          </TouchableOpacity>

          {/* Already have account Link (Line ~278) */}
          <TouchableOpacity
            style={styles.linkContainer}
            onPress={() => router.replace('/(auth)/login')}
            activeOpacity={0.7}
          >
            <Text style={styles.linkText}>
              {t('auth.have_account', 'Already have an account?')}{' '}
              <Text style={styles.linkHighlight}>{t('auth.sign_in', 'Sign In')}</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
