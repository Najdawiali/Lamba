import { Stack } from 'expo-router';
import { useThemeColors } from '../../context/ThemeContext';

export default function AuthLayout() {
  const Colors = useThemeColors();
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: Colors.background },
        animation: 'fade',
      }}
    />
  );
}