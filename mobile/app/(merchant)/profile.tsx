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
  getUser, getMyMarket, logout, MarketResponse,
  getInventoryValue, getCheckoutHistory, getMarketItems, updateMarketStatus,
  HistoricalReceipt,
  getMarketProfile, updateMarketProfile, updateEmployees,
  MarketProfileResponse, MarketProfileUpdatePayload
} from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useTheme, useThemeColors, ThemeMode } from '../../context/ThemeContext';
import { t, i18n, changeLanguage } from '../../services/i18n';
import { formatPrice } from '../../services/currency';
import Constants from 'expo-constants';

// ── Privacy Policy & Terms Content ────────────────────────────
const PRIVACY_POLICY_EN = `Privacy Policy — Lamba App

Last updated: August 2026

1. Information We Collect
We collect the following information when you use the Lamba app:
- Account information: name, phone number, email
- Location: to show nearby stores and products
- Search history: to improve results and provide better suggestions
- Messages: conversations between you and stores

2. How We Use Your Information
- Display products and services near your location
- Improve search results based on your preferences
- Send notifications when products you requested become available
- Enable communication between buyers and sellers

3. Information Sharing
We do not sell your personal information to third parties. We may share:
- Your approximate location with stores to calculate distance
- Your contact information with stores you communicate with

4. Data Protection
We use SSL/TLS encryption to protect your data during transit and store passwords in encrypted form.

5. Your Rights
At any time, you can:
- Request deletion of your account and data
- Edit your personal information
- Disable availability notifications

6. Contact Us
For privacy inquiries: privacy@lamba.app`;

const PRIVACY_POLICY_AR = `سياسة الخصوصية - تطبيق لمبة

آخر تحديث: أغسطس ٢٠٢٦

١. المعلومات التي نجمعها
نجمع المعلومات التالية عند استخدامك لتطبيق لمبة:
- معلومات الحساب: الاسم، رقم الهاتف، البريد الإلكتروني
- الموقع الجغرافي: لعرض المتاجر والمنتجات القريبة منك
- سجل البحث: لتحسين نتائج البحث وتقديم اقتراحات أفضل
- الرسائل: المحادثات بينك وبين المتاجر

٢. كيف نستخدم معلوماتك
- عرض المنتجات والخدمات القريبة من موقعك
- تحسين نتائج البحث بناءً على تفضيلاتك
- إرسال إشعارات عند توفر منتجات طلبتها
- تمكين التواصل بين المشترين والبائعين

٣. مشاركة المعلومات
لا نبيع معلوماتك الشخصية لأطراف ثالثة. قد نشارك:
- موقعك التقريبي مع المتاجر لحساب المسافة
- معلومات الاتصال مع المتاجر التي تتواصل معها

٤. حماية البيانات
نستخدم تشفير SSL/TLS لحماية بياناتك أثناء النقل وتخزين كلمات المرور بشكل مشفر.

٥. حقوقك
يمكنك في أي وقت:
- طلب حذف حسابك وبياناتك
- تعديل معلوماتك الشخصية
- إيقاف إشعارات التوفر

٦. التواصل معنا
للاستفسارات حول الخصوصية: privacy@lamba.app`;

const TERMS_OF_SERVICE_EN = `Terms of Service — Lamba App

Last updated: August 2026

1. Acceptance of Terms
By using the Lamba app, you agree to these terms.

2. Service Description
Lamba is a platform that connects buyers with local stores and service providers. We do not sell products directly — we provide a search and communication tool.

3. User Accounts
- Information provided must be accurate
- You are responsible for maintaining the confidentiality of your account
- You must be 16 years or older

4. Seller Responsibilities
- Product information and prices displayed are the seller's responsibility
- Products and services offered must be legal
- Lamba is not responsible for the quality of products or services

5. Acceptable Use
Prohibited:
- Posting offensive or illegal content
- Using the app for fraud
- Collecting other users' data

6. Disclaimer
Lamba is an intermediary platform. We do not guarantee the accuracy of information provided by sellers and are not liable for any transactions between buyers and sellers.

7. Modifications
We reserve the right to modify these terms. You will be notified of any material changes.

8. Contact
support@lamba.app`;

