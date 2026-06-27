/**
 * Auth Gateway — Role-First Selection Screen.
 * Two role cards: "Shop with Lamba" vs "Sell with Lamba".
 * Single unified register link below both cards.
 * Routes to login with role pre-set via query param.
 *
 * Design spec:
 * - Full-screen dark background, Lamba logo + eye icon centered at 40% from top
 * - Two role cards stacked vertically with 16px gap
 * - Language toggle: text-only pill (EN/ع), top-right
 * - Single "New to Lamba? Create an account" link below cards
 * - Footer: version string
 */

import React, { useRef, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Dimensions, Animated,
} from 'react-native';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { t, toggleLanguage, i18n } from '../../services/i18n';

const { width } = Dimensions.get('window');

export default function AuthGatewayScreen() {
  const router = useRouter();
  const isAr = i18n.locale.includes('ar');

  // Entrance animations
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideCustomer = useRef(new Animated.Value(40)).current;
  const slideSeller = useRef(new Animated.Value(40)).current;

  useEffect(() => {
    Animated.sequence([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
      Animated.stagger(150, [
        Animated.spring(slideCustomer, {
          toValue: 0,
          tension: 60,
          friction: 9,
          useNativeDriver: true,
        }),
        Animated.spring(slideSeller, {
          toValue: 0,
          tension: 60,
          friction: 9,
          useNativeDriver: true,
        }),
      ]),
    ]).start();
  }, []);

  const navigateToLogin = (role: 'customer' | 'merchant') => {
    router.push({ pathname: '/(auth)/login', params: { role } });
  };

  const navigateToRegister = () => {
    // Unified registration — no role pre-set, user picks on step 1
    router.push({ pathname: '/(auth)/register' });
  };

  return (
    <View style={styles.container}>
      {/* Premium Ambient Background Glows */}
      <View style={styles.glowOrb1} />
      <View style={styles.glowOrb2} />
      <View style={styles.glowOrb3} />



      {/* Top Welcome / Branding Section — centered at ~40% from top */}
      <Animated.View style={[styles.heroSection, { opacity: fadeAnim }]}>
        <LinearGradient
          colors={[Colors.primary, Colors.secondary]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.logoContainer}
        >
          <Ionicons name="eye" size={48} color={Colors.textOnPrimary} />
        </LinearGradient>

        <Text style={styles.title}>{t('gateway.welcome')}</Text>
        <View style={styles.taglineWrapper}>
          <Text style={styles.tagline}>
            {t('gateway.choose_role')}
          </Text>
        </View>

        {/* Language Switcher — centered pill between tagline and cards */}
        <TouchableOpacity style={styles.langButton} onPress={toggleLanguage} activeOpacity={0.7}>
          <Text style={styles.langText}>{isAr ? 'EN' : 'ع'}</Text>
        </TouchableOpacity>
      </Animated.View>

      {/* Role Selection Cards — stacked with 16px gap */}
      <View style={styles.cardsSection}>
        {/* ── Customer Card ─────────────────────────────── */}
        <Animated.View style={{ transform: [{ translateY: slideCustomer }], opacity: fadeAnim }}>
          <TouchableOpacity
            style={styles.roleCard}
            onPress={() => navigateToLogin('customer')}
            activeOpacity={0.85}
          >
            <View style={[styles.roleIconCircle, { backgroundColor: Colors.primary }]}>
              <Ionicons name="cart-outline" size={24} color={Colors.textOnPrimary} />
            </View>

            <View style={styles.roleCardContent}>
              <Text style={styles.roleCardTitle}>
                {t('gateway.shop_with')}
              </Text>
              <Text style={styles.roleCardDesc}>
                {t('gateway.discover_desc')}
              </Text>
            </View>

            <Ionicons name="chevron-forward" size={20} color={Colors.textSecondary} />
          </TouchableOpacity>
        </Animated.View>

        {/* 16px gap between cards (handled by cardsSection gap) */}

        {/* ── Seller Card ───────────────────────────────── */}
        <Animated.View style={{ transform: [{ translateY: slideSeller }], opacity: fadeAnim }}>
          <TouchableOpacity
            style={styles.roleCard}
            onPress={() => navigateToLogin('merchant')}
            activeOpacity={0.85}
          >
            <View style={[styles.roleIconCircle, { backgroundColor: Colors.secondary }]}>
              <Ionicons name="storefront-outline" size={24} color={Colors.textOnPrimary} />
            </View>

            <View style={styles.roleCardContent}>
              <Text style={styles.roleCardTitle}>
                {t('gateway.sell_with')}
              </Text>
              <Text style={styles.roleCardDesc}>
                {t('gateway.manage_desc')}
              </Text>
            </View>

            <Ionicons name="chevron-forward" size={20} color={Colors.textSecondary} />
          </TouchableOpacity>
        </Animated.View>

        {/* Unified Registration Link */}
        <TouchableOpacity
          style={styles.unifiedRegisterLink}
          onPress={navigateToRegister}
          activeOpacity={0.7}
        >
          <Text style={styles.unifiedRegisterText}>
            {t('gateway.new_to_lamba')}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Footer Branding */}
      <Text style={styles.footerText}>Lamba v1.2.0 • Secure & Hyper-local</Text>
    </View>
  );
}

const styles = StyleSheet.create({
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
    top: '10%',
    left: '-20%',
    width: 320,
    height: 320,
    borderRadius: 160,
    backgroundColor: Colors.primary,
    opacity: 0.08,
  },
  glowOrb2: {
    position: 'absolute',
    bottom: '25%',
    right: '-15%',
    width: 280,
    height: 280,
    borderRadius: 140,
    backgroundColor: Colors.secondary,
    opacity: 0.06,
  },
  glowOrb3: {
    position: 'absolute',
    top: '40%',
    right: '30%',
    width: 150,
    height: 150,
    borderRadius: 75,
    backgroundColor: Colors.accent,
    opacity: 0.04,
  },

  // Language toggle — centered pill between tagline and cards
  langButton: {
    alignSelf: 'center',
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.full,
    marginTop: Spacing.lg,
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

  // Hero — centered at ~40%
  heroSection: {
    alignItems: 'center',
    marginTop: Spacing.md,
  },
  logoContainer: {
    width: 88,
    height: 88,
    borderRadius: 44,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.lg,
    ...Shadows.glow,
  },
  title: {
    ...Typography.h1,
    fontSize: 32,
    color: Colors.textPrimary,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: Spacing.xs,
  },
  taglineWrapper: {
    paddingHorizontal: Spacing.lg,
  },
  tagline: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
  },

  // ── Cards Section ──
  cardsSection: {
    width: '100%',
    gap: Spacing.lg, // 16px gap between cards
    marginBottom: Spacing.lg,
  },
  roleCard: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface, // #12122A card background
    borderRadius: BorderRadius.lg, // 16px
    padding: 20,
    minHeight: 72,
  },
  roleIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginEnd: Spacing.lg,
  },
  roleCardContent: {
    flex: 1,
    marginEnd: Spacing.sm,
  },
  roleCardTitle: {
    ...Typography.h3,
    color: Colors.textPrimary,
    marginBottom: 2,
  },
  roleCardDesc: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },

  // Unified register link
  unifiedRegisterLink: {
    alignItems: 'center',
    paddingVertical: Spacing.md,
    minHeight: 44,
    justifyContent: 'center',
  },
  unifiedRegisterText: {
    ...Typography.caption,
    color: Colors.primary,
    fontWeight: '600',
  },

  footerText: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
});
