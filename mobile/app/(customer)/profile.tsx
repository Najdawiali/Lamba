/**
 * Customer Profile Screen — Account info, settings, search alerts, and logout.
 * Premium dark UI with glassmorphic cards.
 * 
 * All buttons are fully functional:
 * - Edit Profile: opens modal to edit display name (saved to local SecureStore)
 * - Favorites: navigates to favorites screen
 * - Notification Preferences: opens modal with toggle switches
 * - Language: toggles language and prompts restart
 * - Currency: opens currency picker modal
 * - Stock Alerts: opens alerts history modal
 * - Privacy Policy / Terms: opens scrollable text modal
 * - Logout: confirmation dialog → clears session → redirects to gateway
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView,
  Modal, FlatList, ActivityIndicator, TextInput, Switch
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { getUser, saveUser, logout, getCustomerAlerts, AlertResponse } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n, toggleLanguage } from '../../services/i18n';
// currency removed
import Constants from 'expo-constants';
import ThemePreferenceRow from '../../components/ThemePreferenceRow';

// ── Notification Preferences (persisted locally) ──────────────
import * as SecureStore from 'expo-secure-store';

const NOTIF_PREFS_KEY = 'lamba_notif_prefs';

interface NotifPrefs {
  stockAlerts: boolean;
  promotions: boolean;
  messages: boolean;
}

const DEFAULT_NOTIF_PREFS: NotifPrefs = {
  stockAlerts: true,
  promotions: true,
  messages: true,
};

const loadNotifPrefs = async (): Promise<NotifPrefs> => {
  try {
    const raw = await SecureStore.getItemAsync(NOTIF_PREFS_KEY);
    return raw ? JSON.parse(raw) : DEFAULT_NOTIF_PREFS;
  } catch {
    return DEFAULT_NOTIF_PREFS;
  }
};

const saveNotifPrefs = async (prefs: NotifPrefs): Promise<void> => {
  try {
    await SecureStore.setItemAsync(NOTIF_PREFS_KEY, JSON.stringify(prefs));
  } catch {}
};

// ── Privacy Policy & Terms Content ────────────────────────────
const PRIVACY_POLICY_EN = `Last updated: June 2026

Lamba ("we", "us", or "our") respects your privacy. This Privacy Policy explains how we collect, use, and protect your information when you use the Lamba mobile application.

1. Information We Collect
• Account information (email, phone number, display name)
• Location data (GPS coordinates for hyper-local product discovery)
• Search queries and browsing history within the app
• Device information (OS version, device model)

2. How We Use Your Information
• To provide hyper-local product search and discovery
• To connect you with nearby merchants
• To send stock availability notifications
• To improve our services and user experience

3. Data Sharing
We do not sell your personal data. We share information only with:
• Merchants you interact with (messages, inquiries)
• Service providers that help us operate (hosting, analytics)

4. Data Security
We use industry-standard encryption (TLS) and secure storage (device keychain) to protect your data.

5. Your Rights
You may request deletion of your account and associated data at any time by contacting support@lamba.app.

6. Contact Us
For privacy inquiries: privacy@lamba.app`;

const PRIVACY_POLICY_AR = `آخر تحديث: يونيو ٢٠٢٦

تحترم لمبة ("نحن") خصوصيتك. توضح سياسة الخصوصية هذه كيفية جمع واستخدام وحماية معلوماتك عند استخدام تطبيق لمبة.

١. المعلومات التي نجمعها
• معلومات الحساب (البريد الإلكتروني، رقم الهاتف، الاسم)
• بيانات الموقع (إحداثيات GPS لاكتشاف المنتجات القريبة)
• عمليات البحث وسجل التصفح داخل التطبيق
• معلومات الجهاز (إصدار النظام، طراز الجهاز)

٢. كيف نستخدم معلوماتك
• لتوفير البحث والاكتشاف المحلي للمنتجات
• لربطك بالتجار القريبين
• لإرسال إشعارات توفر المخزون
• لتحسين خدماتنا وتجربة المستخدم

٣. مشاركة البيانات
لا نبيع بياناتك الشخصية. نشارك المعلومات فقط مع:
• التجار الذين تتواصل معهم (الرسائل، الاستفسارات)
• مزودي الخدمات الذين يساعدوننا في التشغيل (الاستضافة، التحليلات)

٤. أمان البيانات
نستخدم التشفير المعياري (TLS) والتخزين الآمن لحماية بياناتك.

٥. حقوقك
يمكنك طلب حذف حسابك والبيانات المرتبطة به في أي وقت عبر التواصل مع support@lamba.app.

٦. تواصل معنا
للاستفسارات المتعلقة بالخصوصية: privacy@lamba.app`;

const TERMS_OF_SERVICE_EN = `Last updated: June 2026

Welcome to Lamba. By using our application, you agree to these Terms of Service.

1. Service Description
Lamba is a hyper-local retail discovery platform that connects shoppers with nearby merchants. We facilitate product discovery and communication — we do not process payments or handle transactions.

2. User Accounts
• You must provide accurate information when creating an account
• You are responsible for maintaining the security of your account
• You must be at least 13 years old to use Lamba

3. Acceptable Use
You agree not to:
• Provide false or misleading product information
• Harass or spam other users or merchants
• Attempt to reverse-engineer or disrupt the service
• Use the platform for any illegal purpose

4. Merchant Responsibilities
Merchants are solely responsible for:
• Accuracy of product listings and prices
• Product availability and stock information
• Compliance with local business regulations

5. Limitation of Liability
Lamba serves as a discovery and communication platform. We are not responsible for:
• Product quality or accuracy of merchant listings
• Transactions conducted outside the platform
• Disputes between shoppers and merchants

6. Changes to Terms
We may update these terms from time to time. Continued use of Lamba constitutes acceptance of updated terms.

7. Contact
For questions about these terms: legal@lamba.app`;

const TERMS_OF_SERVICE_AR = `آخر تحديث: يونيو ٢٠٢٦

مرحباً بك في لمبة. باستخدامك لتطبيقنا، فإنك توافق على شروط الخدمة هذه.

١. وصف الخدمة
لمبة هي منصة اكتشاف تجزئة محلية تربط المتسوقين بالتجار القريبين. نحن نسهل اكتشاف المنتجات والتواصل — لا نعالج المدفوعات أو المعاملات.

٢. حسابات المستخدمين
• يجب تقديم معلومات دقيقة عند إنشاء الحساب
• أنت مسؤول عن الحفاظ على أمان حسابك
• يجب أن يكون عمرك ١٣ سنة على الأقل لاستخدام لمبة

٣. الاستخدام المقبول
توافق على عدم:
• تقديم معلومات منتج كاذبة أو مضللة
• مضايقة أو إرسال رسائل غير مرغوبة للمستخدمين أو التجار
• محاولة عكس هندسة الخدمة أو تعطيلها
• استخدام المنصة لأي غرض غير قانوني

٤. مسؤوليات التاجر
التجار مسؤولون وحدهم عن:
• دقة قوائم المنتجات والأسعار
• توفر المنتجات ومعلومات المخزون
• الامتثال للوائح الأعمال المحلية

٥. تحديد المسؤولية
تعمل لمبة كمنصة اكتشاف وتواصل. لسنا مسؤولين عن:
• جودة المنتج أو دقة قوائم التاجر
• المعاملات التي تتم خارج المنصة
• النزاعات بين المتسوقين والتجار

٦. تغييرات في الشروط
قد نحدث هذه الشروط من وقت لآخر. الاستمرار في استخدام لمبة يشكل قبولاً للشروط المحدثة.

٧. تواصل معنا
للأسئلة حول هذه الشروط: legal@lamba.app`;

export default function CustomerProfileScreen() {
  const Colors = useThemeColors();
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [loadingUser, setLoadingUser] = useState(true);

  // Alerts state
  const [alerts, setAlerts] = useState<AlertResponse[]>([]);
  const [alertsModalVisible, setAlertsModalVisible] = useState(false);
  const [loadingAlerts, setLoadingAlerts] = useState(false);

  // Currency state removed

  // Edit Profile state
  const [editProfileVisible, setEditProfileVisible] = useState(false);
  const [editName, setEditName] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);

  // Notification Preferences state
  const [notifModalVisible, setNotifModalVisible] = useState(false);
  const [notifPrefs, setNotifPrefs] = useState<NotifPrefs>(DEFAULT_NOTIF_PREFS);

  // Legal text modals state
  const [privacyModalVisible, setPrivacyModalVisible] = useState(false);
  const [termsModalVisible, setTermsModalVisible] = useState(false);

  const loadUserData = async () => {
    try {
      setLoadingUser(true);
      const userData = await getUser();
      setUser(userData);
    } catch (err) {
      console.error('Failed to load user profile:', err);
    } finally {
      setLoadingUser(false);
    }
  };

  useEffect(() => {
    loadUserData();
    loadNotifPrefs().then(setNotifPrefs);
  }, []);

  // ── Edit Profile ──────────────────────────────────────────────
  const handleOpenEditProfile = () => {
    setEditName(user?.full_name || '');
    setEditProfileVisible(true);
  };

  const handleSaveProfile = async () => {
    const trimmedName = editName.trim();
    if (!trimmedName) {
      Alert.alert(t('common.error', 'Error'), t('profile.edit_name_placeholder'));
      return;
    }
    setSavingProfile(true);
    try {
      const updatedUser = { ...user, full_name: trimmedName };
      await saveUser(updatedUser);
      setUser(updatedUser);
      setEditProfileVisible(false);
      Alert.alert(
        t('profile.profile_updated'),
        t('profile.profile_updated_desc')
      );
    } catch (err) {
      console.error('Failed to save profile:', err);
      Alert.alert(t('common.error', 'Error'), t('profile.profile_update_failed'));
    } finally {
      setSavingProfile(false);
    }
  };

  // ── Notification Preferences ──────────────────────────────────
  const handleToggleNotif = useCallback(async (key: keyof NotifPrefs) => {
    const updated = { ...notifPrefs, [key]: !notifPrefs[key] };
    setNotifPrefs(updated);
    await saveNotifPrefs(updated);
  }, [notifPrefs]);

  const handleCloseNotifModal = () => {
    setNotifModalVisible(false);
    Alert.alert(
      t('profile.notif_saved'),
      t('profile.notif_saved_desc')
    );
  };

  // ── Language Toggle ───────────────────────────────────────────
  const handleToggleLanguage = async () => {
    await toggleLanguage();
    Alert.alert(
      t('common.info', 'Info'),
      t('profile.restart_required')
    );
  };

  // ── Stock Alerts ──────────────────────────────────────────────
  const handleOpenAlerts = async () => {
    if (!user || !user.id) {
      Alert.alert(t('common.info'), t('profile.login_required'));
      return;
    }
    setLoadingAlerts(true);
    setAlertsModalVisible(true);
    try {
      const data = await getCustomerAlerts(user.id);
      setAlerts(data);
    } catch (err) {
      console.error('Failed to load search alerts:', err);
      Alert.alert(t('common.error'), t('profile.alerts_failed'));
    } finally {
      setLoadingAlerts(false);
    }
  };

  // ── Logout ────────────────────────────────────────────────────
  const handleLogout = () => {
    Alert.alert(
      t('profile.logout_title'),
      t('profile.logout_confirm'),
      [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('profile.logout'),
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/(auth)/gateway');
          },
        },
      ],
    );
  };

  // ── Derived values ────────────────────────────────────────────
  const hasName = !!user?.full_name;
  const mainText = hasName ? user.full_name : (user?.email || user?.phone_number || t('profile.lamba_shopper'));
  const initials = mainText ? mainText.charAt(0).toUpperCase() : 'L';
  const isAr = i18n.locale.includes('ar');

  const styles = useMemo(() => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    scroll: {
      paddingHorizontal: Spacing.xl,
      paddingBottom: Spacing.xxxl,
    },
    header: {
      paddingVertical: Spacing.lg,
    },
    headerTitle: {
      ...Typography.h1,
      color: Colors.textPrimary,
    },

    // Profile Card
    profileCard: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.xl,
      padding: Spacing.xl,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.lg,
      ...Shadows.medium,
    },
    avatarWrapper: {
      position: 'relative',
      marginBottom: Spacing.md,
    },
    avatar: {
      width: 72,
      height: 72,
      borderRadius: 36,
      justifyContent: 'center',
      alignItems: 'center',
      ...Shadows.glow,
    },
    cameraOverlay: {
      position: 'absolute',
      bottom: 0,
      right: 0,
      width: 24,
      height: 24,
      borderRadius: 12,
      backgroundColor: Colors.surfaceElevated,
      justifyContent: 'center',
      alignItems: 'center',
      borderWidth: 2,
      borderColor: Colors.surface,
    },
    avatarText: {
      fontSize: 28,
      fontWeight: '700',
      color: Colors.textOnPrimary,
    },
    displayNameH2: {
      ...Typography.h2,
      color: Colors.textPrimary,
      marginBottom: 2,
    },
    displayEmail: {
      ...Typography.body,
      color: Colors.textSecondary,
      marginBottom: Spacing.sm,
    },
    roleBadge: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.xs,
      paddingVertical: Spacing.xs,
      paddingHorizontal: Spacing.md,
      borderRadius: BorderRadius.full,
      backgroundColor: Colors.primary,
      borderWidth: 0,
      marginBottom: Spacing.sm,
    },
    roleBadgeText: {
      ...Typography.caption,
      color: Colors.textOnPrimary,
      fontWeight: '700',
    },
    memberSince: {
      ...Typography.caption,
      color: Colors.textMuted,
    },

    // Settings
    sectionCard: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.xl,
      padding: Spacing.lg,
      borderWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.lg,
    },
    sectionTitle: {
      ...Typography.label,
      color: Colors.textMuted,
      textTransform: 'uppercase',
      marginBottom: Spacing.md,
    },
    menuItem: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: Spacing.md,
      gap: Spacing.md,
    },
    menuIcon: {
      width: 40,
      height: 40,
      borderRadius: 12,
      justifyContent: 'center',
      alignItems: 'center',
    },
    menuContent: {
      flex: 1,
    },
    menuLabel: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '500',
    },
    menuValue: {
      ...Typography.bodySmall,
      color: Colors.textMuted,
      marginTop: 1,
    },

    // Logout
    logoutButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: Spacing.sm,
      paddingVertical: Spacing.lg,
      backgroundColor: 'rgba(226, 75, 74, 0.06)',
      borderRadius: BorderRadius.xl,
      borderWidth: 1,
      borderColor: 'rgba(226, 75, 74, 0.15)',
      marginBottom: Spacing.lg,
    },
    logoutText: {
      ...Typography.button,
      color: Colors.error,
    },
    footer: {
      ...Typography.caption,
      color: Colors.textMuted,
      textAlign: 'center',
    },

    // Modal styling (shared)
    modalOverlay: {
      flex: 1,
      backgroundColor: 'rgba(10, 10, 26, 0.65)',
      justifyContent: 'flex-end',
    },
    modalContainer: {
      height: '75%',
      backgroundColor: Colors.background,
      borderTopLeftRadius: BorderRadius.xl,
      borderTopRightRadius: BorderRadius.xl,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    modalHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: Spacing.xl,
      borderBottomWidth: 1,
      borderColor: Colors.border,
    },
    modalTitle: { ...Typography.h2, color: Colors.textPrimary },
    closeBtn: { padding: Spacing.xs },
    modalLoading: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    loadingText: { ...Typography.bodySmall, color: Colors.textMuted, marginTop: Spacing.md },

    // Alerts list
    alertsList: { padding: Spacing.xl, paddingBottom: Spacing.xxxl },
    alertCard: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.lg,
      padding: Spacing.md,
      borderWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.md,
    },
    alertHeaderRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: Spacing.md,
    },
    alertTextGroup: { flex: 1 },
    alertQueryText: { ...Typography.body, color: Colors.textPrimary, fontWeight: '700' },
    alertDate: { ...Typography.caption, color: Colors.textMuted, marginTop: 4 },
    alertGeoText: { ...Typography.caption, color: Colors.textSecondary, marginTop: Spacing.sm, fontStyle: 'italic' },
    statusBadge: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      paddingHorizontal: Spacing.sm,
      paddingVertical: 4,
      borderRadius: BorderRadius.full,
    },
    statusText: { ...Typography.caption, fontWeight: '700', fontSize: 10 },
    emptyAlerts: { alignItems: 'center', paddingVertical: 60, paddingHorizontal: Spacing.xl },
    emptyAlertsTitle: { ...Typography.h3, color: Colors.textSecondary, marginTop: Spacing.lg },
    emptyAlertsText: { ...Typography.bodySmall, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.sm, lineHeight: 20 },

    // Edit Profile modal
    editProfileBody: {
      padding: Spacing.xl,
    },
    inputLabel: {
      ...Typography.body,
      color: Colors.textSecondary,
      marginBottom: Spacing.sm,
      fontWeight: '600',
    },
    textInput: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.lg,
      padding: Spacing.md,
      ...Typography.body,
      color: Colors.textPrimary,
      borderWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.xl,
    },
    saveButton: {
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.lg,
      paddingVertical: Spacing.md,
      alignItems: 'center',
      justifyContent: 'center',
    },
    saveButtonText: {
      ...Typography.button,
      color: Colors.textOnPrimary,
      fontWeight: '700',
    },

    // Notification Preferences modal
    notifBody: {
      padding: Spacing.xl,
    },
    notifRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.lg,
      padding: Spacing.md,
      borderWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.md,
    },
    notifTextGroup: {
      flex: 1,
      marginRight: Spacing.md,
    },
    notifLabel: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '600',
    },
    notifDesc: {
      ...Typography.caption,
      color: Colors.textMuted,
      marginTop: 2,
    },

    // Legal text modals
    legalBody: {
      padding: Spacing.xl,
      paddingBottom: Spacing.xxxl,
    },
    legalText: {
      ...Typography.body,
      color: Colors.textSecondary,
      lineHeight: 22,
    },
  }), [Colors]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{t('profile.title')}</Text>
        </View>

        {/* Profile Card */}
        {loadingUser ? (
          <View style={[styles.profileCard, { paddingVertical: Spacing.xxl }]}>
            <ActivityIndicator size="small" color={Colors.primary} />
          </View>
        ) : (
          <View style={styles.profileCard}>
            <View style={styles.avatarWrapper}>
              <LinearGradient
                colors={[Colors.primary, '#8B83FF']}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={styles.avatar}
              >
                <Text style={styles.avatarText}>{initials}</Text>
              </LinearGradient>
              <View style={styles.cameraOverlay}>
                <Ionicons name="camera" size={12} color={Colors.textPrimary} />
              </View>
            </View>

            {hasName ? (
              <>
                <Text style={styles.displayNameH2}>{user.full_name}</Text>
                {!!user.email && <Text style={styles.displayEmail}>{user.email}</Text>}
              </>
            ) : (
              <Text style={styles.displayEmail}>{mainText}</Text>
            )}

            <View style={styles.roleBadge}>
              <Ionicons name="cart-outline" size={14} color={Colors.textOnPrimary} />
              <Text style={styles.roleBadgeText}>
                {t('profile.shopper_account')}
              </Text>
            </View>

            {user?.created_at && (
              <Text style={styles.memberSince}>
                {t('profile.member_since')} {new Date(user.created_at).toLocaleDateString(isAr ? 'ar-EG' : 'en-US')}
              </Text>
            )}
          </View>
        )}

        {/* Settings Section */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>{t('profile.settings')}</Text>

          {/* Edit Profile */}
          <TouchableOpacity style={styles.menuItem} onPress={handleOpenEditProfile} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(108, 99, 255, 0.1)' }]}>
              <Ionicons name="pencil-outline" size={20} color={Colors.primary} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.edit_profile')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          {/* Favorites */}
          <TouchableOpacity style={styles.menuItem} onPress={() => router.push('/(customer)/favorites')} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(255, 107, 157, 0.1)' }]}>
              <Ionicons name="heart-outline" size={20} color={Colors.accent} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.favorites')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          {/* Notification Preferences */}
          <TouchableOpacity style={styles.menuItem} onPress={() => setNotifModalVisible(true)} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(108, 99, 255, 0.1)' }]}>
              <Ionicons name="notifications-outline" size={20} color={Colors.primary} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.notification_prefs')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          {/* Language */}
          <TouchableOpacity style={styles.menuItem} onPress={handleToggleLanguage} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(108, 99, 255, 0.1)' }]}>
              <Ionicons name="flag-outline" size={20} color={Colors.primary} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.language')}</Text>
              <Text style={styles.menuValue}>{t('profile.language_value')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          {/* Currency removed */}

          {/* Stock Alerts */}
          <TouchableOpacity style={styles.menuItem} onPress={handleOpenAlerts} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(255, 107, 157, 0.1)' }]}>
              <Ionicons name="scan-outline" size={20} color={Colors.accent} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.alerts')}</Text>
              <Text style={styles.menuValue}>{t('profile.alerts_desc')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Appearance — theme picker */}
        <ThemePreferenceRow />

        {/* About Section */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>{t('profile.about')}</Text>

          <TouchableOpacity style={styles.menuItem} onPress={() => setPrivacyModalVisible(true)} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(255, 107, 157, 0.1)' }]}>
              <Ionicons name="shield-checkmark-outline" size={20} color={Colors.accent} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.privacy_policy')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.menuItem} onPress={() => setTermsModalVisible(true)} activeOpacity={0.7}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(255, 107, 157, 0.1)' }]}>
              <Ionicons name="document-text-outline" size={20} color={Colors.accent} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.terms_of_service')}</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
          </TouchableOpacity>

          <View style={styles.menuItem}>
            <View style={[styles.menuIcon, { backgroundColor: 'rgba(255, 107, 157, 0.1)' }]}>
              <Ionicons name="information-circle-outline" size={20} color={Colors.accent} />
            </View>
            <View style={styles.menuContent}>
              <Text style={styles.menuLabel}>{t('profile.version')}</Text>
              <Text style={styles.menuValue}>v{Constants.expoConfig?.version || '1.0.0'} (build 42)</Text>
            </View>
          </View>
        </View>

        {/* Logout Button */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout} activeOpacity={0.8}>
          <Ionicons name="log-out-outline" size={20} color={Colors.error} />
          <Text style={styles.logoutText}>{t('profile.logout')}</Text>
        </TouchableOpacity>

        <Text style={styles.footer}>Lamba v{Constants.expoConfig?.version || '1.0.0'} • Secure &amp; Hyper-local</Text>
      </ScrollView>

      {/* ════════ MODAL: Edit Profile ════════ */}
      <Modal visible={editProfileVisible} animationType="slide" transparent onRequestClose={() => setEditProfileVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={[styles.modalContainer, { height: '45%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.edit_profile')}</Text>
              <TouchableOpacity onPress={() => setEditProfileVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            <View style={styles.editProfileBody}>
              <Text style={styles.inputLabel}>{t('profile.edit_name')}</Text>
              <TextInput
                style={styles.textInput}
                value={editName}
                onChangeText={setEditName}
                placeholder={t('profile.edit_name_placeholder')}
                placeholderTextColor={Colors.textMuted}
                autoCapitalize="words"
                autoCorrect={false}
                maxLength={60}
              />

              <TouchableOpacity
                style={[styles.saveButton, savingProfile && { opacity: 0.6 }]}
                onPress={handleSaveProfile}
                disabled={savingProfile}
                activeOpacity={0.8}
              >
                {savingProfile ? (
                  <ActivityIndicator size="small" color={Colors.textOnPrimary} />
                ) : (
                  <Text style={styles.saveButtonText}>{t('profile.save')}</Text>
                )}
              </TouchableOpacity>
            </View>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Notification Preferences ════════ */}
      <Modal visible={notifModalVisible} animationType="slide" transparent onRequestClose={handleCloseNotifModal}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={[styles.modalContainer, { height: '55%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.notification_prefs')}</Text>
              <TouchableOpacity onPress={handleCloseNotifModal} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={styles.notifBody}>
              {/* Stock Alerts toggle */}
              <View style={styles.notifRow}>
                <View style={styles.notifTextGroup}>
                  <Text style={styles.notifLabel}>{t('profile.notif_stock_alerts')}</Text>
                  <Text style={styles.notifDesc}>{t('profile.notif_stock_alerts_desc')}</Text>
                </View>
                <Switch
                  value={notifPrefs.stockAlerts}
                  onValueChange={() => handleToggleNotif('stockAlerts')}
                  trackColor={{ false: Colors.surfaceElevated, true: 'rgba(108, 99, 255, 0.4)' }}
                  thumbColor={notifPrefs.stockAlerts ? Colors.primary : Colors.textMuted}
                />
              </View>

              {/* Promotions toggle */}
              <View style={styles.notifRow}>
                <View style={styles.notifTextGroup}>
                  <Text style={styles.notifLabel}>{t('profile.notif_promotions')}</Text>
                  <Text style={styles.notifDesc}>{t('profile.notif_promotions_desc')}</Text>
                </View>
                <Switch
                  value={notifPrefs.promotions}
                  onValueChange={() => handleToggleNotif('promotions')}
                  trackColor={{ false: Colors.surfaceElevated, true: 'rgba(108, 99, 255, 0.4)' }}
                  thumbColor={notifPrefs.promotions ? Colors.primary : Colors.textMuted}
                />
              </View>

              {/* Messages toggle */}
              <View style={styles.notifRow}>
                <View style={styles.notifTextGroup}>
                  <Text style={styles.notifLabel}>{t('profile.notif_messages')}</Text>
                  <Text style={styles.notifDesc}>{t('profile.notif_messages_desc')}</Text>
                </View>
                <Switch
                  value={notifPrefs.messages}
                  onValueChange={() => handleToggleNotif('messages')}
                  trackColor={{ false: Colors.surfaceElevated, true: 'rgba(108, 99, 255, 0.4)' }}
                  thumbColor={notifPrefs.messages ? Colors.primary : Colors.textMuted}
                />
              </View>
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Privacy Policy ════════ */}
      <Modal visible={privacyModalVisible} animationType="slide" transparent onRequestClose={() => setPrivacyModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.privacy_policy')}</Text>
              <TouchableOpacity onPress={() => setPrivacyModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={styles.legalBody}>
              <Text style={styles.legalText}>
                {isAr ? PRIVACY_POLICY_AR : PRIVACY_POLICY_EN}
              </Text>
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Terms of Service ════════ */}
      <Modal visible={termsModalVisible} animationType="slide" transparent onRequestClose={() => setTermsModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.terms_of_service')}</Text>
              <TouchableOpacity onPress={() => setTermsModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={styles.legalBody}>
              <Text style={styles.legalText}>
                {isAr ? TERMS_OF_SERVICE_AR : TERMS_OF_SERVICE_EN}
              </Text>
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Stock Alerts ════════ */}
      <Modal visible={alertsModalVisible} animationType="slide" transparent onRequestClose={() => setAlertsModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.stock_notifications')}</Text>
              <TouchableOpacity onPress={() => setAlertsModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            {loadingAlerts ? (
              <View style={styles.modalLoading}>
                <ActivityIndicator size="large" color={Colors.primary} />
                <Text style={styles.loadingText}>{t('profile.fetching_alerts')}</Text>
              </View>
            ) : (
              <FlatList
                data={alerts}
                keyExtractor={(item) => item.id}
                renderItem={({ item }) => (
                  <View style={styles.alertCard}>
                    <View style={styles.alertHeaderRow}>
                      <View style={styles.alertTextGroup}>
                        <Text style={styles.alertQueryText}>{t('profile.query')} "{item.query_text}"</Text>
                        <Text style={styles.alertDate}>
                          {t('profile.created')} {new Date(item.created_at).toLocaleDateString(isAr ? 'ar-EG' : 'en-US')}
                        </Text>
                      </View>

                      <View style={[
                        styles.statusBadge,
                        { backgroundColor: item.is_active ? 'rgba(255, 176, 0, 0.1)' : 'rgba(0, 200, 150, 0.1)' }
                      ]}>
                        <Ionicons
                          name={item.is_active ? 'hourglass-outline' : 'checkmark-circle-outline'}
                          size={12}
                          color={item.is_active ? Colors.warning : Colors.secondary}
                        />
                        <Text style={[
                          styles.statusText,
                          { color: item.is_active ? Colors.warning : Colors.secondary }
                        ]}>
                          {item.is_active ? t('profile.awaiting_stock') : t('profile.resolved')}
                        </Text>
                      </View>
                    </View>
                    
                    <Text style={styles.alertGeoText}>
                      {t('profile.tracking_gps')} {item.latitude.toFixed(4)}, {item.longitude.toFixed(4)} ({t('profile.radius')})
                    </Text>
                  </View>
                )}
                contentContainerStyle={styles.alertsList}
                ListEmptyComponent={
                  <View style={styles.emptyAlerts}>
                    <Ionicons name="notifications-off-outline" size={48} color={Colors.textMuted} />
                    <Text style={styles.emptyAlertsTitle}>{t('profile.no_alerts')}</Text>
                    <Text style={styles.emptyAlertsText}>{t('profile.no_alerts_desc')}</Text>
                  </View>
                }
              />
            )}
          </SafeAreaView>
        </View>
      </Modal>

      {/* Currency Modal removed */}
    </SafeAreaView>
  );
}
