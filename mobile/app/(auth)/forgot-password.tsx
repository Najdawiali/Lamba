import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useThemeColors } from '../../context/ThemeContext';
import { Spacing, BorderRadius, Typography } from '../../constants/theme';
import { t, i18n } from '../../services/i18n';
import { forgotPassword, resetPassword } from '../../services/api';
import KeyboardForm from '../../components/KeyboardForm';
import OtpInput from '../../components/auth/OtpInput';
import PasswordRules, { checkPassword } from '../../components/auth/PasswordRules';
import { messageFromError } from '../../utils/serverMessage';

export default function ForgotPasswordScreen() {
  const Colors = useThemeColors();
  const router = useRouter();
  const isAr = i18n.locale?.startsWith('ar');

  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const networkText = t('login.network_error', "Couldn't reach the server. Check your internet connection and try again.");

  const handleSendCode = async () => {
    if (!email.trim()) {
      Alert.alert(t('common.error', 'Error'), t('auth.enter_email', 'Please enter your email'));
      return;
    }
    setLoading(true);
    try {
      await forgotPassword(email.trim());
      Alert.alert(
        t('auth.code_sent', 'Code Sent'),
        t('auth.reset_code_sent', 'If an account exists, a reset code has been sent to your email.'),
      );
      setStep('code');
    } catch (err: any) {
      Alert.alert(t('common.error', 'Error'), messageFromError(err, !!isAr, { network: networkText, fallback: t('auth.request_failed', 'Request failed') }));
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    const fullCode = code;
    if (fullCode.length !== 6) {
      Alert.alert(t('common.error', 'Error'), t('auth.enter_code', 'Please enter the 6-digit code'));
      return;
    }
    const pw = checkPassword(newPassword, confirmPassword);
    if (!pw.longEnough) {
      Alert.alert(t('common.error', 'Error'), t('auth.password_min', 'Password must be at least 8 characters'));
      return;
    }
    if (!pw.englishOnly) {
      Alert.alert(t('common.error', 'Error'), t('register.password_english_only', 'Password can only contain English letters, numbers and symbols.'));
      return;
    }
    if (!pw.matches) {
      Alert.alert(t('common.error', 'Error'), t('auth.password_mismatch', 'Passwords do not match'));
      return;
    }
    setLoading(true);
    try {
      const resp = await resetPassword(email.trim(), fullCode, newPassword);
      Alert.alert(
        t('common.success', 'Success'),
        t('auth.password_reset_success', 'Password reset successfully!'),
        [{ text: t('common.ok', 'OK'), onPress: () => router.replace('/(auth)/login') }],
      );
    } catch (err: any) {
      Alert.alert(t('common.error', 'Error'), messageFromError(err, !!isAr, { network: networkText, fallback: t('auth.reset_failed', 'Reset failed') }));
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: Colors.background }]} edges={['top']}>
      <View style={{ flex: 1 }}>
        {/* RTL-Safe Header */}
        <View style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: Spacing.lg,
          paddingVertical: Spacing.md,
        }}>
          <TouchableOpacity onPress={() => step === 'code' ? setStep('email') : router.back()} style={{ width: 40, height: 40, justifyContent: 'center', alignItems: 'center' }}>
            <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={22} color={Colors.textPrimary} />
          </TouchableOpacity>
          <View style={{ width: 40 }} />
        </View>

        <KeyboardForm contentContainerStyle={styles.scroll}>

          <View style={styles.header}>
            <Ionicons name="lock-closed-outline" size={48} color="#FF8F00" />
            <Text style={[styles.title, { color: Colors.textPrimary }]}>
              {step === 'email'
                ? t('auth.forgot_password', 'Forgot Password?')
                : t('auth.reset_password', 'Reset Password')}
            </Text>
            <Text style={[styles.subtitle, { color: Colors.textSecondary }]}>
              {step === 'email'
                ? t('auth.forgot_subtitle', 'Enter your email and we\'ll send you a reset code')
                : t('auth.reset_subtitle', 'Enter the code and your new password')}
            </Text>
          </View>

          {step === 'email' ? (
            <View style={styles.form}>
              <TextInput
                style={[styles.input, { backgroundColor: Colors.surface, color: Colors.textPrimary, borderColor: Colors.border }]}
                placeholder={t('auth.email', 'Email')}
                placeholderTextColor={Colors.textMuted}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="email"
                returnKeyType="send"
                onSubmitEditing={handleSendCode}
              />
              <TouchableOpacity
                style={[styles.button, { backgroundColor: '#FF8F00' }, loading && { opacity: 0.5 }]}
                onPress={handleSendCode}
                disabled={loading}
                activeOpacity={0.8}
              >
                {loading ? (
                  <ActivityIndicator color="#FFF" />
                ) : (
                  <Text style={styles.buttonText}>{t('auth.send_code', 'Send Reset Code')}</Text>
                )}
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.form}>
              <OtpInput value={code} onChange={setCode} autoFocus editable={!loading} />

              <View style={[styles.inputWrapper, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
                <TextInput
                  style={[styles.passwordInput, { color: Colors.textPrimary }]}
                  placeholder={t('auth.new_password', 'New Password')}
                  placeholderTextColor={Colors.textMuted}
                  value={newPassword}
                  onChangeText={setNewPassword}
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="new-password"
                  textContentType="newPassword"
                />
                <TouchableOpacity onPress={() => setShowPassword(!showPassword)}>
                  <Ionicons name={showPassword ? 'eye-off' : 'eye'} size={20} color={Colors.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={[styles.inputWrapper, { backgroundColor: Colors.surface, borderColor: Colors.border }]}>
                <TextInput
                  style={[styles.passwordInput, { color: Colors.textPrimary }]}
                  placeholder={t('auth.confirm_password', 'Confirm Password')}
                  placeholderTextColor={Colors.textMuted}
                  value={confirmPassword}
                  onChangeText={setConfirmPassword}
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="new-password"
                  textContentType="newPassword"
                  returnKeyType="done"
                  onSubmitEditing={handleResetPassword}
                />
              </View>

              <PasswordRules password={newPassword} confirm={confirmPassword} />

              <TouchableOpacity
                style={[styles.button, { backgroundColor: '#FF8F00' }, loading && { opacity: 0.5 }]}
                onPress={handleResetPassword}
                disabled={loading}
                activeOpacity={0.8}
              >
                {loading ? (
                  <ActivityIndicator color="#FFF" />
                ) : (
                  <Text style={styles.buttonText}>{t('auth.reset_password', 'Reset Password')}</Text>
                )}
              </TouchableOpacity>
            </View>
          )}
        </KeyboardForm>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  scroll: { padding: Spacing.xl, flexGrow: 1 },
  header: { alignItems: 'center', marginVertical: Spacing.xl },
  title: { ...Typography.h2, marginTop: Spacing.md, textAlign: 'center' },
  subtitle: { ...Typography.body, marginTop: Spacing.sm, textAlign: 'center', lineHeight: 22 },
  form: { marginTop: Spacing.xl, gap: Spacing.lg },
  input: {
    borderWidth: 1,
    borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.lg,
    paddingHorizontal: Spacing.lg,
    fontSize: 16,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg,
  },
  passwordInput: {
    flex: 1,
    paddingVertical: Spacing.lg,
    fontSize: 16,
  },
  button: {
    backgroundColor: '#FF8F00',
    paddingVertical: Spacing.lg,
    borderRadius: BorderRadius.xl,
    alignItems: 'center',
  },
  buttonText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
});
