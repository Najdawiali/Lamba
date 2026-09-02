/**
 * Customer Profile Screen — Account info, settings, search alerts, and logout.
 * Restructured grouped design with RTL support and working modals.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView,
  Modal, FlatList, ActivityIndicator, TextInput
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getUser, saveUser, logout, getCustomerAlerts, AlertResponse, getMyStore, updateProfile } from '../../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../../constants/theme';
import { useTheme, useThemeColors, ThemeMode } from '../../../context/ThemeContext';
import { t, i18n, toggleLanguage, changeLanguage } from '../../../services/i18n';
import { PRIVACY_POLICY_EN, PRIVACY_POLICY_AR, TERMS_OF_SERVICE_EN, TERMS_OF_SERVICE_AR } from '../../../constants/legal';
import SectionHeader from '../../../components/SectionHeader';
import Divider from '../../../components/Divider';
import Constants from 'expo-constants';

// ── Sub-components for Grouped Layout ─────────────────────────
const MenuRow = ({
  icon,
  label,
  value,
  badge,
  onPress,
  showChevron = true,
}: {
  icon: string;
  label: string;
  value?: string;
  badge?: number;
  onPress: () => void;
  showChevron?: boolean;
}) => {
  const Colors = useThemeColors();
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.6}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 15,
        paddingHorizontal: 20,
      }}
    >
      {/* Left side: chevron + value / badge */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        {showChevron && (
          <Ionicons name="chevron-back" size={16} color={Colors.textSecondary} />
        )}
        {value && (
          <Text style={{ color: Colors.textSecondary, fontSize: 13 }}>
            {value}
          </Text>
        )}
        {badge !== undefined && badge > 0 && (
          <View style={{
            backgroundColor: Colors.primary,
            borderRadius: 10,
            minWidth: 20,
            height: 20,
            justifyContent: 'center',
            alignItems: 'center',
            paddingHorizontal: 6,
          }}>
            <Text style={{ color: '#FFF', fontSize: 11, fontWeight: '700' }}>
              {badge}
            </Text>
          </View>
        )}
      </View>

      {/* Spacer */}
      <View style={{ flex: 1 }} />

      {/* Right side: label + icon */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Text style={{ color: Colors.textPrimary, fontSize: 15, fontWeight: '500' }}>
          {label}
        </Text>
        <View style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          backgroundColor: Colors.surfaceElevated,
          justifyContent: 'center',
          alignItems: 'center',
        }}>
          <Ionicons name={icon as any} size={18} color={Colors.primary} />
        </View>
      </View>
    </TouchableOpacity>
  );
};

