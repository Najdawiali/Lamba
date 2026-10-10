/**
 * LocationPicker: a full-screen map where the merchant sets the store pin.
 *
 * The pin stays in the middle of the screen and the merchant moves the map under it (more reliable
 * on Android than dragging a marker). Satellite view helps to find the shop entrance, the
 * my-location button re-reads the GPS, and a weak GPS fix (worse than ~50 m) gets a warning until the
 * map is moved. For a store that already exists, a ring shows how far the pin may be moved in the
 * app (utils/jordanAddress FREE_MOVE_LIMIT_M); the server enforces the same rule.
 */

import React, { useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Modal, ActivityIndicator, Alert } from 'react-native';
import MapView, { Circle, PROVIDER_GOOGLE, type Region } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography, Shadows } from '../constants/theme';
import { t } from '../services/i18n';
import { getMapStyle } from '../services/utils';
import { getCurrentFix, LocationPermissionDenied, type GpsFix } from '../services/deviceLocation';
import {
  FREE_MOVE_LIMIT_M, JORDAN_CENTER, distanceMeters, isInsideJordan, moveStatus, needsAccuracyWarning,
  type Pin,
} from '../utils/jordanAddress';

interface Props {
  visible: boolean;
  /** Where the map opens: the pin chosen so far, else the last GPS fix, else Amman. */
  initial: Pin | null;
  /** The store's saved pin when editing an existing store: shows the ring and limits the move. */
  anchor?: Pin | null;
  /** The last GPS fix, so its accuracy warning can be shown on opening. */
  gpsFix?: GpsFix | null;
  onConfirm: (pin: Pin, gpsFix: GpsFix | null) => void;
  onClose: () => void;
}

const CLOSE_ZOOM_DELTA = 0.002; // about 200 m across
const AT_FIX_M = 15;            // the pin counts as "on the GPS fix" within this distance
const PIN_SIZE = 44;

export default function LocationPicker({ visible, ...rest }: Props) {
  return (
    <Modal
      visible={visible}
      animationType="slide"
      onRequestClose={rest.onClose}
      statusBarTranslucent
      navigationBarTranslucent
    >
      {visible ? <PickerBody {...rest} /> : null}
    </Modal>
  );
}

