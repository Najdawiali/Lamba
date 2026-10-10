/**
 * Market Profile Onboarding Screen — Setup store parameters.
 * Captures name, store type, location (pin on the map + governorate / area / street / landmark,
 * see components/StoreLocationForm) and operating hours.
 */

import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
  ScrollView,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { createMarket } from '../../services/api';
import { Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { useThemeColors } from '../../context/ThemeContext';
import { t, i18n } from '../../services/i18n';
import { messageFromError } from '../../utils/serverMessage';
import KeyboardForm from '../../components/KeyboardForm';
import StoreLocationForm from '../../components/StoreLocationForm';
import { EMPTY_LOCATION, locationProblems, toLocationPayload, type LocationProblem, type StoreLocationValue } from '../../utils/jordanAddress';

const BUSINESS_CATEGORIES = [
  {
    group: { en: 'Food & Grocery', ar: 'أغذية وبقالة' },
    types: [
      { en: 'Supermarket / Grocery', ar: 'سوبرماركت / بقالة' },
      { en: 'Bakery & Pastries', ar: 'مخبز ومعجنات' },
      { en: 'Butcher Shop', ar: 'ملحمة' },
      { en: 'Fruits & Vegetables', ar: 'خضار وفواكه' },
      { en: 'Nuts & Spices', ar: 'محمصة ومكسرات وبهارات' },
      { en: 'Dairy & Cheese', ar: 'ألبان وأجبان' },
      { en: 'Sweets & Desserts', ar: 'حلويات' },
    ],
  },
  {
    group: { en: 'Food Service', ar: 'مطاعم وخدمات طعام' },
    types: [
      { en: 'Restaurant', ar: 'مطعم' },
      { en: 'Cafe / Coffee Shop', ar: 'مقهى / كوفي شوب' },
      { en: 'Juice Bar', ar: 'عصائر ومشروبات طازجة' },
      { en: 'Catering Service', ar: 'تموين وطبخ' },
    ],
  },
  {
    group: { en: 'Retail & Shopping', ar: 'تجارة وتسوق' },
    types: [
      { en: 'Clothing & Fashion', ar: 'ملابس وأزياء' },
      { en: 'Electronics & Phones', ar: 'إلكترونيات وهواتف' },
      { en: 'Cosmetics & Perfumes', ar: 'مستحضرات تجميل وعطور' },
      { en: 'Household & Home', ar: 'أدوات منزلية' },
      { en: 'Stationery & Office', ar: 'قرطاسية ومكتبات' },
      { en: 'General Store', ar: 'متجر عام' },
    ],
  },
  {
    group: { en: 'Services', ar: 'خدمات' },
    types: [
      { en: 'Barber / Salon', ar: 'حلاقة / صالون تجميل' },
      { en: 'Laundry & Dry Cleaning', ar: 'مغسلة ملابس' },
      { en: 'Auto Parts & Repair', ar: 'قطع غيار سيارات' },
      { en: 'Pharmacy', ar: 'صيدلية' },
      { en: 'Other Services', ar: 'خدمات أخرى' },
    ],
  },
];

export default function OnboardingScreen() {
  const router = useRouter();
  const Colors = useThemeColors();
  const isAr = i18n.locale.includes('ar');

  const [name, setName] = useState('');
  const [location, setLocation] = useState<StoreLocationValue>(EMPTY_LOCATION);
  const [problems, setProblems] = useState<LocationProblem[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [typeModalVisible, setTypeModalVisible] = useState(false);
  const [hoursPreset, setHoursPreset] = useState<'standard' | 'open_24_7' | 'weekdays'>('standard');

  const [loading, setLoading] = useState(false);

  // Build structured operating_hours based on selected preset.
  const buildOperatingHours = (): Record<string, string> | null => {
    if (hoursPreset === 'open_24_7') return null;
    if (hoursPreset === 'weekdays') return { 'Mon-Fri': '09:00-17:00', 'Sat-Sun': 'closed' };
    return { 'Sat-Thu': '08:00-22:00', Fri: '09:00-22:00' };
  };

  const handleInitialize = async () => {
    if (!name.trim()) {
      Alert.alert(t('common.error', 'Error'), t('onboarding.fill_all_fields', 'Please fill in all physical store fields'));
      return;
    }

    const found = locationProblems(location);
    const payload = toLocationPayload(location);
    if (found.length > 0 || !payload) {
      setProblems(found);
      Alert.alert(t('common.error', 'Error'), t(`storeLocation.problem_${found[0] ?? 'pin_missing'}`));
      return;
    }

    // Make sure the API gets the English label, regardless of display language
    const typeEntry = BUSINESS_CATEGORIES
      .flatMap(c => c.types)
      .find(item => item.en === selectedType || item.ar === selectedType);
    const businessNatureValue = typeEntry?.en || selectedType;

    setLoading(true);
    try {
      await createMarket(name.trim(), payload, {
        business_nature: businessNatureValue.trim() || undefined,
        operating_hours: buildOperatingHours(),
      });
      
      Alert.alert(
        t('common.success', 'Success'),
        t('onboarding.init_success', 'Your market has been successfully initialized! Welcome to your Dashboard.'),
        [
          {
            text: t('onboarding.lets_go', "Let's Go"),
            onPress: () => router.replace('/(merchant)/dashboard')
          }
        ]
      );
    } catch (err: any) {
      Alert.alert(
        t('onboarding.init_failed', 'Initialization Failed'),
        messageFromError(err, isAr, {
          network: t('login.network_error', "Couldn't reach the server. Check your internet connection and try again."),
          fallback: t('common.something_went_wrong', 'Something went wrong. Please try again.'),
        })
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
      paddingVertical: Spacing.xl,
    },
    glowOrb1: {
      position: 'absolute',
      top: '10%',
      left: '-20%',
      width: 300,
      height: 300,
      borderRadius: 150,
      backgroundColor: Colors.secondary,
      opacity: 0.05,
    },
    glowOrb2: {
      position: 'absolute',
      bottom: '10%',
      right: '-15%',
      width: 250,
      height: 250,
      borderRadius: 125,
      backgroundColor: Colors.primary,
      opacity: 0.04,
    },
    header: {
      alignItems: 'center',
      marginBottom: Spacing.xxl,
      marginTop: Spacing.xl,
    },
    iconContainer: {
      width: 80,
      height: 80,
      borderRadius: 40,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: Spacing.lg,
      ...Shadows.glow,
    },
    title: {
      ...Typography.h1,
      color: Colors.textPrimary,
      marginBottom: Spacing.xs,
    },
    subtitle: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      textAlign: 'center',
    },
    card: {
      backgroundColor: Colors.surfaceGlass,
      borderRadius: BorderRadius.xl,
      padding: Spacing.xl,
      borderWidth: 1,
      borderColor: Colors.border,
      ...Shadows.medium,
    },
    cardTitle: {
      ...Typography.h3,
      color: Colors.textPrimary,
      marginBottom: Spacing.xl,
      textAlign: 'center',
    },
    label: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      fontWeight: '600',
      marginBottom: Spacing.xs,
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
      marginRight: Spacing.sm,
    },
    input: {
      flex: 1,
      color: Colors.textPrimary,
      ...Typography.body,
    },
    selectButton: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      borderWidth: 1,
      borderRadius: BorderRadius.lg,
      paddingVertical: Spacing.lg,
      paddingHorizontal: Spacing.lg,
      marginBottom: Spacing.lg,
    },
    selectButtonText: {
      ...Typography.body,
      flex: 1,
    },
    presetLabel: {
      ...Typography.bodySmall,
      color: Colors.textSecondary,
      fontWeight: '700',
      marginTop: Spacing.sm,
      marginBottom: Spacing.xs,
    },
    presetRow: {
      flexDirection: 'row',
      gap: Spacing.sm,
      marginBottom: Spacing.xs,
    },
    presetBtn: {
      flex: 1,
      paddingVertical: Spacing.sm,
      borderRadius: BorderRadius.md,
      borderWidth: 1,
      borderColor: Colors.border,
      backgroundColor: Colors.surface,
      alignItems: 'center',
    },
    presetBtnActive: {
      borderColor: Colors.secondary,
      backgroundColor: 'rgba(0, 217, 166, 0.08)',
    },
    presetBtnText: {
      ...Typography.caption,
      color: Colors.textSecondary,
      fontWeight: '600',
    },
    presetBtnTextActive: {
      color: Colors.secondary,
      fontWeight: '700',
    },
    presetHint: {
      ...Typography.caption,
      color: Colors.textMuted,
      marginBottom: Spacing.md,
    },
    button: {
      backgroundColor: Colors.primary,
      borderRadius: BorderRadius.md,
      height: 52,
      justifyContent: 'center',
      alignItems: 'center',
      ...Shadows.small,
    },
    buttonDisabled: {
      opacity: 0.6,
    },
    buttonText: {
      ...Typography.button,
      color: Colors.textOnPrimary,
    },
  }), [Colors]);

  return (
    <View style={styles.container}>
      <KeyboardForm contentContainerStyle={styles.scroll}>
        {/* Glow Ambient */}
        <View style={styles.glowOrb1} />
        <View style={styles.glowOrb2} />

        <View style={styles.header}>
          <LinearGradient
            colors={[Colors.secondary, Colors.primary]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.iconContainer}
          >
            <Ionicons name="storefront" size={40} color={Colors.textOnPrimary} />
          </LinearGradient>
          <Text style={styles.title}>{t('onboarding.title', 'Store Profile Details')}</Text>
          <Text style={styles.subtitle}>{t('onboarding.subtitle', 'Initialize your store')}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>{t('onboarding.title', 'Store Profile Details')}</Text>

          {/* Store Name */}
          <Text style={styles.label}>{t('onboarding.store_name', 'Store Name')} *</Text>
          <View style={styles.inputContainer}>
            <Ionicons name="business-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('onboarding.store_name', 'Store Name')}
              placeholderTextColor={Colors.textMuted}
              value={name}
              onChangeText={setName}
            />
          </View>

          {/* Store Type Selector */}
          <Text style={styles.label}>{t('onboarding.store_type', 'Store Type')}</Text>
          <TouchableOpacity
            style={[styles.selectButton, { backgroundColor: Colors.surface, borderColor: Colors.border }]}
            onPress={() => setTypeModalVisible(true)}
            activeOpacity={0.7}
          >
            <Text style={[
              styles.selectButtonText,
              { color: selectedType ? Colors.textPrimary : Colors.textMuted }
            ]}>
              {selectedType || t('onboarding.select_type', 'Select your store type')}
            </Text>
            <Ionicons name="chevron-down" size={20} color={Colors.textMuted} />
          </TouchableOpacity>

          {/* Store Location */}
          <Text style={styles.label}>{t('onboarding.location', 'Location')} *</Text>
          <StoreLocationForm
            value={location}
            onChange={(next) => { setLocation(next); setProblems([]); }}
            problems={problems}
            disabled={loading}
          />

          {/* Operating Hours Preset */}
          <Text style={styles.presetLabel}>
            {t('onboarding.operating_hours', 'Operating Hours')}
          </Text>
          <View style={styles.presetRow}>
            {([
              { key: 'standard', label: t('onboarding.hours_standard', 'Standard') },
              { key: 'open_24_7', label: '24/7' },
              { key: 'weekdays', label: t('onboarding.hours_workdays', 'Workdays') },
            ] as const).map((opt) => (
              <TouchableOpacity
                key={opt.key}
                style={[styles.presetBtn, hoursPreset === opt.key && styles.presetBtnActive]}
                onPress={() => setHoursPreset(opt.key)}
                activeOpacity={0.7}
              >
                <Text style={[styles.presetBtnText, hoursPreset === opt.key && styles.presetBtnTextActive]}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={styles.presetHint}>
            {hoursPreset === 'standard'
              ? t('onboarding.hours_standard_hint', 'Sat–Thu 08:00–22:00, Fri 09:00–22:00')
              : hoursPreset === 'weekdays'
              ? t('onboarding.hours_weekdays_hint', 'Mon–Fri 09:00–17:00')
              : t('onboarding.hours_24_7_hint', 'Always open (no schedule)')}
          </Text>

          {/* Action Button */}
          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleInitialize}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <ActivityIndicator color={Colors.textOnPrimary} />
            ) : (
              <Text style={styles.buttonText}>{t('onboarding.create_store', 'Create Store')}</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardForm>

      {/* Store Type Picker */}
      <Modal visible={typeModalVisible} animationType="slide" transparent onRequestClose={() => setTypeModalVisible(false)}>
        <View style={{ flex: 1, justifyContent: 'flex-end', backgroundColor: Colors.modalOverlay }}>
          <SafeAreaView style={{
            maxHeight: '75%',
            backgroundColor: Colors.surface,
            borderTopLeftRadius: 20,
            borderTopRightRadius: 20,
            borderWidth: 1,
            borderColor: Colors.border,
            borderBottomWidth: 0,
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: Spacing.lg }}>
              <Text style={[Typography.h3, { color: Colors.textPrimary }]}>
                {t('onboarding.select_type', 'Select your store type')}
              </Text>
              <TouchableOpacity onPress={() => setTypeModalVisible(false)}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ paddingHorizontal: Spacing.lg }}>
              {BUSINESS_CATEGORIES.map((cat, idx) => (
                <View key={idx} style={{ marginBottom: Spacing.lg }}>
                  <Text style={[Typography.caption, {
                    color: Colors.textMuted,
                    textTransform: 'uppercase',
                    letterSpacing: 1,
                    marginBottom: Spacing.sm,
                    fontWeight: '600',
                  }]}>
                    {isAr ? cat.group.ar : cat.group.en}
                  </Text>
                  {cat.types.map((type, tIdx) => {
                    const label = isAr ? type.ar : type.en;
                    const isSelected = selectedType === label;
                    return (
                      <TouchableOpacity
                        key={tIdx}
                        style={{
                          paddingVertical: Spacing.md,
                          paddingHorizontal: Spacing.md,
                          borderBottomWidth: StyleSheet.hairlineWidth,
                          borderColor: Colors.border,
                          flexDirection: 'row',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          backgroundColor: isSelected ? Colors.primaryLight : 'transparent',
                          borderRadius: isSelected ? BorderRadius.md : 0,
                        }}
                        onPress={() => {
                          setSelectedType(label);
                          setTypeModalVisible(false);
                        }}
                      >
                        <Text style={[Typography.body, { color: isSelected ? Colors.primary : Colors.textPrimary }]}>
                          {label}
                        </Text>
                        {isSelected && <Ionicons name="checkmark" size={20} color={Colors.primary} />}
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ))}
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>
    </View>
  );
}
