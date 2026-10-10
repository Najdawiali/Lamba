/**
 * StoreLocationForm: where a store is, in one reusable piece. Used when a customer opens a store
 * (create-store), in the merchant onboarding screen, and when a merchant edits the address (profile).
 *
 * - the pin: "Detect my location" (GPS) or "Choose on map" (LocationPicker); raw coordinates are not shown;
 * - the address: governorate (fixed list of Jordan's 12), area, street (optional), landmark (optional);
 * - the phone's geocoder only PREFILLS governorate / area / street. A merchant's own text is never
 *   replaced without asking, and a detect that finds nothing leaves the fields as they are.
 *
 * Controlled: the parent owns the value (utils/jordanAddress StoreLocationValue) and validates it with
 * locationProblems / toLocationPayload. For an existing store pass `saved`: the pin may then move only
 * FREE_MOVE_LIMIT_M and the governorate is fixed (the server enforces the same rules).
 */

import React, { useMemo, useRef, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, Modal, ScrollView, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../constants/theme';
import { t, i18n } from '../services/i18n';
import {
  getCurrentFix, reverseGeocodeDevice, LocationPermissionDenied, type GpsFix,
} from '../services/deviceLocation';
import LocationPicker from './LocationPicker';
import {
  AREA_MAX_LENGTH, FREE_MOVE_LIMIT_M, GOVERNORATES, LANDMARK_MAX_LENGTH, STREET_MAX_LENGTH,
  applyPlan, distanceMeters, governorateName, moveStatus, needsAccuracyWarning, planPrefill,
  type LocationProblem, type Pin, type PrefillField, type StoreLocationValue,
} from '../utils/jordanAddress';

interface Props {
  value: StoreLocationValue;
  onChange: (next: StoreLocationValue) => void;
  /** An existing store: its saved pin and governorate. Limits moving the pin and fixes the governorate. */
  saved?: { latitude: number; longitude: number; governorate: string } | null;
  /** Fields to mark as problems (red), from locationProblems(). */
  problems?: LocationProblem[];
  disabled?: boolean;
}

const SAME_PIN_M = 15;         // a GPS fix and a pin closer than this are the same place
const REGEOCODE_MOVE_M = 100;  // after the map, look up the address again only if the pin moved this far

export default function StoreLocationForm({ value, onChange, saved, problems = [], disabled }: Props) {
  const Colors = useThemeColors();
  const isAr = !!i18n.locale?.startsWith('ar');

  const valueRef = useRef(value);
  valueRef.current = value;
  // Fields the merchant typed or chose (an earlier suggestion does not count). A saved store's text is theirs.
  const edited = useRef<Record<PrefillField, boolean>>({
    governorate: !!saved, area: !!saved, street: !!saved,
  });
  const [gpsFix, setGpsFix] = useState<GpsFix | null>(null);
  const [locating, setLocating] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [governorateOpen, setGovernorateOpen] = useState(false);
  const [note, setNote] = useState<'filled' | 'none' | null>(null);

  const governorateLocked = !!saved?.governorate;
  const pin: Pin | null =
    value.latitude !== null && value.longitude !== null ? { latitude: value.latitude, longitude: value.longitude } : null;
  const weakFix =
    !!gpsFix && !!pin && needsAccuracyWarning(gpsFix.accuracy) &&
    distanceMeters(pin.latitude, pin.longitude, gpsFix.latitude, gpsFix.longitude) < SAME_PIN_M;

  const update = (patch: Partial<StoreLocationValue>) => {
    const next = { ...valueRef.current, ...patch };
    valueRef.current = next;
    onChange(next);
  };

  const fieldLabel = (field: PrefillField) =>
    field === 'governorate' ? t('storeLocation.governorate', 'Governorate')
      : field === 'area' ? t('storeLocation.area', 'Area / neighbourhood')
      : t('storeLocation.street', 'Street');

  const askToReplace = (fields: PrefillField[]) =>
    new Promise<boolean>((resolve) => {
      Alert.alert(
        t('storeLocation.replace_title', 'Replace what you typed?'),
        t('storeLocation.replace_message', 'This location suggests different values for: {{fields}}. Replace what you typed?', {
          fields: fields.map(fieldLabel).join(isAr ? '، ' : ', '),
        }),
        [
          { text: t('storeLocation.keep', 'Keep mine'), style: 'cancel', onPress: () => resolve(false) },
          { text: t('storeLocation.replace', 'Replace'), onPress: () => resolve(true) },
        ],
        { cancelable: true, onDismiss: () => resolve(false) },
      );
    });

  /** Look up the address of a pin on the phone and fill governorate / area / street as suggestions. */
  const prefillFrom = async (latitude: number, longitude: number) => {
    const prefill = await reverseGeocodeDevice(latitude, longitude);
    if (!prefill.governorate && !prefill.area && !prefill.street) {
      setNote('none');
      return;
    }
    const now = valueRef.current;
    const current = { governorate: now.governorate, area: now.area, street: now.street };
    const plan = planPrefill(current, edited.current, prefill, { skipGovernorate: governorateLocked });
    const replace = plan.conflicts.length > 0 ? await askToReplace(plan.conflicts) : false;
    const next = applyPlan(current, plan, prefill, replace);
    update({ governorate: next.governorate, area: next.area, street: next.street });
    for (const field of Object.keys(plan.fill) as PrefillField[]) edited.current[field] = false;
    if (replace) for (const field of plan.conflicts) edited.current[field] = false;
    setNote(Object.keys(plan.fill).length > 0 || replace ? 'filled' : null);
  };

  const tooFarMessage = (meters: number) =>
    t('storeLocation.too_far', 'That is {{meters}} m from the saved location. The app can move it up to {{limit}} m; for more, contact support.', {
      meters: Math.round(meters), limit: FREE_MOVE_LIMIT_M,
    });

  const handleDetect = async () => {
    setLocating(true);
    try {
      const fix = await getCurrentFix();
      if (saved) {
        const move = moveStatus(saved, fix);
        if (!move.allowed) {
          Alert.alert(t('common.error', 'Error'), tooFarMessage(move.meters));
          return;
        }
      }
      setGpsFix(fix);
      update({ latitude: fix.latitude, longitude: fix.longitude });
      await prefillFrom(fix.latitude, fix.longitude);
    } catch (err) {
      const denied = err instanceof LocationPermissionDenied;
      Alert.alert(
        denied ? t('storeLocation.permission_title', 'Location permission') : t('common.error', 'Error'),
        denied
          ? t('storeLocation.permission_desc', 'Please allow location access to find your position, or choose the location on the map.')
          : t('storeLocation.detect_failed', "Couldn't get your location. Choose it on the map instead."),
      );
    } finally {
      setLocating(false);
    }
  };

  const handlePicked = async (picked: Pin, fix: GpsFix | null) => {
    setPickerOpen(false);
    const before = valueRef.current;
    setGpsFix(fix);
    update({ latitude: picked.latitude, longitude: picked.longitude });
    const movedFar =
      before.latitude === null || before.longitude === null ||
      distanceMeters(before.latitude, before.longitude, picked.latitude, picked.longitude) >= REGEOCODE_MOVE_M;
    if (movedFar && !saved) await prefillFrom(picked.latitude, picked.longitude);
  };

  const styles = useMemo(() => StyleSheet.create({
    buttons: { flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.md },
    button: {
      flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.xs,
      paddingVertical: Spacing.md, paddingHorizontal: Spacing.sm, borderRadius: BorderRadius.lg,
      borderWidth: 1, borderColor: Colors.primary + '40', backgroundColor: Colors.primary + '1F',
    },
    buttonText: { ...Typography.bodySmall, color: Colors.primary, fontWeight: '700', flexShrink: 1, textAlign: 'center' },
    status: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, marginBottom: Spacing.sm },
    statusText: { ...Typography.caption, flex: 1 },
    warning: {
      flexDirection: 'row', gap: Spacing.sm, padding: Spacing.md, marginBottom: Spacing.md,
      borderRadius: BorderRadius.md, backgroundColor: Colors.warningBg, borderWidth: 1, borderColor: Colors.warningBorder,
    },
    warningText: { ...Typography.caption, flex: 1, color: Colors.textPrimary },
    label: { ...Typography.bodySmall, color: Colors.textSecondary, fontWeight: '600', marginBottom: Spacing.xs },
    field: {
      flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surfaceElevated, borderRadius: BorderRadius.lg,
      borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, minHeight: 52, marginBottom: Spacing.md,
    },
    fieldError: { borderColor: Colors.error },
    fieldDisabled: { opacity: 0.6 },
    input: { flex: 1, color: Colors.textPrimary, ...Typography.body },
    selectText: { flex: 1, ...Typography.body },
    help: { ...Typography.caption, color: Colors.textMuted, marginTop: -Spacing.sm, marginBottom: Spacing.md },
    overlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: Colors.modalOverlay },
    sheet: {
      maxHeight: '80%', backgroundColor: Colors.surface, borderTopLeftRadius: BorderRadius.xl,
      borderTopRightRadius: BorderRadius.xl, borderWidth: 1, borderBottomWidth: 0, borderColor: Colors.border,
    },
    sheetHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: Spacing.lg },
    sheetTitle: { ...Typography.h3, color: Colors.textPrimary },
    option: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.xl, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: Colors.border,
    },
  }), [Colors]);

  const has = (problem: LocationProblem) => problems.includes(problem);
  const pinProblem = has('pin_missing') || has('pin_outside_jordan');
  const busy = !!disabled || locating;

  return (
    <View>
      <View style={styles.buttons}>
        <TouchableOpacity style={[styles.button, busy && styles.fieldDisabled]} onPress={handleDetect} disabled={busy}>
          {locating
            ? <ActivityIndicator size="small" color={Colors.primary} />
            : <Ionicons name="navigate-circle-outline" size={20} color={Colors.primary} />}
          <Text style={styles.buttonText}>
            {locating ? t('storeLocation.detecting', 'Detecting...') : t('storeLocation.detect', 'Detect my location')}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.button, disabled && styles.fieldDisabled]} onPress={() => setPickerOpen(true)} disabled={disabled}>
          <Ionicons name="map-outline" size={20} color={Colors.primary} />
          <Text style={styles.buttonText}>
            {pin ? t('storeLocation.adjust_on_map', 'Adjust pin on map') : t('storeLocation.choose_on_map', 'Choose on map')}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.status}>
        <Ionicons
          name={pin ? 'checkmark-circle' : 'ellipse-outline'}
          size={18}
          color={pin ? Colors.success : pinProblem ? Colors.error : Colors.textMuted}
        />
        <Text style={[styles.statusText, { color: pin ? Colors.success : pinProblem ? Colors.error : Colors.textMuted }]}>
          {pin
            ? t('storeLocation.pin_set', 'Store location pinned on the map')
            : has('pin_outside_jordan')
              ? t('storeLocation.outside_jordan', 'The pin must be inside Jordan.')
              : t('storeLocation.pin_missing', 'Set your store location with one of the buttons above')}
        </Text>
      </View>

      {weakFix && gpsFix ? (
        <View style={styles.warning}>
          <Ionicons name="warning-outline" size={18} color={Colors.warning} />
          <Text style={styles.warningText}>
            {t('storeLocation.accuracy_low', 'GPS accuracy is low (about ±{{meters}} m). Move the map so the pin sits on your shop entrance.', {
              meters: Math.round(gpsFix.accuracy ?? 0),
            })}
          </Text>
        </View>
      ) : null}

      {note ? (
        <Text style={[styles.help, { marginTop: 0 }]}>
          {note === 'filled'
            ? t('storeLocation.prefill_hint', 'Some fields were filled from your location. Please check them and edit if needed.')
            : t('storeLocation.prefill_none', "Couldn't work out the address from this location. Please fill it in below.")}
        </Text>
      ) : null}

      <Text style={styles.label}>{t('storeLocation.governorate', 'Governorate')} *</Text>
      <TouchableOpacity
        style={[styles.field, has('governorate_missing') && styles.fieldError, (governorateLocked || disabled) && styles.fieldDisabled]}
        onPress={() => setGovernorateOpen(true)}
        disabled={governorateLocked || disabled}
        activeOpacity={0.7}
      >
        <Text style={[styles.selectText, { color: value.governorate ? Colors.textPrimary : Colors.textMuted }]}>
          {value.governorate
            ? governorateName(value.governorate, isAr)
            : t('storeLocation.governorate_placeholder', 'Select governorate')}
        </Text>
        <Ionicons name={governorateLocked ? 'lock-closed-outline' : 'chevron-down'} size={18} color={Colors.textMuted} />
      </TouchableOpacity>
      {governorateLocked ? (
        <Text style={styles.help}>
          {t('storeLocation.governorate_locked', "The governorate can't be changed in the app. Contact support.")}
        </Text>
      ) : null}

      <Text style={styles.label}>{t('storeLocation.area', 'Area / neighbourhood')} *</Text>
      <View style={[styles.field, has('area_missing') && styles.fieldError]}>
        <TextInput
          style={styles.input}
          value={value.area}
          onChangeText={(text) => { edited.current.area = true; update({ area: text }); }}
          placeholder={t('storeLocation.area_placeholder', 'e.g. Sport City')}
          placeholderTextColor={Colors.textMuted}
          maxLength={AREA_MAX_LENGTH}
          editable={!disabled}
        />
      </View>

      <Text style={styles.label}>{t('storeLocation.street', 'Street')} ({t('storeLocation.optional', 'optional')})</Text>
      <View style={styles.field}>
        <TextInput
          style={styles.input}
          value={value.street}
          onChangeText={(text) => { edited.current.street = true; update({ street: text }); }}
          placeholder={t('storeLocation.street_placeholder', 'e.g. University Street')}
          placeholderTextColor={Colors.textMuted}
          maxLength={STREET_MAX_LENGTH}
          editable={!disabled}
        />
      </View>

      <Text style={styles.label}>{t('storeLocation.landmark', 'Nearby landmark')} ({t('storeLocation.optional', 'optional')})</Text>
      <View style={styles.field}>
        <TextInput
          style={styles.input}
          value={value.landmark}
          onChangeText={(text) => update({ landmark: text })}
          placeholder={t('storeLocation.landmark_placeholder', 'e.g. Opposite Al-Rahman Mosque')}
          placeholderTextColor={Colors.textMuted}
          maxLength={LANDMARK_MAX_LENGTH}
          editable={!disabled}
        />
      </View>

      {saved ? (
        <Text style={styles.help}>
          {t('storeLocation.limit_note', 'You can move the pin up to {{limit}} m and edit the area, street and landmark freely. Anything bigger, or a different governorate, goes through support.', {
            limit: FREE_MOVE_LIMIT_M,
          })}
        </Text>
      ) : null}

      <LocationPicker
        visible={pickerOpen}
        initial={pin ?? (gpsFix ? { latitude: gpsFix.latitude, longitude: gpsFix.longitude } : null)}
        anchor={saved ?? null}
        gpsFix={gpsFix}
        onConfirm={handlePicked}
        onClose={() => setPickerOpen(false)}
      />

      <Modal visible={governorateOpen} animationType="slide" transparent onRequestClose={() => setGovernorateOpen(false)}>
        <View style={styles.overlay}>
          <SafeAreaView style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>{t('storeLocation.governorate_placeholder', 'Select governorate')}</Text>
              <TouchableOpacity onPress={() => setGovernorateOpen(false)}>
                <Ionicons name="close" size={24} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
            <ScrollView>
              {GOVERNORATES.map((g) => {
                const selected = g.key === value.governorate;
                return (
                  <TouchableOpacity
                    key={g.key}
                    style={styles.option}
                    onPress={() => { edited.current.governorate = true; update({ governorate: g.key }); setGovernorateOpen(false); }}
                    activeOpacity={0.7}
                  >
                    <Text style={[Typography.body, { color: selected ? Colors.primary : Colors.textPrimary, fontWeight: selected ? '700' : '400' }]}>
                      {isAr ? g.ar : g.en}
                    </Text>
                    {selected ? <Ionicons name="checkmark" size={20} color={Colors.primary} /> : null}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>
    </View>
  );
}