const TERMS_OF_SERVICE_AR = `شروط الخدمة - تطبيق لمبة

آخر تحديث: أغسطس ٢٠٢٦

١. القبول بالشروط
باستخدامك لتطبيق لمبة، فإنك توافق على هذه الشروط.

٢. وصف الخدمة
لمبة منصة تربط المشترين بالمتاجر ومقدمي الخدمات المحلية. نحن لا نبيع منتجات مباشرة — نحن نوفر أداة البحث والتواصل.

٣. حسابات المستخدمين
- يجب أن تكون المعلومات المقدمة صحيحة
- أنت مسؤول عن الحفاظ على سرية حسابك
- يجب أن يكون عمرك ١٦ سنة أو أكثر

٤. مسؤوليات البائعين
- المعلومات والأسعار المعروضة هي مسؤولية البائع
- يجب أن تكون المنتجات والخدمات المعروضة قانونية
- لمبة غير مسؤولة عن جودة المنتجات أو الخدمات

٥. الاستخدام المقبول
يُحظر:
- نشر محتوى مسيء أو غير قانوني
- استخدام التطبيق للاحتيال
- جمع بيانات المستخدمين الآخرين

٦. إخلاء المسؤولية
لمبة منصة وسيطة. لا نضمن دقة المعلومات المقدمة من البائعين ولا نتحمل مسؤولية أي معاملات بين المشترين والبائعين.

٧. التعديلات
نحتفظ بحق تعديل هذه الشروط. سيتم إشعارك بأي تغييرات جوهرية.

٨. التواصل
support@lamba.app`;

// ── Sub-components for Grouped Layout ─────────────────────────
const SectionHeader = ({ title }: { title: string }) => {
  const Colors = useThemeColors();
  const isAr = i18n.locale.includes('ar');
  return (
    <Text style={{
      color: Colors.textMuted,
      fontSize: 12,
      fontWeight: '600',
      textAlign: isAr ? 'right' : 'left',
      paddingHorizontal: 20,
      paddingTop: 24,
      paddingBottom: 8,
      letterSpacing: 0.5,
      textTransform: 'uppercase',
    }}>
      {title}
    </Text>
  );
};

