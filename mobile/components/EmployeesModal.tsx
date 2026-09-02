import React, { useState } from 'react';
import {
  View, Text, StyleSheet, Modal, TextInput, TouchableOpacity,
  ActivityIndicator, FlatList, Alert
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../constants/theme';
import { t, i18n } from '../services/i18n';

interface Props {
  visible: boolean;
  onClose: () => void;
  employees: string[];
  onAdd: (name: string) => Promise<void>;
  onDelete: (index: number) => void;
  saving: boolean;
}

export default function EmployeesModal({
  visible,
  onClose,
  employees,
  onAdd,
  onDelete,
  saving,
}: Props) {
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');
  const [newEmployeeName, setNewEmployeeName] = useState('');

  const handleAdd = async () => {
    const trimmed = newEmployeeName.trim();
    if (!trimmed) {
      Alert.alert(
        isAr ? 'تنبيه' : 'Alert',
        isAr ? 'يرجى إدخال اسم الموظف' : 'Please enter employee name'
      );
      return;
    }
    await onAdd(trimmed);
    setNewEmployeeName('');
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={[styles.fullScreenModalContainer, { backgroundColor: Colors.background }]} edges={['top']}>
        {/* Modal Header */}
        <View style={[styles.modalHeader, { borderColor: Colors.border }]}>
          <Text style={[styles.modalTitle, { color: Colors.textPrimary }]}>
            {t('merchant.employees', isAr ? 'الموظفون' : 'Employees')}
          </Text>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color={Colors.textPrimary} />
          </TouchableOpacity>
        </View>

        {/* Hint */}
        <View style={{ paddingHorizontal: 16, paddingTop: 4, paddingBottom: 10 }}>
          <Text style={{ color: Colors.textMuted, fontSize: 13, textAlign: isAr ? 'right' : 'left' }}>
            {t('merchant.employees_hint', 'Add your team members so customers can see who works here')}
          </Text>
        </View>

        {/* Add Employee Input Row */}
        <View style={[styles.employeeAddRow, { borderColor: Colors.border }]}>
          <TextInput
            style={[
              styles.employeeInput,
              {
                backgroundColor: Colors.surfaceElevated,
                borderColor: Colors.border,
                color: Colors.textPrimary,
                textAlign: isAr ? 'right' : 'left',
              },
            ]}
            value={newEmployeeName}
            onChangeText={setNewEmployeeName}
            placeholder={isAr ? 'أدخل اسم الموظف الجديد' : 'Enter new employee name'}
            placeholderTextColor={Colors.textMuted}
            returnKeyType="done"
            onSubmitEditing={handleAdd}
          />
          <TouchableOpacity
            style={[styles.employeeAddBtn, { backgroundColor: Colors.secondary }]}
            onPress={handleAdd}
            disabled={saving || !newEmployeeName.trim()}
            activeOpacity={0.8}
          >
            {saving ? (
              <ActivityIndicator size="small" color="#000" />
            ) : (
              <Ionicons name="add" size={24} color="#000" />
            )}
          </TouchableOpacity>
        </View>

        {/* Employees List */}
        <FlatList
          data={employees}
          keyExtractor={(_, index) => index.toString()}
          contentContainerStyle={styles.employeeList}
          renderItem={({ item, index }) => (
            <View style={[styles.employeeItem, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
              <View style={styles.employeeItemInner}>
                <View style={styles.employeeAvatarBox}>
                  <Ionicons name="person" size={18} color={Colors.secondary} />
                </View>
                <Text style={[styles.employeeNameText, { color: Colors.textPrimary }]}>{item}</Text>
              </View>
              <TouchableOpacity
                style={styles.employeeDeleteBtn}
                onPress={() => onDelete(index)}
                activeOpacity={0.7}
              >
                <Ionicons name="trash-outline" size={18} color={Colors.error} />
              </TouchableOpacity>
            </View>
          )}
          ListEmptyComponent={
            <View style={styles.emptyEmployees}>
              <Ionicons name="people-outline" size={48} color={Colors.textMuted} />
              <Text style={[styles.emptyEmployeesText, { color: Colors.textPrimary, fontWeight: '700', marginTop: 8 }]}>
                {t('merchant.no_employees', 'No employees added yet')}
              </Text>
              <Text style={{ color: Colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: 4, paddingHorizontal: 20 }}>
                {t('merchant.employees_optional', 'You can add team members to show on your store profile')}
              </Text>
            </View>
          }
        />
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fullScreenModalContainer: {
    flex: 1,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.xl,
    borderBottomWidth: 1,
  },
  modalTitle: {
    ...Typography.h2,
  },
  closeBtn: {
    padding: Spacing.xs,
  },
  employeeAddRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    padding: Spacing.xl,
    borderBottomWidth: 1,
  },
  employeeInput: {
    flex: 1,
    borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg,
    paddingVertical: 12,
    fontSize: 15,
    borderWidth: 1,
  },
  employeeAddBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
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
    borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    marginBottom: Spacing.sm,
    borderWidth: 1,
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
  },
});
