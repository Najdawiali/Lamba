import React from 'react';
import { View, Text, StyleSheet, Modal, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../constants/theme';

interface PickerOption {
  key: string;
  label: string;
  icon?: string;
  subtitle?: string;
}

interface Props {
  visible: boolean;
  onClose: () => void;
  title: string;
  options: PickerOption[];
  selectedKey: string;
  onSelect: (key: string) => void;
  heightPercent?: string;
}

export default function PickerModal({
  visible, onClose, title, options, selectedKey, onSelect, heightPercent = '42%',
}: Props) {
  const Colors = useThemeColors();
  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: Colors.modalOverlay }]}>
        <SafeAreaView style={[styles.container, { backgroundColor: Colors.surface, borderColor: Colors.border, height: heightPercent as any }]}>
          <View style={styles.header}>
            <Text style={[styles.title, { color: Colors.textPrimary }]}>{title}</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>
          {options.map((opt) => {
            const isSelected = opt.key === selectedKey;
            return (
              <TouchableOpacity
                key={opt.key}
                style={[styles.option, { borderColor: Colors.border }]}
                onPress={() => { onSelect(opt.key); onClose(); }}
                activeOpacity={0.7}
              >
                {opt.icon && (
                  <Ionicons name={opt.icon as any} size={22} color={isSelected ? Colors.primary : Colors.textSecondary} />
                )}
                <View style={styles.optionText}>
                  <Text style={[styles.optionLabel, { color: isSelected ? Colors.primary : Colors.textPrimary }]}>
                    {opt.label}
                  </Text>
                  {opt.subtitle && (
                    <Text style={[styles.optionSubtitle, { color: Colors.textMuted }]}>{opt.subtitle}</Text>
                  )}
                </View>
                {isSelected && <Ionicons name="checkmark-circle" size={22} color={Colors.primary} />}
              </TouchableOpacity>
            );
          })}
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  container: {
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    borderWidth: 1,
    borderBottomWidth: 0,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.lg,
  },
  title: { ...Typography.h2 },
  closeBtn: { padding: Spacing.xs },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: Spacing.lg,
    paddingHorizontal: Spacing.xl,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  optionText: { flex: 1 },
  optionLabel: { ...Typography.body, fontWeight: '600' },
  optionSubtitle: { ...Typography.caption, marginTop: 2 },
});
