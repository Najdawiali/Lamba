/**
 * Auth Welcome Screen.
 * 
 * Simplified direct entry:
 * - App logo and name
 * - "تسجيل الدخول" (Sign in) button
 * - "حساب جديد" (Create account) link
 * - Version footer
 */

import React, { useRef, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Animated, Image, Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors, useTheme } from '../../context/ThemeContext';
import { t, i18n, changeLanguage } from '../../services/i18n';

export default function WelcomeScreen() {
  const Colors = useThemeColors();
  const { isDark, setMode } = useTheme();
  const router = useRouter();
  const [, setLangTick] = useState(0);

  const { width: screenWidth } = Dimensions.get('window');
  const iconSize = screenWidth * 0.38; // 38% of screen width — balanced for all devices

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
      paddingTop: 60,
      paddingBottom: Spacing.xxl,
      paddingHorizontal: Spacing.xl,
    },
    glowOrb1: {
      position: 'absolute',
      top: '10%',
      left: '-15%',
      width: 320,
      height: 320,
      borderRadius: 160,
      backgroundColor: 'rgba(255, 179, 0, 0.08)',
    },
    glowOrb2: {
      position: 'absolute',
      bottom: '20%',
      right: '-15%',
      width: 280,
      height: 280,
      borderRadius: 140,
      backgroundColor: 'rgba(255, 143, 0, 0.06)',
    },
    glowOrb3: {
      position: 'absolute',
      top: '40%',
      right: '-20%',
      width: 220,
      height: 220,
      borderRadius: 110,
      backgroundColor: 'rgba(255, 213, 79, 0.07)',
    },
    heroSection: {
      alignItems: 'center',
      width: '100%',
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
      backgroundColor: '#FF8F00',
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
      color: '#FFFFFF',
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
      borderColor: 'rgba(255, 143, 0, 0.3)',
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
      {/* Background warm amber glow ambiance */}
      <View style={styles.glowOrb1} />
      <View style={styles.glowOrb2} />
      <View style={styles.glowOrb3} />

      {/* Top Bar with Language Toggle */}
      <View style={{
        width: '100%',
        flexDirection: 'row',
        justifyContent: 'flex-end',
        paddingHorizontal: Spacing.xs,
        paddingTop: Spacing.xs,
      }}>
        <TouchableOpacity
          onPress={async () => {
            const newLang = i18n.locale?.startsWith('ar') ? 'en' : 'ar';
            await changeLanguage(newLang);
            setLangTick(prev => prev + 1);
          }}
          style={{
            paddingVertical: 6,
            paddingHorizontal: 14,
            borderRadius: 20,
            borderWidth: 1,
            borderColor: Colors.border,
            backgroundColor: Colors.surface,
          }}
          activeOpacity={0.7}
        >
          <Text style={{ color: Colors.textPrimary, fontSize: 14, fontWeight: '600' }}>
            {i18n.locale?.startsWith('ar') ? 'EN' : 'ع'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Hero Branding Section */}
      <Animated.View style={[styles.heroSection, { opacity: fadeAnim, transform: [{ translateY: slideAnim }] }]}>
        <TouchableOpacity
          onPress={() => {
            setMode(isDark ? 'light' : 'dark');
          }}
          activeOpacity={0.8}
          style={{ alignItems: 'center', marginBottom: Spacing.lg }}
        >
          <View style={{ width: iconSize, height: iconSize }}>
            <Image
              source={require('../../assets/images/lamba-icon.png')}
              style={{
                width: iconSize,
                height: iconSize,
                position: 'absolute',
                opacity: isDark ? 0 : 1,
              }}
              resizeMode="contain"
            />
            <Image
              source={require('../../assets/images/lamba-icon-off.png')}
              style={{
                width: iconSize,
                height: iconSize,
                position: 'absolute',
                opacity: isDark ? 1 : 0,
              }}
              resizeMode="contain"
            />
          </View>
          <Text style={{
            color: Colors.textMuted,
            fontSize: 12,
            marginTop: 8,
            textAlign: 'center',
          }}>
            {t('welcome.tap_to_toggle', 'Tap the bulb to switch theme')}
          </Text>
        </TouchableOpacity>

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
          <Ionicons name="log-in-outline" size={20} color="#FFFFFF" />
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