function PickerBody({ initial, anchor, gpsFix, onConfirm, onClose }: Omit<Props, 'visible'>) {
  const { colors: Colors, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const mapRef = useRef<MapView>(null);

  const start = initial ?? JORDAN_CENTER;
  const [center, setCenter] = useState<Pin>({ latitude: start.latitude, longitude: start.longitude });
  const [satellite, setSatellite] = useState(false);
  const [fix, setFix] = useState<GpsFix | null>(gpsFix ?? null);
  const [locating, setLocating] = useState(false);

  const inside = isInsideJordan(center.latitude, center.longitude);
  const move = anchor ? moveStatus(anchor, center) : null;
  const tooFar = !!move && !move.allowed;
  const atFix = !!fix && distanceMeters(center.latitude, center.longitude, fix.latitude, fix.longitude) < AT_FIX_M;
  const weakFix = atFix && !!fix && needsAccuracyWarning(fix.accuracy);
  const canConfirm = inside && !tooFar;

  const goTo = (pin: Pin) => {
    mapRef.current?.animateToRegion(
      { latitude: pin.latitude, longitude: pin.longitude, latitudeDelta: CLOSE_ZOOM_DELTA, longitudeDelta: CLOSE_ZOOM_DELTA },
      400,
    );
  };

  const handleMyLocation = async () => {
    setLocating(true);
    try {
      const reading = await getCurrentFix();
      setFix(reading);
      setCenter({ latitude: reading.latitude, longitude: reading.longitude });
      goTo(reading);
    } catch (err) {
      Alert.alert(
        err instanceof LocationPermissionDenied
          ? t('storeLocation.permission_title', 'Location permission')
          : t('common.error', 'Error'),
        err instanceof LocationPermissionDenied
          ? t('storeLocation.permission_desc', 'Please allow location access to find your position, or move the map by hand.')
          : t('storeLocation.detect_failed', "Couldn't get your location. Move the map to set it."),
      );
    } finally {
      setLocating(false);
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    root: { flex: 1, backgroundColor: Colors.background },
    map: { ...StyleSheet.absoluteFillObject },
    pinLayer: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
    pinDot: { position: 'absolute', width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.primary, opacity: 0.6 },
    topBar: {
      position: 'absolute', left: 0, right: 0, top: 0, paddingTop: insets.top + Spacing.sm,
      paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    },
    roundButton: {
      width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center',
      justifyContent: 'center', borderWidth: 1, borderColor: Colors.border, ...Shadows.medium,
    },
    titlePill: {
      flex: 1, marginHorizontal: Spacing.md, paddingVertical: Spacing.sm, paddingHorizontal: Spacing.md,
      borderRadius: BorderRadius.full, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border,
    },
    titleText: { ...Typography.bodySmall, color: Colors.textPrimary, fontWeight: '700', textAlign: 'center' },
    myLocation: {
      position: 'absolute', right: Spacing.lg, width: 48, height: 48, borderRadius: 24,
      backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center',
      borderWidth: 1, borderColor: Colors.border, ...Shadows.medium,
    },
    sheet: {
      position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: Colors.surface,
      borderTopLeftRadius: BorderRadius.xl, borderTopRightRadius: BorderRadius.xl,
      paddingHorizontal: Spacing.lg, paddingTop: Spacing.lg, paddingBottom: insets.bottom + Spacing.lg,
      borderWidth: 1, borderBottomWidth: 0, borderColor: Colors.border, gap: Spacing.sm,
    },
    hint: { ...Typography.bodySmall, color: Colors.textSecondary, textAlign: 'center' },
    banner: { flexDirection: 'row', gap: Spacing.sm, padding: Spacing.md, borderRadius: BorderRadius.md, borderWidth: 1 },
    bannerWarning: { backgroundColor: Colors.warningBg, borderColor: Colors.warningBorder },
    bannerError: { backgroundColor: Colors.errorBg, borderColor: Colors.errorBorder },
    bannerText: { ...Typography.caption, flex: 1, color: Colors.textPrimary },
    confirm: {
      backgroundColor: Colors.primary, borderRadius: BorderRadius.lg, paddingVertical: Spacing.md,
      alignItems: 'center', marginTop: Spacing.xs,
    },
    confirmDisabled: { opacity: 0.45 },
    confirmText: { ...Typography.button, color: Colors.textOnPrimary },
  }), [Colors, insets.top, insets.bottom]);

  // The my-location button sits above the sheet; the sheet grows with its banners.
  const bannerCount = (weakFix ? 1 : 0) + (!inside ? 1 : 0) + (tooFar ? 1 : 0);
  const myLocationBottom = insets.bottom + 150 + bannerCount * 64;

  return (
    <View style={styles.root}>
      <MapView
        ref={mapRef}
        style={styles.map}
        provider={PROVIDER_GOOGLE}
        mapType={satellite ? 'hybrid' : 'standard'}
        customMapStyle={satellite ? undefined : getMapStyle(isDark ? 'dark' : 'light')}
        initialRegion={{
          latitude: start.latitude, longitude: start.longitude,
          latitudeDelta: initial ? CLOSE_ZOOM_DELTA : 0.05, longitudeDelta: initial ? CLOSE_ZOOM_DELTA : 0.05,
        }}
        onRegionChangeComplete={(region: Region) =>
          setCenter({ latitude: region.latitude, longitude: region.longitude })}
        showsUserLocation
        showsMyLocationButton={false}
        toolbarEnabled={false}
        rotateEnabled={false}
        pitchEnabled={false}
      >
        {anchor ? (
          <Circle
            center={anchor}
            radius={FREE_MOVE_LIMIT_M}
            strokeColor={Colors.primary}
            strokeWidth={2}
            fillColor={Colors.primary + '22'}
          />
        ) : null}
      </MapView>

      {/* The pin: its tip is the exact middle of the screen. */}
      <View style={styles.pinLayer} pointerEvents="none">
        <View style={styles.pinDot} />
        <Ionicons name="location" size={PIN_SIZE} color={Colors.primary} style={{ marginBottom: PIN_SIZE }} />
      </View>

      <View style={styles.topBar}>
        <TouchableOpacity style={styles.roundButton} onPress={onClose} accessibilityLabel={t('common.cancel', 'Cancel')}>
          <Ionicons name="close" size={22} color={Colors.textPrimary} />
        </TouchableOpacity>
        <View style={styles.titlePill}>
          <Text style={styles.titleText} numberOfLines={1}>{t('storeLocation.picker_title', 'Set store location')}</Text>
        </View>
        <TouchableOpacity
          style={styles.roundButton}
          onPress={() => setSatellite((on) => !on)}
          accessibilityLabel={satellite ? t('storeLocation.map_view', 'Map') : t('storeLocation.satellite_view', 'Satellite')}
        >
          <Ionicons name={satellite ? 'map-outline' : 'earth'} size={22} color={Colors.textPrimary} />
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        style={[styles.myLocation, { bottom: myLocationBottom }]}
        onPress={handleMyLocation}
        disabled={locating}
        accessibilityLabel={t('storeLocation.my_location', 'My location')}
      >
        {locating
          ? <ActivityIndicator size="small" color={Colors.primary} />
          : <Ionicons name="locate" size={24} color={Colors.primary} />}
      </TouchableOpacity>

      <View style={styles.sheet}>
        {weakFix && fix ? (
          <View style={[styles.banner, styles.bannerWarning]}>
            <Ionicons name="warning-outline" size={18} color={Colors.warning} />
            <Text style={styles.bannerText}>
              {t('storeLocation.accuracy_low', 'GPS accuracy is low (about ±{{meters}} m). Move the map so the pin sits on your shop entrance.', { meters: Math.round(fix.accuracy ?? 0) })}
            </Text>
          </View>
        ) : null}
        {!inside ? (
          <View style={[styles.banner, styles.bannerError]}>
            <Ionicons name="alert-circle-outline" size={18} color={Colors.error} />
            <Text style={styles.bannerText}>{t('storeLocation.outside_jordan', 'The pin must be inside Jordan.')}</Text>
          </View>
        ) : null}
        {tooFar && move ? (
          <View style={[styles.banner, styles.bannerError]}>
            <Ionicons name="alert-circle-outline" size={18} color={Colors.error} />
            <Text style={styles.bannerText}>
              {t('storeLocation.too_far', 'That is {{meters}} m from the saved location. The app can move it up to {{limit}} m; for more, contact support.', { meters: Math.round(move.meters), limit: FREE_MOVE_LIMIT_M })}
            </Text>
          </View>
        ) : null}
        <Text style={styles.hint}>{t('storeLocation.picker_hint', 'Move the map so the pin sits on your shop entrance.')}</Text>
        <TouchableOpacity
          style={[styles.confirm, !canConfirm && styles.confirmDisabled]}
          disabled={!canConfirm}
          onPress={() => onConfirm({ latitude: center.latitude, longitude: center.longitude }, atFix ? fix : null)}
        >
          <Text style={styles.confirmText}>{t('storeLocation.confirm_pin', 'Confirm location')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}
