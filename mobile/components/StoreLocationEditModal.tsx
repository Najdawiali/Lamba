/**
 * StoreLocationEditModal: change where an existing store is (merchant profile, "Store address").
 *
 * The pin may be moved up to FREE_MOVE_LIMIT_M and the area, street and landmark edited freely; a
 * bigger move or another governorate goes through support. The form says so, checks the distance
 * before sending, and shows the server's own message if it refuses (PUT /api/v1/merchant/market/location).
 */

import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Modal, Alert, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../constants/theme';
import { t, i18n } from '../services/i18n';
import { updateMarketLocation, type MarketResponse } from '../services/api';
import { messageFromError } from '../utils/serverMessage';
import KeyboardForm from './KeyboardForm';
import StoreLocationForm from './StoreLocationForm';
import {
  FREE_MOVE_LIMIT_M, locationFromMarket, locationProblems, moveStatus, toLocationPayload,
  type LocationProblem, type StoreLocationValue,
} from '../utils/jordanAddress';

interface Props {
  visible: boolean;
  market: MarketResponse;
  onClose: () => void;
  /** The server accepted the change: the store as it is now. */
  onSaved: (market: MarketResponse) => void;
}

export default function StoreLocationEditModal({ visible, ...rest }: Props) {
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={rest.onClose}>
      {visible ? <EditBody {...rest} /> : null}
    </Modal>
  );
}

function EditBody({ market, onClose, onSaved }: Omit<Props, 'visible'>) {
  const Colors = useThemeColors();
  const isAr = !!i18n.locale?.startsWith('ar');
  const [value, setValue] = useState<StoreLocationValue>(() => locationFromMarket(market));
  const [problems, setProblems] = useState<LocationProblem[]>([]);
  const [saving, setSaving] = useState(false);

  const saved = {
    latitude: market.latitude,
    longitude: market.longitude,
    governorate: market.governorate ?? '',
  };

  const handleSave = async () => {
    const found = locationProblems(value);
    const payload = toLocationPayload(value);
    if (found.length > 0 || !payload) {
      setProblems(found);
      Alert.alert(t('common.error', 'Error'), t(`storeLocation.problem_${found[0] ?? 'pin_missing'}`));
      return;
    }
    const move = moveStatus(saved, payload);
    if (!move.allowed) {
      Alert.alert(
        t('common.error', 'Error'),
        t('storeLocation.too_far', 'That is {{meters}} m from the saved location. The app can move it up to {{limit}} m; for more, contact support.', {
          meters: Math.round(move.meters), limit: FREE_MOVE_LIMIT_M,
        }),
      );
      return;
    }
    setSaving(true);
    try {
      const updated = await updateMarketLocation(payload);
      onSaved(updated);
      Alert.alert(t('storeLocation.saved', 'Location saved'));
    } catch (err) {
      Alert.alert(
        t('common.error', 'Error'),
        messageFromError(err, isAr, {
          network: t('login.network_error', "Couldn't reach the server. Check your internet connection and try again."),
          fallback: t('storeLocation.save_failed', "Couldn't save the location. Please try again."),
        }),
      );
    } finally {
      setSaving(false);
    }
  };

  const styles = useMemo(() => StyleSheet.create({
    root: { flex: 1, backgroundColor: Colors.background },
    header: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border, backgroundColor: Colors.surface,
    },
    title: { ...Typography.h3, color: Colors.textPrimary },
    close: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
    content: { padding: Spacing.xl, paddingBottom: Spacing.xxxl * 2 },
    save: {
      backgroundColor: Colors.primary, borderRadius: BorderRadius.xl, paddingVertical: Spacing.lg,
      alignItems: 'center', justifyContent: 'center', marginTop: Spacing.md,
    },
    saveDisabled: { opacity: 0.6 },
    saveText: { ...Typography.button, color: Colors.textOnPrimary, fontSize: 16, fontWeight: '800' },
  }), [Colors]);

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Text style={styles.title}>{t('storeLocation.edit_title', 'Store address')}</Text>
        <TouchableOpacity style={styles.close} onPress={onClose} disabled={saving}>
          <Ionicons name="close" size={24} color={Colors.textPrimary} />
        </TouchableOpacity>
      </View>
      <KeyboardForm contentContainerStyle={styles.content}>
        <StoreLocationForm
          value={value}
          onChange={(next) => { setValue(next); setProblems([]); }}
          saved={saved}
          problems={problems}
          disabled={saving}
        />
        <TouchableOpacity style={[styles.save, saving && styles.saveDisabled]} onPress={handleSave} disabled={saving}>
          {saving
            ? <ActivityIndicator size="small" color={Colors.textOnPrimary} />
            : <Text style={styles.saveText}>{t('storeLocation.save', 'Save')}</Text>}
        </TouchableOpacity>
      </KeyboardForm>
    </SafeAreaView>
  );
}