export default function CustomerProfileScreen() {
  const Colors = useThemeColors();
  const { mode: themeMode, setMode } = useTheme();
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [loadingUser, setLoadingUser] = useState(true);

  // Alerts state
  const [alerts, setAlerts] = useState<AlertResponse[]>([]);
  const [alertsModalVisible, setAlertsModalVisible] = useState(false);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [alertCount, setAlertCount] = useState(0);

  // Edit Profile state
  const [editProfileVisible, setEditProfileVisible] = useState(false);
  const [editName, setEditName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);

  // Merchant Store detection state
  const [hasStore, setHasStore] = useState(false);
  const [checkingStore, setCheckingStore] = useState(true);

  // Modals state
  const [privacyModalVisible, setPrivacyModalVisible] = useState(false);
  const [termsModalVisible, setTermsModalVisible] = useState(false);
  const [themeModalVisible, setThemeModalVisible] = useState(false);
  const [showLanguageModal, setShowLanguageModal] = useState(false);

  const fetchAlertCount = useCallback(async (userId?: string) => {
    const targetId = userId || user?.id;
    if (!targetId) return;
    try {
      const data = await getCustomerAlerts(targetId);
      setAlertCount(Array.isArray(data) ? data.length : 0);
    } catch {
      setAlertCount(0);
    }
  }, [user?.id]);

  const loadUserData = useCallback(async () => {
    try {
      setLoadingUser(true);
      const userData = await getUser();
      setUser(userData);

      if (userData?.id) {
        fetchAlertCount(userData.id);
      }

      // Check if user has an associated store in backend or has merchant role
      try {
        const store = await getMyStore();
        if (store && store.id) {
          setHasStore(true);
        } else if (userData?.user_type === 'merchant' || userData?.role === 'merchant') {
          setHasStore(true);
        } else {
          setHasStore(false);
        }
      } catch {
        if (userData?.user_type === 'merchant' || userData?.role === 'merchant') {
          setHasStore(true);
        } else {
          setHasStore(false);
        }
      }
    } catch (err) {
      console.error('Failed to load user profile:', err);
    } finally {
      setLoadingUser(false);
      setCheckingStore(false);
    }
  }, [fetchAlertCount]);

  useFocusEffect(
    useCallback(() => {
      loadUserData();
    }, [loadUserData])
  );

  useEffect(() => {
    loadUserData();
  }, [loadUserData]);

  // ── Edit Profile ──────────────────────────────────────────────
  const handleOpenEditProfile = () => {
    setEditName(user?.full_name || '');
    setEditEmail(user?.email || '');
    setEditPhone(user?.phone_number || user?.phone || '');
    setEditProfileVisible(true);
  };

  const handleSaveProfile = async () => {
    const trimmedName = editName.trim();
    const trimmedPhone = editPhone.trim();
    if (!trimmedName) {
      Alert.alert(t('common.error', 'Error'), t('profile.edit_name_placeholder', 'يرجى إدخال اسمك'));
      return;
    }
    setSavingProfile(true);
    try {
      // Persist to backend server
      await updateProfile({
        full_name: trimmedName,
        phone_number: trimmedPhone || undefined,
      });
      // Update local cache
      const updatedUser = {
        ...user,
        full_name: trimmedName,
        phone_number: trimmedPhone || user?.phone_number,
      };
      await saveUser(updatedUser);
      setUser(updatedUser);
      setEditProfileVisible(false);
      Alert.alert(
        t('profile.profile_updated', 'تم حفظ التعديلات'),
        t('profile.profile_updated_desc', 'تم تحديث ملفك الشخصي بنجاح')
      );
    } catch (err) {
      console.error('Failed to save profile:', err);
      Alert.alert(t('common.error', 'Error'), t('profile.profile_update_failed', 'فشل حفظ التعديلات'));
    } finally {
      setSavingProfile(false);
    }
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
      const alertList = Array.isArray(data) ? data : [];
      setAlerts(alertList);
      setAlertCount(alertList.length);
    } catch (err) {
      setAlerts([]);
    } finally {
      setLoadingAlerts(false);
    }
  };

  // ── Logout ────────────────────────────────────────────────────
  const handleLogout = () => {
    Alert.alert(
      t('profile.logout_title', 'تسجيل الخروج'),
      t('profile.logout_confirm', 'هل أنت تأكد من رغبتك في تسجيل الخروج؟'),
      [
        { text: t('common.cancel', 'إلغاء'), style: 'cancel' },
        {
          text: t('profile.logout', 'تسجيل الخروج'),
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
  const userBadge = (user?.user_type === 'merchant' || user?.role === 'merchant' || hasStore)
    ? t('profile.store_owner', 'صاحب متجر')
    : t('profile.shopper_account', 'متسوق');

  const styles = useMemo(() => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: Colors.background,
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
      marginBottom: Spacing.lg,
    },
    saveButton: {
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.lg,
      paddingVertical: Spacing.md,
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: Spacing.sm,
    },
    saveButtonText: {
      ...Typography.button,
      color: Colors.textOnPrimary,
      fontWeight: '700',
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

    // Theme option row
    themeOption: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.xl,
      borderRadius: BorderRadius.lg,
      backgroundColor: Colors.surfaceElevated,
      marginBottom: Spacing.md,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    themeOptionText: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '600',
    },
  }), [Colors]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>

        {/* === User Header Card === */}
        <View style={{
          backgroundColor: Colors.surface,
          paddingVertical: 28,
          paddingHorizontal: 20,
          alignItems: 'center',
          borderBottomLeftRadius: 24,
          borderBottomRightRadius: 24,
          borderWidth: 1,
          borderColor: Colors.border,
          ...Shadows.medium,
        }}>
          {/* Avatar */}
          <View style={{
            width: 72,
            height: 72,
            borderRadius: 36,
            backgroundColor: Colors.primary,
            justifyContent: 'center',
            alignItems: 'center',
            marginBottom: 12,
            ...Shadows.glow,
          }}>
            <Text style={{ color: '#FFF', fontSize: 28, fontWeight: '700' }}>
              {initials}
            </Text>
          </View>
          
          {/* Name */}
          <Text style={{ color: Colors.textPrimary, fontSize: 18, fontWeight: '700', marginBottom: 4 }}>
            {hasName ? user.full_name : (user?.email || user?.phone_number || t('profile.user', 'المتسوق'))}
          </Text>
          
          {/* Email / Phone */}
          <Text style={{ color: Colors.textSecondary, fontSize: 13, marginBottom: 8 }}>
            {user?.email || user?.phone_number || ''}
          </Text>
          
          {/* Role badge */}
          <View style={{
            backgroundColor: Colors.primary + '20',
            borderRadius: 12,
            paddingVertical: 4,
            paddingHorizontal: 12,
          }}>
            <Text style={{ color: Colors.primary, fontSize: 12, fontWeight: '600' }}>
              {userBadge}
            </Text>
          </View>
        </View>

        {/* === Manage Store Button (only if has store) === */}
        {!checkingStore && hasStore && (
          <TouchableOpacity
            onPress={() => router.push('/(merchant)/dashboard')}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: Colors.primary,
              marginHorizontal: 16,
              marginTop: 16,
              borderRadius: 14,
              paddingVertical: 14,
              paddingHorizontal: 18,
              ...Shadows.small,
            }}
            activeOpacity={0.85}
          >
            <Ionicons name="chevron-back" size={20} color="#FFF" />
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Text style={{ color: '#FFF', fontSize: 15, fontWeight: '700' }}>
                {t('profile.manage_store', 'إدارة متجري')}
              </Text>
              <Ionicons name="storefront" size={20} color="#FFF" />
            </View>
          </TouchableOpacity>
        )}

        {/* === Add Store Button (only if NO store) === */}
        {!checkingStore && !hasStore && (
          <TouchableOpacity
            onPress={() => router.push('/create-store')}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: Colors.surfaceElevated,
              marginHorizontal: 16,
              marginTop: 16,
              borderRadius: 14,
              paddingVertical: 14,
              paddingHorizontal: 18,
              borderWidth: 1,
              borderColor: Colors.primary + '30',
              ...Shadows.small,
            }}
            activeOpacity={0.85}
          >
            <Ionicons name="chevron-back" size={20} color={Colors.primary} />
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Text style={{ color: Colors.textPrimary, fontSize: 15, fontWeight: '600' }}>
                {t('profile.add_store', 'إضافة متجرك')}
              </Text>
              <Ionicons name="add-circle-outline" size={20} color={Colors.primary} />
            </View>
          </TouchableOpacity>
        )}

        {/* === Section: الحساب (Account) === */}
        <SectionHeader title={t('profile.section_account', 'Account')} />
        <View style={{
          backgroundColor: Colors.surface,
          marginHorizontal: 16,
          borderRadius: 14,
          overflow: 'hidden',
          borderWidth: 1,
          borderColor: Colors.border,
        }}>
          <MenuRow
            icon="person-outline"
            label={t('profile.edit_profile', 'تعديل الملف الشخصي')}
            onPress={handleOpenEditProfile}
          />
          <Divider />
          <MenuRow
            icon="notifications-outline"
            label={t('profile.availability_alerts', 'تنبيهات التوفر')}
            badge={alertCount}
            onPress={handleOpenAlerts}
          />
        </View>

        {/* === Section: التطبيق (App Settings) === */}
        <SectionHeader title={t('profile.section_app', 'App')} />
        <View style={{
          backgroundColor: Colors.surface,
          marginHorizontal: 16,
          borderRadius: 14,
          overflow: 'hidden',
          borderWidth: 1,
          borderColor: Colors.border,
        }}>
          <MenuRow
            icon="language-outline"
            label={t('profile.language', 'اللغة')}
            value={isAr ? 'العربية' : 'English'}
            onPress={() => setShowLanguageModal(true)}
          />
          <Divider />
          <MenuRow
            icon="color-palette-outline"
            label={t('profile.theme', 'المظهر')}
            value={themeMode === 'dark' ? t('profile.theme_dark', 'Dark') : themeMode === 'light' ? t('profile.theme_light', 'Light') : t('profile.theme_system', 'System')}
            onPress={() => setThemeModalVisible(true)}
          />
        </View>

        {/* === Section: معلومات (Info) === */}
        <SectionHeader title={t('profile.section_info', 'Info')} />
        <View style={{
          backgroundColor: Colors.surface,
          marginHorizontal: 16,
          borderRadius: 14,
          overflow: 'hidden',
          borderWidth: 1,
          borderColor: Colors.border,
        }}>
          <MenuRow
            icon="shield-checkmark-outline"
            label={t('profile.privacy_policy', 'سياسة الخصوصية')}
            onPress={() => setPrivacyModalVisible(true)}
          />
          <Divider />
          <MenuRow
            icon="document-text-outline"
            label={t('profile.terms', 'شروط الخدمة')}
            onPress={() => setTermsModalVisible(true)}
          />
          <Divider />
          <MenuRow
            icon="information-circle-outline"
            label={t('profile.version', 'الإصدار')}
            value={`v${Constants.expoConfig?.version || '1.0.0'}`}
            showChevron={false}
            onPress={() => {}}
          />
        </View>

        {/* === Sign Out === */}
        <View style={{ marginHorizontal: 16, marginTop: 24, marginBottom: 20 }}>
          <TouchableOpacity
            onPress={handleLogout}
            activeOpacity={0.8}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'rgba(226, 75, 74, 0.06)',
              borderWidth: 1,
              borderColor: 'rgba(226, 75, 74, 0.2)',
              borderRadius: 14,
              paddingVertical: 14,
              gap: 8,
            }}
          >
            <Text style={{ color: Colors.error, fontSize: 15, fontWeight: '600' }}>
              {t('profile.logout', 'تسجيل الخروج')}
            </Text>
            <Ionicons name="log-out-outline" size={20} color={Colors.error} />
          </TouchableOpacity>
        </View>

        {/* Footer */}
        <Text style={{
          color: Colors.textMuted,
          fontSize: 11,
          textAlign: 'center',
          marginBottom: 30,
          opacity: 0.8,
        }}>
          {`Lamba v${Constants.expoConfig?.version || '1.0.0'} · ${t('profile.footer_tagline', 'Local & Secure')}`}
        </Text>
      </ScrollView>

      {/* ════════ MODAL: Edit Profile ════════ */}
      <Modal visible={editProfileVisible} animationType="slide" transparent onRequestClose={() => setEditProfileVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={[styles.modalContainer, { height: '65%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.edit_profile', 'تعديل الملف الشخصي')}</Text>
              <TouchableOpacity onPress={() => setEditProfileVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={styles.editProfileBody} keyboardShouldPersistTaps="handled">
              {/* Full Name */}
              <Text style={styles.inputLabel}>{t('profile.edit_name', 'الاسم الكامل')}</Text>
              <TextInput
                style={styles.textInput}
                value={editName}
                onChangeText={setEditName}
                placeholder={t('profile.edit_name_placeholder', 'أدخل اسمك')}
                placeholderTextColor={Colors.textMuted}
                autoCapitalize="words"
                autoCorrect={false}
                maxLength={60}
              />

              {/* Email */}
              <Text style={styles.inputLabel}>{t('common.email', 'البريد الإلكتروني')}</Text>
              <TextInput
                style={[styles.textInput, { opacity: 0.7 }]}
                value={editEmail}
                editable={false}
                placeholder={t('auth.email_placeholder', 'example@domain.com')}
                placeholderTextColor={Colors.textMuted}
                autoCapitalize="none"
                keyboardType="email-address"
              />

              {/* Phone */}
              <Text style={styles.inputLabel}>{t('profile.phone', 'رقم الهاتف')}</Text>
              <TextInput
                style={styles.textInput}
                value={editPhone}
                onChangeText={setEditPhone}
                placeholder={t('profile.phone_placeholder', '07XXXXXXXX')}
                placeholderTextColor={Colors.textMuted}
                keyboardType="phone-pad"
                maxLength={20}
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
                  <Text style={styles.saveButtonText}>{t('profile.save', 'حفظ')}</Text>
                )}
              </TouchableOpacity>
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Language Selection ════════ */}
      <Modal visible={showLanguageModal} animationType="slide" transparent onRequestClose={() => setShowLanguageModal(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={[styles.modalContainer, { height: '42%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.choose_language', 'اختر اللغة')}</Text>
              <TouchableOpacity onPress={() => setShowLanguageModal(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <View style={{ padding: Spacing.xl }}>
              {[
                { code: 'ar', label: 'العربية', sublabel: 'Arabic' },
                { code: 'en', label: 'English', sublabel: 'الإنجليزية' },
              ].map((lang) => {
                const isSelected = (isAr && lang.code === 'ar') || (!isAr && lang.code === 'en');
                return (
                  <TouchableOpacity
                    key={lang.code}
                    style={[styles.themeOption, isSelected && { borderColor: Colors.primary }]}
                    onPress={async () => {
                      setShowLanguageModal(false);
                      if ((lang.code === 'ar' && !isAr) || (lang.code === 'en' && isAr)) {
                        await changeLanguage(lang.code as 'ar' | 'en');
                      }
                    }}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.themeOptionText, isSelected && { color: Colors.primary }]}>
                        {lang.label}
                      </Text>
                      <Text style={{ color: Colors.textMuted, fontSize: 12, marginTop: 2 }}>
                        {lang.sublabel}
                      </Text>
                    </View>
                    {isSelected && <Ionicons name="checkmark-circle" size={22} color={Colors.primary} />}
                  </TouchableOpacity>
                );
              })}
              <TouchableOpacity
                onPress={() => setShowLanguageModal(false)}
                style={{ paddingVertical: 14, alignItems: 'center', marginTop: 4 }}
              >
                <Text style={{ color: Colors.textSecondary, fontSize: 14 }}>{t('common.cancel', 'إلغاء')}</Text>
              </TouchableOpacity>
            </View>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Theme Selection ════════ */}
      <Modal visible={themeModalVisible} animationType="slide" transparent onRequestClose={() => setThemeModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={[styles.modalContainer, { height: '40%' }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.theme', 'اختيار المظهر')}</Text>
              <TouchableOpacity onPress={() => setThemeModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <View style={{ padding: Spacing.xl }}>
              {(['system', 'light', 'dark'] as ThemeMode[]).map((modeOption) => {
                const isSelected = themeMode === modeOption;
                const labels: Record<ThemeMode, string> = {
                  system: t('profile.theme_system', 'System'),
                  light: t('profile.theme_light', 'Light'),
                  dark: t('profile.theme_dark', 'Dark'),
                };
                return (
                  <TouchableOpacity
                    key={modeOption}
                    style={[styles.themeOption, isSelected && { borderColor: Colors.primary }]}
                    onPress={() => {
                      setMode(modeOption);
                      setThemeModalVisible(false);
                    }}
                  >
                    <Text style={[styles.themeOptionText, isSelected && { color: Colors.primary }]}>
                      {labels[modeOption]}
                    </Text>
                    {isSelected && <Ionicons name="checkmark-circle" size={20} color={Colors.primary} />}
                  </TouchableOpacity>
                );
              })}
            </View>
          </SafeAreaView>
        </View>
      </Modal>

      {/* ════════ MODAL: Privacy Policy ════════ */}
      <Modal visible={privacyModalVisible} animationType="slide" transparent onRequestClose={() => setPrivacyModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <SafeAreaView style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{t('profile.privacy_policy', 'سياسة الخصوصية')}</Text>
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
              <Text style={styles.modalTitle}>{t('profile.terms_of_service', 'شروط الخدمة')}</Text>
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
              <Text style={styles.modalTitle}>{t('profile.stock_notifications', 'تنبيهات التوفر')}</Text>
              <TouchableOpacity onPress={() => setAlertsModalVisible(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>

            {loadingAlerts ? (
              <View style={styles.modalLoading}>
                <ActivityIndicator size="large" color={Colors.primary} />
                <Text style={styles.loadingText}>{t('profile.fetching_alerts', 'جاري تحميل التنبيهات...')}</Text>
              </View>
            ) : (
              <FlatList
                data={alerts}
                keyExtractor={(item) => item.id}
                renderItem={({ item }) => (
                  <View style={styles.alertCard}>
                    <View style={styles.alertHeaderRow}>
                      <View style={styles.alertTextGroup}>
                        <Text style={styles.alertQueryText}>{t('profile.query', 'البحث:')} "{item.query_text}"</Text>
                        <Text style={styles.alertDate}>
                          {t('profile.created', 'التاريخ:')} {new Date(item.created_at).toLocaleDateString(isAr ? 'ar-EG' : 'en-US')}
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
                          {item.is_active ? t('profile.awaiting_stock', 'في انتظار التوفر') : t('profile.resolved', 'تم التوفر')}
                        </Text>
                      </View>
                    </View>
                    
                    <Text style={styles.alertGeoText}>
                      {t('profile.tracking_gps', 'الموقع:')} {item.latitude.toFixed(4)}, {item.longitude.toFixed(4)} ({t('profile.radius', 'نطاق متتبع')})
                    </Text>
                  </View>
                )}
                contentContainerStyle={styles.alertsList}
                ListEmptyComponent={
                  <View style={styles.emptyAlerts}>
                    <Ionicons name="notifications-off-outline" size={48} color={Colors.textMuted} />
                    <Text style={styles.emptyAlertsTitle}>{t('profile.no_alerts', 'لا توجد تنبيهات توفر حالياً')}</Text>
                    <Text style={styles.emptyAlertsText}>{t('profile.no_alerts_desc', 'سنقوم بتنبيهك تلقائياً عند توفر المنتجات غير الموجودة في الدليل')}</Text>
                  </View>
                }
              />
            )}
          </SafeAreaView>
        </View>
      </Modal>

    </SafeAreaView>
  );
}
