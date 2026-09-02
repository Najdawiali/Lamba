/**
 * Merchant Profile Screen — Account info, market details, settings, and logout.
 * Redesigned with inline edit sheets, GPS address detection, lock on first edit,
 * employee management, analytics, and RTL support.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView, ActivityIndicator,
  Modal, Switch, RefreshControl, TextInput, FlatList, TouchableWithoutFeedback, Keyboard
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import {
  getUser, logout,
  getMarketProfile, updateMarketProfile, updateEmployees,
  MarketProfileResponse, MarketProfileUpdatePayload,
} from '../../services/api';
import {
  useMarket, useMarketItems, useInventoryValue, useCheckoutHistory,
  useUpdateMarketStatus, merchantKeys,
} from '../../hooks/useMerchant';
import { useQueryClient } from '@tanstack/react-query';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useTheme, useThemeColors, ThemeMode } from '../../context/ThemeContext';
import { t, i18n, changeLanguage } from '../../services/i18n';
import { formatPrice } from '../../services/currency';
import { PRIVACY_POLICY_EN, PRIVACY_POLICY_AR, TERMS_OF_SERVICE_EN, TERMS_OF_SERVICE_AR } from '../../constants/legal';
import SectionHeader from '../../components/SectionHeader';
import Divider from '../../components/Divider';
import LegalModal from '../../components/LegalModal';
import PickerModal from '../../components/PickerModal';
import EmployeesModal from '../../components/EmployeesModal';
import Constants from 'expo-constants';

// ── Sub-components for Grouped Layout ─────────────────────────
const MenuRow = ({
  icon,
  label,
  subtitle,
  value,
  badge,
  onPress,
  showChevron = true,
  isLocked = false,
  iconColor,
  iconBgColor,
  disabled = false,
}: {
  icon: string;
  label: React.ReactNode;
  subtitle?: string;
  value?: string | null;
  badge?: number;
  onPress?: () => void;
  showChevron?: boolean;
  isLocked?: boolean;
  iconColor?: string;
  iconBgColor?: string;
  disabled?: boolean;
}) => {
  const Colors = useThemeColors();
  const isAr = i18n.locale.includes('ar');

  const content = (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 14,
        paddingHorizontal: 20,
      }}
    >
      {/* Left side: chevron / lock icon + value / badge */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 1, maxWidth: '55%' }}>
        {isLocked ? (
          <Ionicons name="lock-closed" size={15} color={Colors.textMuted} />
        ) : showChevron ? (
          <Ionicons name={isAr ? "chevron-back" : "chevron-forward"} size={16} color={Colors.textSecondary} />
        ) : null}
        {value && (
          <Text style={{ color: Colors.textSecondary, fontSize: 13 }} numberOfLines={1}>
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

      {/* Right side: label & subtitle + icon */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <View style={{ alignItems: isAr ? 'flex-end' : 'flex-start' }}>
          {typeof label === 'string' ? (
            <Text style={{ color: Colors.textPrimary, fontSize: 15, fontWeight: '500' }}>
              {label}
            </Text>
          ) : (
            label
          )}
          {subtitle && (
            <Text style={{ color: Colors.textMuted, fontSize: 11, marginTop: 2 }}>
              {subtitle}
            </Text>
          )}
        </View>
        <View style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          backgroundColor: iconBgColor || Colors.surfaceElevated,
          justifyContent: 'center',
          alignItems: 'center',
        }}>
          <Ionicons name={icon as any} size={18} color={iconColor || Colors.primary} />
        </View>
      </View>
    </View>
  );

  if (disabled || isLocked || !onPress) {
    return content;
  }

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.6}>
      {content}
    </TouchableOpacity>
  );
};

