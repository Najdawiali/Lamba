import { Linking, Alert } from 'react-native';
import { t } from '../services/i18n';

export const openWhatsApp = (phone?: string | null, message?: string) => {
  if (!phone || !phone.trim()) {
    Alert.alert(
      t('market.whatsapp_unavailable', 'واتساب غير متوفر'),
      t('market.whatsapp_no_phone', 'رقم هاتف المتجر غير متوفر للتواصل حالياً')
    );
    return;
  }

  // Clean phone number — remove spaces, dashes, parentheses, plus
  let cleaned = phone.replace(/[\s\-()+]/g, '');

  // Convert Jordanian local format to international
  if (cleaned.startsWith('0')) {
    cleaned = '962' + cleaned.substring(1); // 07x → 9627x
  }
  if (!cleaned.startsWith('962')) {
    cleaned = '962' + cleaned;
  }

  const encodedMsg = message ? `?text=${encodeURIComponent(message)}` : '';
  const url = `https://wa.me/${cleaned}${encodedMsg}`;

  Linking.canOpenURL(url).then((supported) => {
    if (supported) {
      Linking.openURL(url);
    } else {
      Alert.alert(
        t('market.whatsapp_unavailable', 'واتساب غير متوفر'),
        t('market.whatsapp_install', 'يرجى تثبيت واتساب للتواصل مع المتجر')
      );
    }
  }).catch(() => {
    Linking.openURL(url).catch(() => {
      Alert.alert(
        t('market.whatsapp_unavailable', 'واتساب غير متوفر'),
        t('market.whatsapp_install', 'يرجى تثبيت واتساب للتواصل مع المتجر')
      );
    });
  });
};