const Divider = () => {
  const Colors = useThemeColors();
  return (
    <View style={{
      height: 0.5,
      backgroundColor: Colors.border,
      marginHorizontal: 20,
    }} />
  );
};

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
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [loadingMarket, setLoadingMarket] = useState(true);
  const isAr = i18n.locale.includes('ar');

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
  const [newEmployeeName, setNewEmployeeName] = useState('');
  const [savingEmployees, setSavingEmployees] = useState(false);

  // Relocated Analytics & Status States
  const [analyticsVisible, setAnalyticsVisible] = useState(false);
  const [totalAssetsValue, setTotalAssetsValue] = useState<number>(0);
  const [historyReceipts, setHistoryReceipts] = useState<HistoricalReceipt[]>([]);
  const [totalProducts, setTotalProducts] = useState<number>(0);
  const [inStockCount, setInStockCount] = useState<number>(0);
  const [loadingStats, setLoadingStats] = useState(false);
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

  const loadAnalyticsData = useCallback(async () => {
    try {
      setLoadingStats(true);
      const freshMarket = await getMyMarket();
      setMarket(freshMarket);

      try {
        const valResp = await getInventoryValue();
        setTotalAssetsValue(valResp.total_value);
      } catch (valErr) {
        console.warn('Failed to load inventory valuation in profile:', valErr);
      }

      try {
        const historyData = await getCheckoutHistory();
        setHistoryReceipts(historyData);
      } catch (histErr) {
        console.warn('Failed to load transaction history in profile:', histErr);
      }

      try {
        const items = await getMarketItems();
        setTotalProducts(items.length);
        setInStockCount(items.filter((p: any) => p.in_stock).length);
      } catch (itemsErr) {
        console.warn('Failed to load products list count in profile:', itemsErr);
      }
    } catch (err) {
      console.warn('Failed to load analytics in profile:', err);
    } finally {
      setLoadingStats(false);
      setRefreshingStats(false);
    }
  }, []);

  useEffect(() => {
    if (analyticsVisible) {
      loadAnalyticsData();
    }
  }, [analyticsVisible, loadAnalyticsData]);

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

      try {
        const marketData = await getMyMarket();
        setMarket(marketData);
      } catch {
        // No market set up yet
      } finally {
        setLoadingMarket(false);
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
      const freshMarket = await getMyMarket();
      setMarket(freshMarket);

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

  // Employee Add Handler
  const handleAddEmployee = async () => {
    const trimmed = newEmployeeName.trim();
    if (!trimmed) {
      Alert.alert(
        isAr ? 'تنبيه' : 'Alert',
        isAr ? 'يرجى إدخال اسم الموظف' : 'Please enter employee name'
      );
      return;
    }
    const updated = [...employeeList, trimmed];
    setEmployeeList(updated);
    setNewEmployeeName('');
    setSavingEmployees(true);
    try {
      const res = await updateEmployees(updated);
      setProfileData(res);
      setEmployeeList(res.employees || updated);
    } catch (err: any) {
      Alert.alert(
        t('common.error', 'خطأ'),
        isAr ? 'فشل إضافة الموظف' : 'Failed to add employee'
      );
      setEmployeeList(profileData?.employees || []);
    } finally {
      setSavingEmployees(false);
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
    // Modals styling (shared)
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
    fullScreenModalContainer: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    modalHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: Spacing.xl,
      borderBottomWidth: 1,
      borderColor: Colors.border,
    },
    modalTitle: {
      ...Typography.h2,
      color: Colors.textPrimary,
    },
    closeBtn: {
      padding: Spacing.xs,
    },
    legalBody: {
      padding: Spacing.xl,
      paddingBottom: Spacing.xxxl,
    },
    legalText: {
      ...Typography.body,
      color: Colors.textSecondary,
      lineHeight: 22,
    },
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

    // Employees modal styles
    employeeAddRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.sm,
      padding: Spacing.xl,
      borderBottomWidth: 1,
      borderColor: Colors.border,
    },
    employeeInput: {
      flex: 1,
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.lg,
      paddingHorizontal: Spacing.lg,
      paddingVertical: 12,
      color: Colors.textPrimary,
      fontSize: 15,
      borderWidth: 1,
      borderColor: Colors.border,
      textAlign: isAr ? 'right' : 'left',
    },
    employeeAddBtn: {
      width: 44,
      height: 44,
      borderRadius: 22,
      backgroundColor: Colors.secondary,
      justifyContent: 'center',
      alignItems: 'center',
    },
    employeeList: {
      padding: Spacing.xl,
    },
    employeeItem: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.lg,
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.lg,
      marginBottom: Spacing.sm,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    employeeItemInner: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.md,
      flex: 1,
    },
    employeeAvatarBox: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: 'rgba(0, 217, 166, 0.12)',
      justifyContent: 'center',
      alignItems: 'center',
    },
    employeeNameText: {
      ...Typography.body,
      color: Colors.textPrimary,
      fontWeight: '600',
    },
    employeeDeleteBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: 'rgba(255, 77, 106, 0.1)',
      justifyContent: 'center',
      alignItems: 'center',
    },
    emptyEmployees: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: 60,
      gap: Spacing.sm,
    },
    emptyEmployeesText: {
      ...Typography.body,
      color: Colors.textMuted,
    },

    // Analytics Modal Specific
    analyticsModalContainer: {
      flex: 1,
      backgroundColor: Colors.background,
    },
    analyticsModalScroll: {
      paddingBottom: Spacing.xxxl,
    },
    analyticsModalHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.lg,
      borderBottomWidth: 1,
      borderColor: Colors.border,
      marginBottom: Spacing.xl,
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
      marginHorizontal: Spacing.xl,
      marginBottom: Spacing.lg,
      borderWidth: 1,
      borderColor: Colors.border,
      ...Shadows.small,
    },
    statusCardHeader: {
      marginBottom: Spacing.md,
    },
    statusCardTitleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.sm,
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
    segmentedContainer: {
      flexDirection: 'row',
      backgroundColor: Colors.surfaceElevated,
      borderRadius: BorderRadius.md,
      padding: 2,
      gap: 2,
    },
    segmentBtn: {
      flex: 1,
      paddingVertical: Spacing.sm,
      alignItems: 'center',
      borderRadius: BorderRadius.md - 2,
    },
    segmentBtnActive: {
      backgroundColor: Colors.surface,
      ...Shadows.small,
    },
    segmentText: {
      ...Typography.caption,
      color: Colors.textSecondary,
      fontWeight: '600',
    },
    segmentTextActive: {
      color: Colors.primary,
      fontWeight: '700',
    },
    manualSwitchRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginTop: Spacing.md,
      paddingTop: Spacing.sm,
      borderTopWidth: 1,
      borderColor: Colors.border,
    },
    manualSwitchLabel: {
      ...Typography.caption,
      color: Colors.textSecondary,
    },
    statusDot: {
      width: 10,
      height: 10,
      borderRadius: 5,
    },
    assetsGlowCard: {
      marginHorizontal: Spacing.xl,
      marginBottom: Spacing.lg,
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
    lowStockWarningCard: {
      marginHorizontal: Spacing.xl,
      marginBottom: Spacing.lg,
      borderRadius: BorderRadius.xl,
      overflow: 'hidden',
      borderWidth: 1,
      borderColor: Colors.errorBorder,
      backgroundColor: Colors.surface,
      ...Shadows.small,
    },
    lowStockInner: {
      flexDirection: 'row',
      padding: Spacing.lg,
      alignItems: 'center',
      gap: Spacing.md,
    },
    lowStockIconWrapper: {
      width: 40,
      height: 40,
      borderRadius: 12,
      backgroundColor: Colors.errorBg,
      justifyContent: 'center',
      alignItems: 'center',
    },
    lowStockTextWrapper: {
      flex: 1,
    },
    lowStockLabel: {
      fontSize: 14,
      color: Colors.error,
      fontWeight: '700',
    },
    lowStockSubText: {
      fontSize: 12,
      color: Colors.textSecondary,
      fontWeight: '400',
      marginTop: 2,
    },
    analyticsCard: {
      marginHorizontal: Spacing.xl,
      marginBottom: Spacing.lg,
      borderRadius: BorderRadius.xl,
      borderWidth: 1,
      borderColor: Colors.border,
      backgroundColor: Colors.surface,
      padding: Spacing.lg,
      ...Shadows.small,
    },
    analyticsHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.sm,
      marginBottom: Spacing.sm,
    },
    analyticsTitle: {
      ...Typography.body,
      fontWeight: '700',
      color: Colors.textPrimary,
    },
    analyticsDivider: {
      height: 1,
      backgroundColor: Colors.border,
      marginBottom: Spacing.md,
    },
    trendRows: {
      gap: Spacing.sm,
      marginBottom: Spacing.md,
    },
    trendRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    trendLabelCol: {
      flex: 1,
    },
    trendLabel: {
      ...Typography.caption,
      color: Colors.textMuted,
      fontWeight: '700',
      letterSpacing: 0.5,
    },
    trendVal: {
      ...Typography.body,
      fontWeight: '700',
      color: Colors.textPrimary,
      marginTop: 2,
    },
    trendBadge: {
      flexDirection: 'row',
      borderRadius: BorderRadius.sm,
      paddingHorizontal: 8,
      paddingVertical: 4,
      alignItems: 'center',
      gap: 4,
      borderWidth: 1,
    },
    trendBadgeUp: {
      backgroundColor: 'rgba(0, 217, 126, 0.08)',
      borderColor: 'rgba(0, 217, 126, 0.25)',
    },
    trendBadgeDown: {
      backgroundColor: 'rgba(255, 77, 106, 0.08)',
      borderColor: 'rgba(255, 77, 106, 0.25)',
    },
    trendBadgeText: {
      fontSize: 11,
      fontWeight: '700',
    },
    trendRowDivider: {
      height: 1,
      backgroundColor: 'rgba(255, 255, 255, 0.02)',
    },
    insightsBox: {
      backgroundColor: 'rgba(108, 99, 255, 0.05)',
      borderRadius: BorderRadius.md,
      borderWidth: 1,
      borderColor: 'rgba(108, 99, 255, 0.15)',
      padding: Spacing.md,
      marginTop: Spacing.xs,
    },
    insightsHeaderRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginBottom: 6,
    },
    insightsHeaderTitle: {
      fontSize: 10,
      fontWeight: '800',
      color: Colors.primary,
      letterSpacing: 0.5,
    },
    insightsBodyText: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      lineHeight: 18,
    },
    statsRow: {
      flexDirection: 'row',
      paddingHorizontal: Spacing.xl,
      gap: Spacing.sm,
      marginBottom: Spacing.lg,
    },
    statCard: {
      flex: 1,
      backgroundColor: Colors.surface,
      borderRadius: BorderRadius.xl,
      paddingVertical: Spacing.md,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: Colors.border,
      ...Shadows.small,
    },
    statNumber: {
      ...Typography.h2,
      color: Colors.textPrimary,
    },
    statLabel: {
      ...Typography.caption,
      color: Colors.textMuted,
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

        {/* === Section: متجري (Store Info) === */}
        <SectionHeader title={t('merchant.my_store', 'متجري')} />
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
              <Divider />

              {/* Row 6 — Analytics */}
              <MenuRow
                icon="bar-chart-outline"
                iconColor={Colors.secondary}
                iconBgColor="rgba(0, 217, 166, 0.12)"
                label={t('merchant.analytics_status', 'إحصائيات وحالة المتجر')}
                subtitle={isAr ? 'تتبع المبيعات وقيمة المخزون وحالة المتجر' : 'Track sales, inventory valuation & status'}
                onPress={() => setAnalyticsVisible(true)}
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

        {/* === Section: التطبيق (App Settings) === */}
        <SectionHeader title={t('profile.app_section', 'التطبيق')} />
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
                ? (isAr ? 'داكن' : 'Dark')
                : themeMode === 'light'
                ? (isAr ? 'فاتح' : 'Light')
                : (isAr ? 'تلقائي' : 'Auto')
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
        <SectionHeader title={t('profile.info_section', 'معلومات')} />
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
          لمبة v{appVersion} · محلي وآمن
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
      <Modal visible={employeesModalVisible} animationType="slide" onRequestClose={() => setEmployeesModalVisible(false)}>
        <SafeAreaView style={styles.fullScreenModalContainer} edges={['top']}>
          {/* Modal Header */}
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{t('merchant.employees', isAr ? 'الموظفون' : 'Employees')}</Text>
            <TouchableOpacity onPress={() => setEmployeesModalVisible(false)} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>

          {/* Mandatory notice */}
          <View style={{ paddingHorizontal: 16, paddingTop: 4, paddingBottom: 10 }}>
            <Text style={{ color: Colors.textMuted, fontSize: 13, textAlign: isAr ? 'right' : 'left' }}>
              {isAr ? '⚠️ يجب إضافة موظف واحد على الأقل للمتجر' : '⚠️ At least one employee is required for the store'}
            </Text>
          </View>

          {/* Add Employee Input Row */}
          <View style={styles.employeeAddRow}>
            <TextInput
              style={styles.employeeInput}
              value={newEmployeeName}
              onChangeText={setNewEmployeeName}
              placeholder={isAr ? 'أدخل اسم الموظف الجديد' : 'Enter new employee name'}
              placeholderTextColor={Colors.textMuted}
              returnKeyType="done"
              onSubmitEditing={handleAddEmployee}
            />
            <TouchableOpacity
              style={styles.employeeAddBtn}
              onPress={handleAddEmployee}
              disabled={savingEmployees || !newEmployeeName.trim()}
              activeOpacity={0.8}
            >
              {savingEmployees ? (
                <ActivityIndicator size="small" color="#000" />
              ) : (
                <Ionicons name="add" size={24} color="#000" />
              )}
            </TouchableOpacity>
          </View>

          {/* Employees List */}
          <FlatList
            data={employeeList}
            keyExtractor={(_, index) => index.toString()}
            contentContainerStyle={styles.employeeList}
            renderItem={({ item, index }) => (
              <View style={styles.employeeItem}>
                <View style={styles.employeeItemInner}>
                  <View style={styles.employeeAvatarBox}>
                    <Ionicons name="person" size={18} color={Colors.secondary} />
                  </View>
                  <Text style={styles.employeeNameText}>{item}</Text>
                </View>
                <TouchableOpacity
                  style={styles.employeeDeleteBtn}
                  onPress={() => handleDeleteEmployee(index)}
                  activeOpacity={0.7}
                >
                  <Ionicons name="trash-outline" size={18} color={Colors.error} />
                </TouchableOpacity>
              </View>
            )}
            ListEmptyComponent={
              <View style={styles.emptyEmployees}>
                <Ionicons name="people-outline" size={48} color={Colors.warning} />
                <Text style={[styles.emptyEmployeesText, { color: Colors.warning, fontWeight: '700', marginTop: 8 }]}>
                  {isAr ? 'مطلوب إضافة موظف واحد على الأقل' : 'At least one employee is required'}
                </Text>
                <Text style={{ color: Colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: 4, paddingHorizontal: 20 }}>
                  {isAr ? 'أدخل اسم الموظف في الحقل أعلاه واضغط على زر الإضافة (+)' : 'Enter employee name in the field above and tap (+)'}
                </Text>
              </View>
            }
          />
        </SafeAreaView>
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
                  system: isAr ? 'تلقائي (حسب النظام)' : 'System Default',
                  light: isAr ? 'فاتح' : 'Light',
                  dark: isAr ? 'داكن' : 'Dark',
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

      {/* ════════ MODAL: Analytics & Store Status ════════ */}
      <Modal
        visible={analyticsVisible}
        animationType="slide"
        onRequestClose={() => setAnalyticsVisible(false)}
      >
        <SafeAreaView style={styles.analyticsModalContainer} edges={['top']}>
          {/* Modal Header */}
          <View style={styles.analyticsModalHeader}>
            <Text style={styles.analyticsModalTitle}>{t('merchant.analytics_status', 'Store Analytics & Status')}</Text>
            <TouchableOpacity 
              onPress={() => setAnalyticsVisible(false)}
              style={styles.modalCloseBtn}
            >
              <Ionicons name="close" size={24} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>

          {loadingStats && !refreshingStats ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={Colors.secondary} />
              <Text style={styles.loadingText}>{t('common.loading', 'Loading analytics...')}</Text>
            </View>
          ) : (
            <ScrollView
              contentContainerStyle={styles.analyticsModalScroll}
              refreshControl={
                <RefreshControl
                  refreshing={refreshingStats}
                  onRefresh={() => {
                    setRefreshingStats(true);
                    loadAnalyticsData();
                  }}
                  tintColor={Colors.secondary}
                />
              }
            >
              {/* Store Status Control Card */}
              {market && (
                <View style={styles.statusCardContainer}>
                  <View style={styles.statusCardHeader}>
                    <View style={styles.statusCardTitleRow}>
                      <View style={[styles.statusDot, { backgroundColor: market.is_currently_open ? Colors.success : Colors.error }]} />
                      <Text style={styles.statusCardTitle}>
                        {t('common.store_status')}: <Text style={[styles.statusCardValue, { color: market.is_currently_open ? Colors.success : Colors.error }]}>
                          {market.is_currently_open ? t('common.open') : t('common.closed')}
                        </Text>
                      </Text>
                    </View>
                    <Text style={styles.statusCardSubtitle}>
                      {market.is_manual_override ? t('common.manual_override') : t('common.automatic_schedule')}
                    </Text>
                  </View>

                  {/* Mode Selector Segmented Control */}
                  <View style={styles.segmentedContainer}>
                    <TouchableOpacity
                      style={[styles.segmentBtn, !market.is_manual_override && styles.segmentBtnActive]}
                      onPress={async () => {
                        try {
                          const updated = await updateMarketStatus(null, false);
                          setMarket(updated);
                        } catch (err) {
                          Alert.alert(t('common.error'), isAr ? 'فشل تحويل المتجر إلى الوضع التلقائي' : 'Failed to set store to automatic mode');
                        }
                      }}
                    >
                      <Text style={[styles.segmentText, !market.is_manual_override && styles.segmentTextActive]}>
                        {t('common.automatic_schedule')}
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={[styles.segmentBtn, market.is_manual_override && styles.segmentBtnActive]}
                      onPress={async () => {
                        try {
                          const updated = await updateMarketStatus(market.is_currently_open, true);
                          setMarket(updated);
                        } catch (err) {
                          Alert.alert(t('common.error'), isAr ? 'فشل تحويل المتجر إلى وضع التجاوز اليدوي' : 'Failed to set store to manual override mode');
                        }
                      }}
                    >
                      <Text style={[styles.segmentText, market.is_manual_override && styles.segmentTextActive]}>
                        {t('common.manual_override')}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {/* Manual Switch */}
                  {market.is_manual_override && (
                    <View style={styles.manualSwitchRow}>
                      <Text style={styles.manualSwitchLabel}>{t('common.reverts_at_midnight')}</Text>
                      <Switch
                        value={market.is_currently_open}
                        onValueChange={async (value) => {
                          try {
                            const updated = await updateMarketStatus(value, true);
                            setMarket(updated);
                          } catch (err) {
                            Alert.alert(t('common.error'), isAr ? 'فشل تغيير حالة المتجر' : 'Failed to override store status');
                          }
                        }}
                        trackColor={{ false: '#444466', true: Colors.primaryDark }}
                        thumbColor={market.is_currently_open ? Colors.success : Colors.textMuted}
                      />
                    </View>
                  )}
                </View>
              )}

              {/* Inventory Assets Value Glow Card */}
              {market && (
                <View style={styles.assetsGlowCard}>
                  <View style={styles.assetsGlowInner}>
                    <View style={styles.assetsIconWrapper}>
                      <Ionicons name="calculator-outline" size={22} color={Colors.primary} />
                    </View>
                    <View style={styles.assetsTextWrapper}>
                      <Text style={styles.assetsLabel}>{t('dashboard.inventory_value', 'إجمالي قيمة أصول المخزون')}</Text>
                      <Text style={styles.assetsValue}>
                        {formatPrice(totalAssetsValue)}
                      </Text>
                    </View>
                  </View>
                </View>
              )}

              {/* Sales Performance Card */}
              {market && (
                <View style={styles.analyticsCard}>
                  <View style={styles.analyticsHeader}>
                    <Ionicons name="trending-up-outline" size={20} color={Colors.secondary} />
                    <Text style={styles.analyticsTitle}>
                      {t('dashboard.sales_performance', 'أداء المبيعات والتحليلات اليومية')}
                    </Text>
                  </View>
                  
                  <View style={styles.analyticsDivider} />

                  <View style={styles.trendRows}>
                    {/* Daily Trend */}
                    <View style={styles.trendRow}>
                      <View style={styles.trendLabelCol}>
                        <Text style={styles.trendLabel}>{t('dashboard.todays_sales', 'مبيعات اليوم')}</Text>
                        <Text style={styles.trendVal}>{formatPrice(stats.todaySales)}</Text>
                      </View>
                      
                      <View style={[styles.trendBadge, stats.todaySales >= stats.yesterdaySales ? styles.trendBadgeUp : styles.trendBadgeDown]}>
                        <Ionicons 
                          name={stats.todaySales >= stats.yesterdaySales ? 'trending-up' : 'trending-down'} 
                          size={14} 
                          color={stats.todaySales >= stats.yesterdaySales ? Colors.success : Colors.error} 
                        />
                        <Text style={[styles.trendBadgeText, { color: stats.todaySales >= stats.yesterdaySales ? Colors.success : Colors.error }]}>
                          {stats.todaySales >= stats.yesterdaySales ? '+' : ''}{stats.dailyChange.toFixed(1)}%
                        </Text>
                      </View>
                    </View>

                    <View style={styles.trendRowDivider} />

                    {/* Weekly Trend */}
                    <View style={styles.trendRow}>
                      <View style={styles.trendLabelCol}>
                        <Text style={styles.trendLabel}>{t('dashboard.this_weeks_sales', 'مبيعات هذا الأسبوع')}</Text>
                        <Text style={styles.trendVal}>{formatPrice(stats.thisWeekSales)}</Text>
                      </View>
                      
                      <View style={[styles.trendBadge, stats.thisWeekSales >= stats.lastWeekSales ? styles.trendBadgeUp : styles.trendBadgeDown]}>
                        <Ionicons 
                          name={stats.thisWeekSales >= stats.lastWeekSales ? 'trending-up' : 'trending-down'} 
                          size={14} 
                          color={stats.thisWeekSales >= stats.lastWeekSales ? Colors.success : Colors.error} 
                        />
                        <Text style={[styles.trendBadgeText, { color: stats.thisWeekSales >= stats.lastWeekSales ? Colors.success : Colors.error }]}>
                          {stats.thisWeekSales >= stats.lastWeekSales ? '+' : ''}{stats.weeklyChange.toFixed(1)}%
                        </Text>
                      </View>
                    </View>
                  </View>

                  {/* Daily Dynamic Analysis Insights box */}
                  <View style={styles.insightsBox}>
                    <View style={styles.insightsHeaderRow}>
                      <Ionicons name="sparkles-outline" size={16} color={Colors.primary} />
                      <Text style={styles.insightsHeaderTitle}>
                        {t('dashboard.daily_summary_analysis', 'تحليل الملخص اليومي')}
                      </Text>
                    </View>
                    <Text style={styles.insightsBodyText}>
                      {stats.summaryAnalysis}
                    </Text>
                  </View>
                </View>
              )}

              {/* Stats Summary cards */}
              <View style={styles.statsRow}>
                <View style={styles.statCard}>
                  <Text style={[styles.statNumber, { color: Colors.secondary }]}>{market ? 1 : 0}</Text>
                  <Text style={styles.statLabel}>{t('dashboard.store_active', 'المتجر نشط')}</Text>
                </View>
                
                <View style={styles.statCard}>
                  <Text style={styles.statNumber}>{totalProducts}</Text>
                  <Text style={styles.statLabel}>{t('dashboard.catalog_items', 'عناصر الكتالوج')}</Text>
                </View>
                
                <View style={[styles.statCard, { borderColor: Colors.success }]}>
                  <Text style={[styles.statNumber, { color: Colors.success }]}>{inStockCount}</Text>
                  <Text style={styles.statLabel}>{t('dashboard.in_stock', 'متوفر')}</Text>
                </View>
              </View>

              {/* Deficiencies Warnings (Low Stock Button) */}
              <TouchableOpacity
                style={styles.lowStockWarningCard}
                onPress={() => {
                  setAnalyticsVisible(false);
                  router.push('/(merchant)/low-stock');
                }}
                activeOpacity={0.8}
              >
                <View style={styles.lowStockInner}>
                  <View style={styles.lowStockIconWrapper}>
                    <Ionicons name="warning-outline" size={20} color={Colors.error} />
                  </View>
                  <View style={styles.lowStockTextWrapper}>
                    <Text style={styles.lowStockLabel}>
                      {t('lowStock.title', 'تنبيهات نقص المخزون')}
                    </Text>
                    <Text style={styles.lowStockSubText}>
                      {t('merchant.low_stock_manage', 'اضغط لإدارة المنتجات التي أوشكت على النفاد')}
                    </Text>
                  </View>
                  <Ionicons name={isAr ? "chevron-back" : "chevron-forward"} size={16} color={Colors.textSecondary} />
                </View>
              </TouchableOpacity>

            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}