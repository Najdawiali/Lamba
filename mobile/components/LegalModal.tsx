import React from 'react';
import { View, Text, StyleSheet, Modal, ScrollView, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../constants/theme';

interface Props {
  visible: boolean;
  onClose: () => void;
  title: string;
  content: string;
}

export default function LegalModal({ visible, onClose, title, content }: Props) {
  const Colors = useThemeColors();
  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: Colors.modalOverlay }]}>
        <SafeAreaView style={[styles.container, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
          <View style={styles.header}>
            <Text style={[styles.title, { color: Colors.textPrimary }]}>{title}</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.body} showsVerticalScrollIndicator={false}>
            <Text style={[styles.text, { color: Colors.textSecondary }]}>{content}</Text>
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  container: {
    maxHeight: '85%',
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
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  title: { ...Typography.h2 },
  closeBtn: { padding: Spacing.xs },
  body: { padding: Spacing.lg },
  text: { ...Typography.body, lineHeight: 22 },
});
