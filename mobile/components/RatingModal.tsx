/**
 * RatingModal — Bottom sheet-style interactive modal overlay.
 *
 * Provides:
 *  - Interactive 5-star rating selector with smooth color highlights.
 *  - Multiline review text field.
 *  - Submit button with spinner loading state and a visual "Rating Stored!" checkmark success panel.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Modal, View, Text, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform, TouchableWithoutFeedback, Keyboard
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { Spacing, BorderRadius, Typography, Shadows } from '../constants/theme';
import { useThemeColors } from '../context/ThemeContext';
import { t } from '../services/i18n';
import { submitMarketRating, getUser } from '../services/api';

interface Props {
  visible: boolean;
  onClose: () => void;
  marketId: string;
  marketName: string;
}

export default function RatingModal({ visible, onClose, marketId, marketName }: Props) {
  const Colors = useThemeColors();

  const styles = useMemo(() => StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: Colors.modalOverlay,
    justifyContent: 'flex-end',
  },
  keyboardView: {
    width: '100%',
  },
  sheet: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    paddingTop: Spacing.md,
    paddingHorizontal: Spacing.xl,
    paddingBottom: Platform.OS === 'ios' ? Spacing.xxxl : Spacing.xl,
    borderTopWidth: 1,
    borderColor: Colors.border,
    ...Shadows.large,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderColor: Colors.border,
    marginBottom: Spacing.md,
  },
  headerTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
    flex: 1,
    marginRight: Spacing.md,
  },
  closeButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  formContainer: {
    paddingVertical: Spacing.sm,
  },
  label: {
    ...Typography.label,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
    marginTop: Spacing.md,
  },
  starRow: {
    flexDirection: 'row',
    direction: 'ltr',
    writingDirection: 'ltr' as any,
    justifyContent: 'center',
    gap: Spacing.md,
    marginVertical: Spacing.md,
  },
  starTouch: {
    padding: Spacing.xs,
  },
  textInput: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    color: Colors.textPrimary,
    ...Typography.bodySmall,
    height: 100,
    textAlignVertical: 'top',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  errorText: {
    ...Typography.bodySmall,
    color: Colors.error,
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  submitButton: {
    backgroundColor: Colors.primary,
    height: 50,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.xl,
    ...Shadows.small,
  },
  submitText: {
    ...Typography.label,
    color: Colors.background,
    fontWeight: '700',
  },
  submitTextDisabled: {
    opacity: 0.6,
  },
  
  // Success View Styles
  successContainer: {
    alignItems: 'center',
    paddingVertical: Spacing.xl,
  },
  successBadge: {
    marginBottom: Spacing.md,
  },
  successTitle: {
    ...Typography.h2,
    color: Colors.textPrimary,
    marginBottom: Spacing.sm,
  },
  successText: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    paddingHorizontal: Spacing.lg,
    marginBottom: Spacing.xl,
    lineHeight: 22,
  },
  doneButton: {
    backgroundColor: Colors.surfaceElevated,
    height: 48,
    borderRadius: BorderRadius.md,
    width: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  doneButtonText: {
    ...Typography.label,
    color: Colors.textPrimary,
  },
  }), [Colors]);
  const [score, setScore] = useState<number>(0);
  const [review, setReview] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [success, setSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form when modal visibility changes
  useEffect(() => {
    if (visible) {
      setScore(0);
      setReview('');
      setSuccess(false);
      setError(null);
      setLoading(false);
    }
  }, [visible]);

  const handleSubmit = async () => {
    if (score < 1 || score > 5) {
      setError(t('rating.validation_error', 'Please select a rating between 1 and 5 stars.'));
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      const user = await getUser();
      if (!user || !user.id) {
        setError(t('rating.login_required', 'You must be logged in to submit reviews.'));
        setLoading(false);
        return;
      }
      
      // Request location to verify physical presence at shop counter
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setError(t('rating.gps_permission', 'GPS permission is required to verify you are physically at the shop.'));
        setLoading(false);
        return;
      }

      const loc = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      await submitMarketRating({
        market_id: marketId,
        customer_id: user.id,
        score,
        review: review.trim() || undefined,
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude
      });
      
      setSuccess(true);
    } catch (err: any) {
      console.error('Failed to submit rating:', err);
      const detail = err.response?.data?.detail || t('rating.submission_failed', 'Failed to submit review. Try again.');
      setError(typeof detail === 'string' ? detail : t('rating.submission_failed', 'Failed to submit review.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={true}
      onRequestClose={onClose}
    >
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <View style={styles.overlay}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardView}
          >
            <View style={styles.sheet}>
              {/* Header */}
              <View style={styles.header}>
                <Text style={styles.headerTitle} numberOfLines={1}>
                  {success ? t('rating.thank_you', 'Thank You!') : `${t('common.filter', 'Rate')} ${marketName}`}
                </Text>
                <TouchableOpacity onPress={onClose} style={styles.closeButton}>
                  <Ionicons name="close" size={22} color={Colors.textPrimary} />
                </TouchableOpacity>
              </View>

              {success ? (
                /* Success View */
                <View style={styles.successContainer}>
                  <View style={styles.successBadge}>
                    <Ionicons name="checkmark-circle" size={64} color={Colors.inStock} />
                  </View>
                  <Text style={styles.successTitle}>{t('rating.rating_stored', 'Rating Stored!')}</Text>
                  <Text style={styles.successText}>
                    {t('rating.feedback_helps', 'Your feedback helps others discover the best hyper-local stores.')}
                  </Text>
                  <TouchableOpacity style={styles.doneButton} onPress={onClose}>
                    <Text style={styles.doneButtonText}>{t('common.done', 'Done')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                /* Interactive Form View */
                <View style={styles.formContainer}>
                  <Text style={styles.label}>{t('rating.how_was', 'How was your experience?')}</Text>
                  
                  {/* Star Selector */}
                  <View style={styles.starRow}>
                    {[1, 2, 3, 4, 5].map((star) => (
                      <TouchableOpacity
                        key={star}
                        activeOpacity={0.7}
                        onPress={() => setScore(star)}
                        style={styles.starTouch}
                      >
                        <Ionicons
                          name={star <= score ? 'star' : 'star-outline'}
                          size={40}
                          color={star <= score ? '#FFB000' : Colors.textMuted}
                        />
                      </TouchableOpacity>
                    ))}
                  </View>

                  {/* Review Text Input */}
                  <Text style={styles.label}>{t('rating.review_optional', 'Write a review (optional)')}</Text>
                  <TextInput
                    style={styles.textInput}
                    placeholder={t('rating.review_hint', 'Tell us about the catalog quality, freshness, or service...')}
                    placeholderTextColor={Colors.textMuted}
                    multiline
                    numberOfLines={4}
                    value={review}
                    onChangeText={setReview}
                    maxLength={1000}
                  />

                  {/* Error display */}
                  {!!error && <Text style={styles.errorText}>{error}</Text>}

                  {/* Submit Button */}
                  <TouchableOpacity
                    style={styles.submitButton}
                    onPress={handleSubmit}
                    disabled={loading || score === 0}
                  >
                    {loading ? (
                      <ActivityIndicator size="small" color={Colors.background} />
                    ) : (
                      <Text style={[styles.submitText, score === 0 && styles.submitTextDisabled]}>
                        {t('rating.submit_rating', 'Submit Rating')}
                      </Text>
                    )}
                  </TouchableOpacity>
                </View>
              )}
            </View>
          </KeyboardAvoidingView>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}
