/**
 * Auth Gateway Screen — Welcome Screen.
 * 
 * Simplified direct entry:
 * - App logo and name
 * - "تسجيل الدخول" (Sign in) button
 * - "حساب جديد" (Create account) link
 * - Language switcher pill (EN / ع)
 * - Version footer
 */

import React, { useRef, useEffect, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Animated, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, toggleLanguage, i18n } from '../../services/i18n';

export default function AuthGatewayScreen() {
  const Colors = useThemeColors();
  const router = useRouter();
  const isAr = i18n.locale?.startsWith('ar');

  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(30)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
      Animated.spring(slideAnim, {
        toValue: 0,
        tension: 50,
        friction: 8,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  const styles = useMemo(() => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: Colors.background,
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: Spacing.xxxl,
      paddingHorizontal: Spacing.xl,
    },
    glowOrb1: {
      position: 'absolute',
      top: '12%',
      left: '-15%',
      width: 320,
      height: 320,
      borderRadius: 160,
      backgroundColor: Colors.primary,
      opacity: 0.08,
    },
    glowOrb2: {
      position: 'absolute',
      bottom: '20%',
      right: '-15%',
      width: 280,
      height: 280,
      borderRadius: 140,
      backgroundColor: Colors.secondary,
      opacity: 0.06,
    },
    topBar: {
      width: '100%',
      flexDirection: 'row',
      justifyContent: 'flex-end',
      paddingTop: Spacing.md,
    },
    langButton: {
      paddingVertical: Spacing.xs,
      paddingHorizontal: Spacing.md,
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.full,
      borderWidth: 1,
      borderColor: Colors.border,
      minWidth: 44,
      minHeight: 36,
      justifyContent: 'center',
      alignItems: 'center',
    },
    langText: {
      fontSize: 13,
      color: Colors.textPrimary,
      fontWeight: '700',
    },
    heroSection: {
      alignItems: 'center',
      width: '100%',
      marginTop: -Spacing.xxl,
    },
    title: {
      ...Typography.h1,
      fontSize: 36,
      color: Colors.textPrimary,
      fontWeight: '900',
      textAlign: 'center',
      marginBottom: Spacing.xs,
    },
    tagline: {
      ...Typography.body,
      color: Colors.textSecondary,
      textAlign: 'center',
      lineHeight: 22,
      maxWidth: 280,
    },
    actionsSection: {
      width: '100%',
      gap: Spacing.md,
      marginBottom: Spacing.lg,
    },
    signInButton: {
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.xl,
      height: 54,
      justifyContent: 'center',
      alignItems: 'center',
      flexDirection: 'row',
      gap: Spacing.sm,
      ...Shadows.glow,
    },
    signInButtonText: {
      ...Typography.button,
      color: Colors.textOnPrimary,
      fontSize: 16,
      fontWeight: '800',
    },
    createAccountButton: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.xl,
      height: 54,
      justifyContent: 'center',
      alignItems: 'center',
      borderWidth: 1,
      borderColor: Colors.border,
    },
    createAccountText: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '700',
      fontSize: 15,
    },
    footerText: {
      ...Typography.caption,
      color: Colors.textMuted,
      fontSize: 12,
    },
  }), [Colors]);

  return (
    <View style={styles.container}>
      {/* Background glow ambiance */}
      <View style={styles.glowOrb1} />
      <View style={styles.glowOrb2} />

      {/* Top Bar with Language Toggle */}
      <View style={styles.topBar}>
        <TouchableOpacity style={styles.langButton} onPress={toggleLanguage} activeOpacity={0.7}>
          <Text style={styles.langText}>{isAr ? 'EN' : 'ع'}</Text>
        </TouchableOpacity>
      </View>

      {/* Hero Branding Section */}
      <Animated.View style={[styles.heroSection, { opacity: fadeAnim, transform: [{ translateY: slideAnim }] }]}>
        <Image
          source={require('../../assets/images/lamba-icon.png')}
          style={{ width: 120, height: 120, borderRadius: 30, marginBottom: Spacing.xl }}
          resizeMode="contain"
        />

        <Text style={styles.title}>{t('welcome.title', 'Lamba')}</Text>
        <Text style={styles.tagline}>
          {t('welcome.subtitle', 'Discover nearby local stores and products effortlessly')}
        </Text>
      </Animated.View>

      {/* Action Buttons: Sign In & Create Account */}
      <Animated.View style={[styles.actionsSection, { opacity: fadeAnim }]}>
        <TouchableOpacity
          style={styles.signInButton}
          onPress={() => router.push('/(auth)/login')}
          activeOpacity={0.85}
        >
          <Ionicons name="log-in-outline" size={20} color={Colors.textOnPrimary} />
          <Text style={styles.signInButtonText}>{t('welcome.sign_in', 'Sign In')}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.createAccountButton}
          onPress={() => router.push('/(auth)/register')}
          activeOpacity={0.8}
        >
          <Text style={styles.createAccountText}>{t('welcome.create_account', 'Create Account')}</Text>
        </TouchableOpacity>
      </Animated.View>

      {/* Footer Branding */}
      <Text style={styles.footerText}>{t('welcome.version', 'Lamba v1.2.0 • Local & Secure')}</Text>
    </View>
  );
}
