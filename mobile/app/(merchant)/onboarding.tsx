/**
 * Market Profile Onboarding Screen — Setup store parameters.
 * Captures name, address, and coordinates (with interactive mock geolocator).
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, Alert, ActivityIndicator, ScrollView
} from 'react-native';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { createMarket } from '../../services/api';
import { Colors, Spacing, BorderRadius, Typography, Shadows } from '../../constants/theme';
import { t, i18n } from '../../services/i18n';

export default function OnboardingScreen() {
  const router = useRouter();
  const isAr = i18n.locale.includes('ar');
  
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [geolocating, setGeolocating] = useState(false);

  const handleGeolocate = () => {
    setGeolocating(true);
    // Simulate high-fidelity GPS lookup in Jordan, As-Salt
    setTimeout(() => {
      setLatitude('32.0385');
      setLongitude('35.7275');
      setGeolocating(false);
      Alert.alert(
        isAr ? 'تم تحديد الموقع' : 'Location Located',
        isAr ? 'تم الحصول على إحداثيات المتجر بنجاح! مدينة السلط الرياضية (32.0385، 35.7275).' : 'Store coordinates successfully acquired! Sport City, As-Salt (32.0385, 35.7275) was selected.'
      );
    }, 1500);
  };

  const handleInitialize = async () => {
    if (!name.trim() || !address.trim() || !latitude.trim() || !longitude.trim()) {
      Alert.alert(t('common.error'), isAr ? 'الرجاء تعبئة كافة حقول المتجر الفعلي' : 'Please fill in all physical store fields');
      return;
    }

    const latVal = parseFloat(latitude);
    const lngVal = parseFloat(longitude);

    if (isNaN(latVal) || latVal < -90 || latVal > 90) {
      Alert.alert(t('common.error'), isAr ? 'الرجاء إدخال خط عرض صحيح (-90 إلى 90)' : 'Please enter a valid Latitude (-90 to 90)');
      return;
    }

    if (isNaN(lngVal) || lngVal < -180 || lngVal > 180) {
      Alert.alert(t('common.error'), isAr ? 'الرجاء إدخال خط طول صحيح (-180 إلى 180)' : 'Please enter a valid Longitude (-180 to 180)');
      return;
    }

    setLoading(true);
    try {
      await createMarket(name.trim(), address.trim(), latVal, lngVal);
      
      Alert.alert(
        t('common.success'),
        isAr ? 'تم تهيئة متجرك بنجاح! أهلاً بك في لوحة التحكم.' : 'Your market has been successfully initialized! Welcome to your Dashboard.',
        [
          {
            text: isAr ? 'دعنا نبدأ' : 'Let\'s Go',
            onPress: () => router.replace('/(merchant)/dashboard')
          }
        ]
      );
    } catch (err: any) {
      Alert.alert(
        isAr ? 'فشل التفعيل' : 'Initialization Failed',
        err?.response?.data?.detail || (isAr ? 'حدث خطأ ما. يرجى التحقق من الإحداثيات والمحاولة مجدداً.' : 'Something went wrong. Please check coordinates and try again.')
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
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
          <Text style={styles.title}>{t('onboarding.title')}</Text>
          <Text style={styles.subtitle}>{t('onboarding.subtitle')}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>{isAr ? 'تفاصيل ملف تعريف المتجر' : 'Store Profile Details'}</Text>

          {/* Store Name */}
          <View style={styles.inputContainer}>
            <Ionicons name="business-outline" size={20} color={Colors.textMuted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder={t('onboarding.store_name')}
              placeholderTextColor={Colors.textMuted}
              value={name}
              onChangeText={setName}
            />
          </View>

          {/* Store Address */}
          <View style={[styles.inputContainer, styles.textAreaContainer]}>
            <Ionicons 
              name="location-outline" 
              size={20} 
              color={Colors.textMuted} 
              style={[styles.inputIcon, { marginTop: Spacing.sm }]} 
            />
            <TextInput
              style={[styles.input, styles.textArea]}
              placeholder={t('onboarding.address')}
              placeholderTextColor={Colors.textMuted}
              value={address}
              onChangeText={setAddress}
              multiline
              numberOfLines={3}
            />
          </View>

          {/* Coordinates Row */}
          <View style={styles.coordsRow}>
            {/* Latitude */}
            <View style={[styles.inputContainer, { flex: 1, marginBottom: 0 }]}>
              <Text style={styles.coordPrefix}>Lat:</Text>
              <TextInput
                style={styles.input}
                placeholder="32.0385"
                placeholderTextColor={Colors.textMuted}
                value={latitude}
                onChangeText={setLatitude}
                keyboardType="numeric"
              />
            </View>
            
            {/* Longitude */}
            <View style={[styles.inputContainer, { flex: 1, marginBottom: 0 }]}>
              <Text style={styles.coordPrefix}>Lng:</Text>
              <TextInput
                style={styles.input}
                placeholder="35.7275"
                placeholderTextColor={Colors.textMuted}
                value={longitude}
                onChangeText={setLongitude}
                keyboardType="numeric"
              />
            </View>
          </View>

          {/* Geolocate Button */}
          <TouchableOpacity
            style={styles.geolocateBtn}
            onPress={handleGeolocate}
            disabled={geolocating || loading}
            activeOpacity={0.7}
          >
            {geolocating ? (
              <ActivityIndicator color={Colors.secondary} />
            ) : (
              <>
                <Ionicons name="locate-outline" size={18} color={Colors.secondary} />
                <Text style={styles.geolocateText}>
                  {isAr ? 'الحصول على الإحداثيات الحالية (محاكاة السلط)' : 'Acquire Current Coordinates (As-Salt Mock)'}
                </Text>
              </>
            )}
          </TouchableOpacity>

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
              <Text style={styles.buttonText}>{t('onboarding.activate')}</Text>
            )}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
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
  textAreaContainer: {
    height: 90,
    alignItems: 'flex-start',
  },
  inputIcon: {
    marginRight: Spacing.sm,
  },
  input: {
    flex: 1,
    color: Colors.textPrimary,
    ...Typography.body,
  },
  textArea: {
    height: '100%',
    textAlignVertical: 'top',
    paddingVertical: Spacing.sm,
  },
  coordsRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  coordPrefix: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    fontWeight: '700',
    marginRight: 4,
  },
  geolocateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: 'rgba(0, 217, 166, 0.05)',
    borderWidth: 1,
    borderColor: 'rgba(0, 217, 166, 0.15)',
    marginBottom: Spacing.xl,
    height: 48,
  },
  geolocateText: {
    ...Typography.caption,
    color: Colors.secondary,
    fontWeight: '700',
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
});