export default function MerchantProfileScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const { mode: themeMode, setMode } = useTheme();
  const [user, setUser] = useState<any>(null);
  const isAr = i18n.locale.includes('ar');

  // React Query merchant hooks
  const queryClient = useQueryClient();
  const { data: market, isLoading: loadingMarket } = useMarket();
  const { data: products = [] } = useMarketItems();
  const { data: inventoryData } = useInventoryValue();
  const { data: historyReceipts = [] } = useCheckoutHistory();
  const updateStatusMutation = useUpdateMarketStatus();

  const totalAssetsValue = inventoryData?.total_value ?? 0;
  const totalProducts = products.length;
  const inStockCount = products.filter(p => p.in_stock).length;

  // Market Profile & Lock States
  const [profileData, setProfileData] = useState<MarketProfileResponse | null>(null);
  const [employeesModalVisible, setEmployeesModalVisible] = useState(false);

  // Inline edit bottom sheet states
  const [editField, setEditField] = useState<'name' | 'address' | 'phone' | 'email' | null>(null);
  const [editValue, setEditValue] = useState('');
  const [savingField, setSavingField] = useState(false);
  const [detectingLocation, setDetectingLocation] = useState(false);

  // Employees states
  const [employeeList, setEmployeeList] = useState<string[]>([]);
  const [savingEmployees, setSavingEmployees] = useState(false);

  // Relocated Analytics & Status States
  const [analyticsVisible, setAnalyticsVisible] = useState(false);
  const [refreshingStats, setRefreshingStats] = useState(false);

  // Modals state
  const [privacyModalVisible, setPrivacyModalVisible] = useState(false);
  const [termsModalVisible, setTermsModalVisible] = useState(false);
  const [themeModalVisible, setThemeModalVisible] = useState(false);
  const [showLanguageModal, setShowLanguageModal] = useState(false);

  const loadProfileData = useCallback(async () => {
    try {
      const profile = await getMarketProfile();
      setProfileData(profile);
      setEmployeeList(profile.employees || []);
    } catch (err) {
      console.warn('Failed to load market profile:', err);
    }
  }, []);

  const stats = useMemo(() => {
    const todayStr = new Date().toISOString().substring(0, 10);
    
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterdayStr = yesterdayDate.toISOString().substring(0, 10);

    let todaySales = 0;
    let yesterdaySales = 0;
    let thisWeekSales = 0;
    let lastWeekSales = 0;

    let todayTxCount = 0;
    const todaySoldItems: Record<string, number> = {};

    const oneDayMs = 24 * 60 * 60 * 1000;
    const nowMs = new Date().getTime();

    historyReceipts.forEach(r => {
      const receiptDateStr = r.created_at.substring(0, 10);
      const receiptTime = new Date(r.created_at).getTime();
      const ageDays = (nowMs - receiptTime) / oneDayMs;

      if (receiptDateStr === todayStr) {
        todaySales += r.total_cost;
        todayTxCount += 1;
        r.items.forEach(item => {
          todaySoldItems[item.name] = (todaySoldItems[item.name] || 0) + item.quantity;
        });
      } else if (receiptDateStr === yesterdayStr) {
        yesterdaySales += r.total_cost;
      }

      if (ageDays <= 7) {
        thisWeekSales += r.total_cost;
      } else if (ageDays > 7 && ageDays <= 14) {
        lastWeekSales += r.total_cost;
      }
    });

    const dailyChange = yesterdaySales > 0 ? ((todaySales - yesterdaySales) / yesterdaySales) * 100 : 0;
    const weeklyChange = lastWeekSales > 0 ? ((thisWeekSales - lastWeekSales) / lastWeekSales) * 100 : 0;

    let topSellingItem = '';
    let topSellingQty = 0;
    Object.keys(todaySoldItems).forEach(name => {
      if (todaySoldItems[name] > topSellingQty) {
        topSellingQty = todaySoldItems[name];
        topSellingItem = name;
      }
    });

    const totalItemsSoldToday = Object.values(todaySoldItems).reduce((sum, qty) => sum + qty, 0);

    let summaryAnalysis = '';
    if (todayTxCount > 0) {
      const trendText = todaySales >= yesterdaySales 
        ? (yesterdaySales > 0 
            ? `${isAr ? 'بزيادة قدرها' : 'representing a'} ${dailyChange.toFixed(1)}% ${isAr ? 'عن يوم أمس' : 'increase compared to yesterday'}`
            : (isAr ? 'مع عدم وجود مبيعات مسجلة يوم أمس' : 'with zero sales recorded yesterday'))
        : `${isAr ? 'بانخفاض قدره' : 'representing a'} ${Math.abs(dailyChange).toFixed(1)}% ${isAr ? 'عن يوم أمس' : 'decrease compared to yesterday'}`;

      const topItemText = topSellingItem 
        ? `, ${isAr ? 'وكان المنتج الأكثر مبيعاً هو' : 'and your top-performing item was'} "${topSellingItem}" (${topSellingQty} ${isAr ? 'قطع' : 'units'})`
        : '';

      summaryAnalysis = isAr 
        ? `اليوم، حققت مبيعات بقيمة ${formatPrice(todaySales)} عبر ${todayTxCount} عمليات دفع كاشير (${trendText}). تم بيع إجمالي ${totalItemsSoldToday} قطع من المنتجات${topItemText}. يستمر المتجر في الأداء الجيد، ويرجى مراقبة مستويات المخزون للمنتجات النشطة.`
        : `Today you generated ${formatPrice(todaySales)} across ${todayTxCount} POS checkouts (${trendText}). A total of ${totalItemsSoldToday} units were sold${topItemText}. The store continues to track well; monitor stock counts for high-velocity items.`;
    } else {
      const yesterdayText = yesterdaySales > 0
        ? (isAr 
            ? `يوم أمس حققت مبيعات بقيمة ${formatPrice(yesterdaySales)}.`
            : `Yesterday you generated ${formatPrice(yesterdaySales)} in transaction value.`)
        : (isAr
            ? 'لم تسجل أي مبيعات يوم أمس أيضاً.'
            : 'No sales were recorded yesterday either.');

      summaryAnalysis = isAr
        ? `لم تقم بإجراء أي عمليات بيع كاشير اليوم حتى الآن. ${yesterdayText} ابدأ بمسح المنتجات في وضع الكاشير (POS) لتسجيل المبيعات تلقائياً وتحديث المخزون.`
        : `You have not processed any POS cashier transactions today. ${yesterdayText} Align barcodes in POS Cashier mode to register checkouts and auto-adjust inventory.`;
    }

    return {
      todaySales,
      yesterdaySales,
      thisWeekSales,
      lastWeekSales,
      dailyChange,
      weeklyChange,
      todayTxCount,
      totalItemsSoldToday,
      topSellingItem,
      summaryAnalysis
    };
  }, [historyReceipts, isAr]);

  useEffect(() => {
    (async () => {
      try {
        const userData = await getUser();
        setUser(userData);
      } catch (err) {
        console.error('Failed to get user data:', err);
      }

      await loadProfileData();
    })();
  }, [loadProfileData]);

  // Open Edit Sheet
  const openEditSheet = (field: 'name' | 'address' | 'phone' | 'email') => {
    if (field === 'name' && profileData?.is_name_locked) return;
    if (field === 'address' && profileData?.is_address_locked) return;

    switch (field) {
      case 'name':
        setEditValue(market?.name || market?.name_ar || '');
        break;
      case 'address':
        setEditValue(market?.address || market?.address_ar || '');
        break;
      case 'phone':
        setEditValue(profileData?.contact_phone || market?.contact_phone || market?.phone || '');
        break;
      case 'email':
        setEditValue(profileData?.contact_email || market?.contact_email || '');
        break;
    }
    setEditField(field);
  };

  // Save Field
  const saveField = async () => {
    if (!editField) return;

    const trimmed = editValue.trim();

    // Mandatory fields validation: name, address, phone cannot be empty
    if ((editField === 'name' || editField === 'address' || editField === 'phone') && !trimmed) {
      Alert.alert(
        isAr ? 'حقل إلزامي' : 'Mandatory Field',
        isAr ? 'هذا الحقل إلزامي ولا يمكن تركه فارغاً' : 'This field is required and cannot be left empty'
      );
      return;
    }

    // Phone format validation
    if (editField === 'phone') {
      const cleanDigits = trimmed.replace(/[\s-]/g, '');
      if (!/^\+?\d{7,20}$/.test(cleanDigits)) {
        Alert.alert(
          isAr ? 'رقم هاتف غير صالح' : 'Invalid Phone Number',
          isAr ? 'يرجى إدخال رقم هاتف صحيح (٧ إلى ٢٠ رقماً)' : 'Please enter a valid phone number (7 to 20 digits)'
        );
        return;
      }
    }

    setSavingField(true);

    try {
      let payload: MarketProfileUpdatePayload = {};

      switch (editField) {
        case 'name':
          payload = { name: trimmed, name_ar: trimmed };
          break;
        case 'address':
          payload = { address: trimmed, address_ar: trimmed };
          break;
        case 'phone':
          payload = { contact_phone: trimmed };
          break;
        case 'email':
          payload = { contact_email: trimmed };
          break;
      }

      const updated = await updateMarketProfile(payload);
      setProfileData(updated);

      // Also refresh market state for the header display
      await queryClient.invalidateQueries({ queryKey: merchantKeys.market });

      setEditField(null);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        const errorMsg = err.response?.data?.detail;
        Alert.alert(
          isAr ? 'غير مسموح' : 'Not Allowed',
          errorMsg || (isAr ? 'تم تعديل هذا الحقل مسبقاً. تواصل مع الدعم لأي تغييرات.' : 'This field was already edited. Contact support for changes.')
        );
      } else {
        Alert.alert(t('common.error', 'خطأ'), isAr ? 'فشل حفظ التعديلات' : 'Failed to save changes');
      }
    } finally {
      setSavingField(false);
    }
  };

  // GPS Location Detection
  const detectLocation = async () => {
    setDetectingLocation(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert(
          isAr ? 'صلاحية الموقع' : 'Location Permission',
          isAr ? 'يرجى السماح بالوصول إلى موقعك لتحديد عنوان المتجر تلقائياً' : 'Please allow location access to auto-detect your store address'
        );
        return;
      }

      const location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const [result] = await Location.reverseGeocodeAsync({
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
      });

      if (result) {
        const parts = [result.street, result.district, result.city, result.region].filter(Boolean);
        const address = parts.join(', ');
        setEditValue(address);
      }
    } catch (err) {
      console.warn('Location detection failed:', err);
      Alert.alert(
        isAr ? 'خطأ' : 'Error',
        isAr ? 'فشل تحديد الموقع. يرجى إدخال العنوان يدوياً.' : 'Failed to detect location. Please enter address manually.'
      );
    } finally {
      setDetectingLocation(false);
    }
  };

  // Employee Delete Handler
  const handleDeleteEmployee = async (index: number) => {
    if (employeeList.length <= 1) {
      Alert.alert(
        isAr ? 'حقل إلزامي' : 'Mandatory Requirement',
        isAr ? 'يجب الإبقاء على موظف واحد على الأقل في المتجر' : 'The store must have at least one employee'
      );
      return;
    }

    const updated = employeeList.filter((_, idx) => idx !== index);
    setEmployeeList(updated);
    setSavingEmployees(true);
    try {
      const res = await updateEmployees(updated);
      setProfileData(res);
      setEmployeeList(res.employees || updated);
      await queryClient.invalidateQueries({ queryKey: merchantKeys.market });
    } catch (err: any) {
      Alert.alert(
        t('common.error', 'خطأ'),
        isAr ? 'فشل حذف الموظف' : 'Failed to remove employee'
      );
      setEmployeeList(profileData?.employees || []);
    } finally {
      setSavingEmployees(false);
    }
  };

  const handleLogout = () => {
    Alert.alert(
      t('profile.logout_title', 'تسجيل الخروج'),
      t('profile.logout_confirm', 'هل أنت متأكد من رغبتك في تسجيل الخروج؟'),
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

  const displayName = user?.name || user?.full_name || (isAr ? 'التاجر' : 'Merchant');
  const initials = displayName.charAt(0).toUpperCase();
  const appVersion = Constants.expoConfig?.version || '1.0.0';

  const styles = useMemo(() => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: Colors.background,
    },

    // Inline Edit Bottom Sheet styles
    sheetOverlay: {
      flex: 1,
      backgroundColor: 'rgba(0, 0, 0, 0.5)',
      justifyContent: 'flex-end',
    },
    sheetContent: {
      backgroundColor: Colors.surface,
      borderTopLeftRadius: BorderRadius.xl,
      borderTopRightRadius: BorderRadius.xl,
      padding: Spacing.xl,
      borderWidth: 1,
      borderColor: Colors.border,
      borderBottomWidth: 0,
      paddingBottom: Spacing.xxxl,
    },
    sheetNotch: {
      width: 36,
      height: 4,
      borderRadius: 2,
      backgroundColor: Colors.border,
      alignSelf: 'center',
      marginBottom: Spacing.lg,
    },
    sheetTitle: {
      ...Typography.h3,
      color: Colors.textPrimary,
      marginBottom: Spacing.md,
      textAlign: isAr ? 'right' : 'left',
    },
    sheetInputWrapper: {
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.md,
      borderWidth: 1,
      borderColor: Colors.border,
      paddingHorizontal: Spacing.md,
      height: 50,
      justifyContent: 'center',
      marginBottom: Spacing.md,
    },
    sheetInput: {
      color: Colors.textPrimary,
      ...Typography.body,
      textAlign: isAr ? 'right' : 'left',
    },
    sheetWarning: {
      ...Typography.caption,
      color: Colors.warning,
      marginBottom: Spacing.md,
      textAlign: isAr ? 'right' : 'left',
    },
    sheetSaveBtn: {
      backgroundColor: Colors.tabActive,
      borderRadius: BorderRadius.md,
      height: 48,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: Spacing.lg,
    },
    sheetSaveBtnText: {
      ...Typography.button,
      color: '#FFF',
      fontWeight: '700',
    },
    detectLocationBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingVertical: Spacing.sm,
      paddingHorizontal: Spacing.md,
      borderRadius: BorderRadius.md,
      backgroundColor: 'rgba(108, 99, 255, 0.08)',
      borderWidth: 1,
      borderColor: 'rgba(108, 99, 255, 0.2)',
      marginBottom: Spacing.md,
    },
    detectLocationText: {
      ...Typography.bodySmall,
      color: Colors.primary,
      fontWeight: '600',
    },
    lockedNote: {
      ...Typography.caption,
      color: Colors.textMuted,
      fontStyle: 'italic',
      textAlign: isAr ? 'right' : 'left',
      paddingHorizontal: 20,
      paddingBottom: Spacing.sm,
    },
    menuLabel: {
      color: Colors.textPrimary,
      fontSize: 15,
      fontWeight: '500',
    },
    optionalBadge: {
      backgroundColor: Colors.surfaceElevated,
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 4,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    optionalBadgeText: {
      fontSize: 10,
      color: Colors.textMuted,
      fontWeight: '500',
    },

    // Analytics Modal Specific
    analyticsModalContainer: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    analyticsModalScroll: {
      paddingTop: Spacing.sm,
      paddingBottom: Spacing.xxxl + 40,
    },
    analyticsModalHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.lg,
      borderBottomWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.md,
    },
    analyticsModalTitle: {
      ...Typography.h2,
      color: Colors.textPrimary,
    },
    modalCloseBtn: {
      padding: Spacing.xs,
    },
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      gap: Spacing.md,
    },
    loadingText: {
      ...Typography.bodySmall,
      color: Colors.textMuted,
    },
    statusCardContainer: {
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.xl,
      padding: Spacing.lg,
      marginHorizontal: Spacing.lg,
      marginBottom: Spacing.md,
      borderWidth: 1,
      borderColor: Colors.border,
      ...Shadows.small,
    },
    statusCardTitle: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '600',
    },
    statusCardValue: {
      fontWeight: '700',
    },
    statusCardSubtitle: {
      ...Typography.caption,
      color: Colors.textMuted,
      marginTop: 2,
    },
    statusDot: {
      width: 10,
      height: 10,
      borderRadius: 5,
    },
    assetsGlowCard: {
      marginHorizontal: Spacing.lg,
      marginBottom: Spacing.md,
      borderRadius: BorderRadius.xl,
      overflow: 'hidden',
      borderWidth: 1,
      borderColor: 'rgba(108, 99, 255, 0.25)',
      backgroundColor: Colors.surfaceElevated,
      ...Shadows.small,
    },
    assetsGlowInner: {
      flexDirection: 'row',
      padding: Spacing.lg,
      alignItems: 'center',
      gap: Spacing.md,
    },
    assetsIconWrapper: {
      width: 46,
      height: 46,
      borderRadius: 23,
      backgroundColor: 'rgba(108, 99, 255, 0.12)',
      justifyContent: 'center',
      alignItems: 'center',
    },
    assetsTextWrapper: {
      flex: 1,
    },
    assetsLabel: {
      ...Typography.caption,
      color: Colors.textSecondary,
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    },
    assetsValue: {
      ...Typography.h2,
      color: Colors.textPrimary,
      fontWeight: '800',
      marginTop: 2,
    },
    loadingRow: {
      paddingVertical: Spacing.lg,
      alignItems: 'center',
    },
    setupButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: Spacing.sm,
      paddingVertical: Spacing.lg,
      backgroundColor: 'rgba(0, 217, 166, 0.06)',
      borderRadius: BorderRadius.md,
      borderWidth: 1,
      borderColor: 'rgba(0, 217, 166, 0.15)',
      borderStyle: 'dashed',
      margin: Spacing.md,
    },
    setupText: {
      ...Typography.button,
      color: Colors.secondary,
    },
  }), [Colors, isAr]);

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
          ...Shadows.small,
        }}>
          {/* Avatar */}
          <LinearGradient
            colors={[Colors.secondary, '#33E4BC']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={{
              width: 72,
              height: 72,
              borderRadius: 36,
              justifyContent: 'center',
              alignItems: 'center',
              marginBottom: 12,
              ...Shadows.glow,
            }}
          >
            <Text style={{ color: '#FFF', fontSize: 28, fontWeight: '700' }}>
              {initials}
            </Text>
          </LinearGradient>

          {/* Name */}
          <Text style={{ color: Colors.textPrimary, fontSize: 18, fontWeight: '700', marginBottom: 4 }}>
            {displayName}
          </Text>

          {/* Email / Phone */}
          {(user?.email || user?.phone_number) && (
            <Text style={{ color: Colors.textSecondary, fontSize: 13, marginBottom: 8 }}>
              {user?.email || user?.phone_number}
            </Text>
          )}

          {/* Role badge */}
          <View style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 4,
            backgroundColor: 'rgba(0, 217, 166, 0.1)',
            borderRadius: 12,
            paddingVertical: 4,
            paddingHorizontal: 12,
            borderWidth: 1,
            borderColor: 'rgba(0, 217, 166, 0.2)',
            marginBottom: user?.created_at ? 6 : 0,
          }}>
            <Ionicons name="storefront-outline" size={14} color={Colors.secondary} />
            <Text style={{ color: Colors.secondary, fontSize: 12, fontWeight: '600' }}>
              {t('merchant.seller_account', 'حساب البائع')}
            </Text>
          </View>

          {/* Member since */}
          {user?.created_at && (
            <Text style={{ color: Colors.textMuted, fontSize: 12, marginTop: 4 }}>
              {t('profile.member_since', 'عضو منذ')}{' '}
              {new Date(user.created_at).toLocaleDateString(isAr ? 'ar-EG' : undefined)}
            </Text>
          )}
        </View>

        {/* === Back to Shopping Banner === */}
        <TouchableOpacity
          onPress={() => router.replace('/(customer)/search')}
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
          <Ionicons name={isAr ? "chevron-back" : "chevron-forward"} size={20} color="#FFF" />
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Text style={{ color: '#FFF', fontSize: 15, fontWeight: '700' }}>
              {t('merchant.back_to_shopping', 'العودة للتسوق')}
            </Text>
            <Ionicons name="cart" size={20} color="#FFF" />
          </View>
        </TouchableOpacity>

        {/* === Section: Store Info === */}
        <SectionHeader title={t('profile.section_store', 'My Store')} />
        <View style={{
          backgroundColor: Colors.surface,
          marginHorizontal: 16,
          borderRadius: 14,
          overflow: 'hidden',
          borderWidth: 1,
          borderColor: Colors.border,
        }}>
          {loadingMarket ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator size="small" color={Colors.secondary} />
            </View>
          ) : market ? (
            <>
              {/* Row 1 — Store Name */}
              <MenuRow
                icon="storefront-outline"
                iconColor={Colors.secondary}
                iconBgColor="rgba(0, 217, 166, 0.12)"
                label={isAr ? 'اسم المتجر' : 'Store Name'}
                value={(isAr && (profileData?.name_ar || market.name_ar)) ? (profileData?.name_ar || market.name_ar) : (profileData?.name || market.name)}
                isLocked={profileData?.is_name_locked}
                showChevron={!profileData?.is_name_locked}
                onPress={() => openEditSheet('name')}
              />
              {profileData?.is_name_locked && (
                <Text style={styles.lockedNote}>
                  {isAr ? 'تم تعديل اسم المتجر — للتعديل تواصل مع الدعم' : 'Store name locked — contact support to change'}
                </Text>
              )}
              <Divider />

              {/* Row 2 — Store Address */}
              <MenuRow
                icon="location-outline"
                iconColor={Colors.primary}
                iconBgColor="rgba(108, 99, 255, 0.12)"
                label={isAr ? 'عنوان المتجر' : 'Store Address'}
                value={
                  (isAr && (profileData?.address_ar || market.address_ar))
                    ? (profileData?.address_ar || market.address_ar)
                    : (profileData?.address || market.address || (isAr ? 'غير متوفر' : 'N/A'))
                }
                isLocked={profileData?.is_address_locked}
                showChevron={!profileData?.is_address_locked}
                onPress={() => openEditSheet('address')}
              />
              {profileData?.is_address_locked && (
                <Text style={styles.lockedNote}>
                  {isAr ? 'تم تعديل عنوان المتجر — للتعديل تواصل مع الدعم' : 'Store address locked — contact support to change'}
                </Text>
              )}
              <Divider />

              {/* Row 3 — Phone */}
              <MenuRow
                icon="call-outline"
                iconColor={Colors.secondary}
                iconBgColor="rgba(0, 217, 166, 0.12)"
                label={isAr ? 'رقم الهاتف' : 'Phone Number'}
                value={profileData?.contact_phone || market.contact_phone || market.phone || (isAr ? 'غير محدد' : 'Not set')}
                onPress={() => openEditSheet('phone')}
              />
              <Divider />

              {/* Row 4 — Email */}
              <MenuRow
                icon="mail-outline"
                iconColor="#3B82F6"
                iconBgColor="rgba(59, 130, 246, 0.12)"
                label={
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={styles.optionalBadge}>
                      <Text style={styles.optionalBadgeText}>{isAr ? 'اختياري' : 'optional'}</Text>
                    </View>
                    <Text style={styles.menuLabel}>{isAr ? 'البريد الإلكتروني' : 'Email'}</Text>
                  </View>
                }
                value={profileData?.contact_email || market.contact_email || (isAr ? 'غير محدد' : 'Not set')}
                onPress={() => openEditSheet('email')}
              />
              <Divider />

              {/* Row 5 — Employees */}
              <MenuRow
                icon="people-outline"
                iconColor={Colors.primary}
                iconBgColor="rgba(108, 99, 255, 0.12)"
                label={isAr ? 'الموظفون' : 'Employees'}
                value={`${profileData?.employees?.length ?? employeeList.length} ${isAr ? 'موظف' : 'staff'}`}
                onPress={() => setEmployeesModalVisible(true)}
              />
            </>
          ) : (
            <TouchableOpacity
              style={styles.setupButton}
              onPress={() => router.push('/(merchant)/onboarding')}
              activeOpacity={0.8}
            >
              <Ionicons name="add-circle-outline" size={20} color={Colors.secondary} />
              <Text style={styles.setupText}>
                {t('onboarding.title', 'إعداد المتجر')}
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* === Section: Analytics === */}
        <SectionHeader title={t('profile.section_analytics', 'Analytics')} />
        <View style={{
          backgroundColor: Colors.surface,
          marginHorizontal: 16,
          borderRadius: 14,
          overflow: 'hidden',
          borderWidth: 1,
          borderColor: Colors.border,
        }}>
          {/* Row 6 — Analytics */}
          <MenuRow
            icon="bar-chart-outline"
            iconColor={Colors.secondary}
            iconBgColor="rgba(0, 217, 166, 0.12)"
            label={t('merchant.analytics_status', 'إحصائيات وحالة المتجر')}
            subtitle={isAr ? 'تتبع المبيعات وقيمة المخزون وحالة المتجر' : 'Track sales, inventory valuation & status'}
            onPress={() => setAnalyticsVisible(true)}
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
            iconColor={Colors.primary}
            label={t('profile.language', 'اللغة')}
            value={isAr ? 'العربية' : 'English'}
            onPress={() => setShowLanguageModal(true)}
          />
          <Divider />
          <MenuRow
            icon="color-palette-outline"
            iconColor={Colors.secondary}
            label={t('profile.theme', 'المظهر')}
            value={
              themeMode === 'dark'
                ? t('profile.theme_dark', 'Dark')
                : themeMode === 'light'
                ? t('profile.theme_light', 'Light')
                : t('profile.theme_system', 'System')
            }
            onPress={() => setThemeModalVisible(true)}
          />
          <Divider />
          <MenuRow
            icon="notifications-outline"
            iconColor={Colors.textMuted}
            label={t('profile.notifications', 'الإشعارات')}
            value={isAr ? 'مقفل' : 'Disabled'}
            showChevron={false}
            disabled={true}
          />
        </View>

        {/* === Section: معلومات (About & Legal) === */}
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
            iconColor={Colors.primary}
            label={t('profile.privacy_policy', 'سياسة الخصوصية')}
            onPress={() => setPrivacyModalVisible(true)}
          />
          <Divider />
          <MenuRow
            icon="document-text-outline"
            iconColor={Colors.secondary}
            label={t('profile.terms', 'شروط الخدمة')}
            onPress={() => setTermsModalVisible(true)}
          />
          <Divider />
          <MenuRow
            icon="information-circle-outline"
            iconColor={Colors.accent}
            label={t('profile.version', 'الإصدار')}
            value={`v${appVersion}`}
            showChevron={false}
            disabled={true}
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
          {`Lamba v${appVersion} · ${t('profile.footer_tagline', 'Local & Secure')}`}
        </Text>
      </ScrollView>

      {/* ════════ MODAL: Inline Edit Bottom Sheet ════════ */}
      <Modal
        visible={editField !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setEditField(null)}
      >
        <TouchableWithoutFeedback onPress={() => setEditField(null)}>
          <View style={styles.sheetOverlay}>
            <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
              <View style={styles.sheetContent}>
                {/* Notch */}
                <View style={styles.sheetNotch} />

                {/* Title */}
                <Text style={styles.sheetTitle}>
                  {editField === 'name' && (isAr ? 'اسم المتجر' : 'Store Name')}
                  {editField === 'address' && (isAr ? 'عنوان المتجر' : 'Store Address')}
                  {editField === 'phone' && (isAr ? 'رقم الهاتف' : 'Phone Number')}
                  {editField === 'email' && (isAr ? 'البريد الإلكتروني' : 'Email')}
                </Text>

                {/* GPS button for address only */}
                {editField === 'address' && (
                  <TouchableOpacity
                    style={styles.detectLocationBtn}
                    onPress={detectLocation}
                    disabled={detectingLocation}
                    activeOpacity={0.7}
                  >
                    {detectingLocation ? (
                      <ActivityIndicator size="small" color={Colors.primary} />
                    ) : (
                      <Ionicons name="locate-outline" size={18} color={Colors.primary} />
                    )}
                    <Text style={styles.detectLocationText}>
                      {detectingLocation
                        ? (isAr ? 'جاري تحديد الموقع...' : 'Detecting location...')
                        : (isAr ? 'تحديد موقعي الحالي' : 'Detect my current location')}
                    </Text>
                  </TouchableOpacity>
                )}

                {/* Input */}
                <View style={styles.sheetInputWrapper}>
                  <TextInput
                    style={styles.sheetInput}
                    value={editValue}
                    onChangeText={setEditValue}
                    placeholder={
                      editField === 'name' ? (isAr ? 'مثال: سوبرماركت القدس' : 'e.g. Quds Supermarket') :
                      editField === 'address' ? (isAr ? 'مثال: السلط، شارع اليرموك' : 'e.g. As-Salt, Yarmouk St.') :
                      editField === 'phone' ? (isAr ? 'مثال: 0790871034' : 'e.g. 0790871034') :
                      (isAr ? 'مثال: store@lamba.com' : 'e.g. store@lamba.com')
                    }
                    placeholderTextColor={Colors.textMuted}
                    keyboardType={
                      editField === 'phone' ? 'phone-pad' :
                      editField === 'email' ? 'email-address' :
                      'default'
                    }
                    autoFocus
                  />
                </View>

                {/* Warning for name/address */}
                {editField === 'name' && (
                  <Text style={styles.sheetWarning}>
                    {isAr ? '⚠️ يمكنك تعديل اسم المتجر مرة واحدة فقط' : '⚠️ Store name can only be edited once'}
                  </Text>
                )}
                {editField === 'address' && (
                  <Text style={styles.sheetWarning}>
                    {isAr ? '⚠️ يمكنك تعديل عنوان المتجر مرة واحدة فقط' : '⚠️ Store address can only be edited once'}
                  </Text>
                )}

                {/* Save button */}
                <TouchableOpacity
                  style={styles.sheetSaveBtn}
                  onPress={saveField}
                  disabled={savingField || !editValue.trim()}
                  activeOpacity={0.8}
                >
                  {savingField ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <Text style={styles.sheetSaveBtnText}>
                      {isAr ? 'حفظ' : 'Save'}
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            </TouchableWithoutFeedback>
          </View>
        </TouchableWithoutFeedback>
      </Modal>

      {/* ════════ MODAL: Employees Management ════════ */}
      <EmployeesModal
        visible={employeesModalVisible}
        onClose={() => setEmployeesModalVisible(false)}
        employees={employeeList}
        onAdd={async (name) => {
          const updated = [...employeeList, name];
          setSavingEmployees(true);
          try {
            const res = await updateEmployees(updated);
            setProfileData(res);
            setEmployeeList(res.employees || updated);
            await queryClient.invalidateQueries({ queryKey: merchantKeys.market });
          } catch (err: any) {
            Alert.alert(
              t('common.error', 'خطأ'),
              isAr ? 'فشل إضافة الموظف' : 'Failed to add employee'
            );
            setEmployeeList(profileData?.employees || []);
          } finally {
            setSavingEmployees(false);
          }
        }}
        onDelete={(index) => handleDeleteEmployee(index)}
        saving={savingEmployees}
      />

      {/* ════════ MODAL: Language Selection ════════ */}
      <PickerModal
        visible={showLanguageModal}
        onClose={() => setShowLanguageModal(false)}
        title={t('profile.choose_language', 'اختر اللغة')}
        options={[
          { key: 'ar', label: 'العربية', icon: 'language-outline', subtitle: 'Arabic' },
          { key: 'en', label: 'English', icon: 'language-outline', subtitle: 'الإنجليزية' },
        ]}
        selectedKey={i18n.locale?.startsWith('ar') ? 'ar' : 'en'}
        onSelect={(key) => changeLanguage(key as 'ar' | 'en')}
      />

      {/* ════════ MODAL: Theme Selection ════════ */}
      <PickerModal
        visible={themeModalVisible}
        onClose={() => setThemeModalVisible(false)}
        title={t('profile.theme', 'اختيار المظهر')}
        options={[
          { key: 'system', label: t('profile.theme_system', 'System'), icon: 'phone-portrait-outline' },
          { key: 'light', label: t('profile.theme_light', 'Light'), icon: 'sunny-outline' },
          { key: 'dark', label: t('profile.theme_dark', 'Dark'), icon: 'moon-outline' },
        ]}
        selectedKey={themeMode}
        onSelect={(key) => setMode(key as ThemeMode)}
        heightPercent="40%"
      />

      {/* ════════ MODAL: Privacy Policy ════════ */}
      <LegalModal
        visible={privacyModalVisible}
        onClose={() => setPrivacyModalVisible(false)}
        title={t('profile.privacy_policy', 'سياسة الخصوصية')}
        content={isAr ? PRIVACY_POLICY_AR : PRIVACY_POLICY_EN}
      />

      {/* ════════ MODAL: Terms of Service ════════ */}
      <LegalModal
        visible={termsModalVisible}
        onClose={() => setTermsModalVisible(false)}
        title={t('profile.terms_of_service', 'شروط الخدمة')}
        content={isAr ? TERMS_OF_SERVICE_AR : TERMS_OF_SERVICE_EN}
      />

      {/* ════════ MODAL: Store Status & Quick Stats ════════ */}
      <Modal
        visible={analyticsVisible}
        animationType="slide"
        onRequestClose={() => setAnalyticsVisible(false)}
      >
        <SafeAreaView style={styles.analyticsModalContainer} edges={['top']}>
          {/* Header */}
          <View style={styles.analyticsModalHeader}>
            <Text style={styles.analyticsModalTitle}>{t('merchant.store_status', 'Store Status')}</Text>
            <TouchableOpacity onPress={() => setAnalyticsVisible(false)} style={styles.modalCloseBtn}>
              <Ionicons name="close" size={24} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>

          <ScrollView contentContainerStyle={styles.analyticsModalScroll}>

            {/* Card 1: Store Open/Closed */}
            {market && (
              <View style={styles.statusCardContainer}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, flex: 1 }}>
                    <View style={[styles.statusDot, { backgroundColor: market.is_currently_open ? Colors.success : Colors.error }]} />
                    <View>
                      <Text style={styles.statusCardTitle}>
                        {market.is_currently_open ? t('common.open') : t('common.closed')}
                      </Text>
                      <Text style={styles.statusCardSubtitle}>
                        {market.is_manual_override
                          ? t('common.manual_override', 'Manual override')
                          : t('common.automatic_schedule', 'Automatic (schedule)')}
                      </Text>
                    </View>
                  </View>
                  <Switch
                    value={market.is_currently_open}
                    onValueChange={async (value) => {
                      try {
                        await updateStatusMutation.mutateAsync({ isOpen: value, isManual: true });
                      } catch (err) {
                        Alert.alert(t('common.error'), t('merchant.status_failed', 'Failed to update store status'));
                      }
                    }}
                    trackColor={{ false: '#444466', true: Colors.primaryDark }}
                    thumbColor={market.is_currently_open ? Colors.success : Colors.textMuted}
                  />
                </View>
                {market.is_manual_override && (
                  <TouchableOpacity
                    style={{ marginTop: Spacing.md, paddingTop: Spacing.sm, borderTopWidth: 1, borderColor: Colors.border }}
                    onPress={async () => {
                      try {
                        await updateStatusMutation.mutateAsync({ isOpen: null, isManual: false });
                      } catch (err) {
                        Alert.alert(t('common.error'), t('merchant.status_failed', 'Failed to update store status'));
                      }
                    }}
                  >
                    <Text style={{ ...Typography.caption, color: Colors.primary, textAlign: 'center' }}>
                      {t('merchant.revert_auto', 'Return to automatic schedule')}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            )}

            {/* Card 2: Inventory Value */}
            <View style={styles.assetsGlowCard}>
              <View style={styles.assetsGlowInner}>
                <View style={styles.assetsIconWrapper}>
                  <Ionicons name="cube-outline" size={22} color={Colors.primary} />
                </View>
                <View style={styles.assetsTextWrapper}>
                  <Text style={styles.assetsLabel}>{t('merchant.inventory_value', 'Inventory Value')}</Text>
                  <Text style={styles.assetsValue}>{formatPrice(totalAssetsValue)}</Text>
                </View>
              </View>
            </View>

            {/* Card 3: Today's Sales */}
            <View style={styles.assetsGlowCard}>
              <View style={styles.assetsGlowInner}>
                <View style={[styles.assetsIconWrapper, { backgroundColor: 'rgba(0, 217, 126, 0.12)' }]}>
                  <Ionicons name="cash-outline" size={22} color={Colors.success} />
                </View>
                <View style={styles.assetsTextWrapper}>
                  <Text style={styles.assetsLabel}>{t('merchant.todays_sales', "Today's Sales")}</Text>
                  <Text style={styles.assetsValue}>{formatPrice(stats.todaySales)}</Text>
                  <Text style={{ ...Typography.caption, color: Colors.textMuted, marginTop: 2 }}>
                    {stats.todayTxCount} {t('merchant.transactions', 'transactions')}
                  </Text>
                </View>
              </View>
            </View>

          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}