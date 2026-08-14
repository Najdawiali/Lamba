import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, RefreshControl, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getConversations } from '../../../services/api';
import { useThemeColors } from '../../../context/ThemeContext';

export default function InboxScreen() {
  const Colors = useThemeColors();
  const router = useRouter();
  const [conversations, setConversations] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchConversations = useCallback(async () => {
    try {
      const res = await getConversations();
      setConversations(res.data || []);
    } catch (e) {
      console.log('Failed to load conversations', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchConversations();
  };

  const formatTime = (dateStr: string) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'الآن';
    if (diffMins < 60) return `قبل ${diffMins} د`;
    if (diffMins < 1440) return `قبل ${Math.floor(diffMins / 60)} س`;
    return date.toLocaleDateString('ar-JO');
  };

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator color={Colors.primary} size="large" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background }} edges={['top']}>
      <Text style={{
        color: Colors.textPrimary,
        fontSize: 22,
        fontWeight: '700',
        textAlign: 'center',
        paddingVertical: 16,
        borderBottomWidth: 1,
        borderBottomColor: Colors.border,
      }}>
        الرسائل
      </Text>

      {conversations.length === 0 ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 }}>
          <Ionicons name="chatbubbles-outline" size={64} color={Colors.textSecondary} style={{ opacity: 0.4, marginBottom: 16 }} />
          <Text style={{ color: Colors.textPrimary, fontSize: 18, fontWeight: '700', textAlign: 'center', marginBottom: 8 }}>
            لا توجد محادثات
          </Text>
          <Text style={{ color: Colors.textSecondary, fontSize: 14, textAlign: 'center', lineHeight: 22 }}>
            ابدأ محادثة مع أي متجر من صفحة المنتج أو المتجر
          </Text>
        </View>
      ) : (
        <FlatList
          data={conversations}
          keyExtractor={(item) => item.id}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.primary} />
          }
          renderItem={({ item }) => (
            <TouchableOpacity
              onPress={() => router.push({
                pathname: '/(customer)/chat/[id]',
                params: {
                  id: item.id,
                  marketName: item.market_name_ar || item.market_name,
                },
              })}
              style={{
                flexDirection: 'row',
                padding: 16,
                borderBottomWidth: 1,
                borderBottomColor: Colors.border,
                alignItems: 'center',
              }}
            >
              <View style={{
                width: 48, height: 48,
                borderRadius: 24,
                backgroundColor: Colors.primary + '20',
                justifyContent: 'center',
                alignItems: 'center',
                marginLeft: 12,
              }}>
                <Ionicons name="storefront" size={22} color={Colors.primary} />
              </View>

              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Text style={{ color: Colors.textSecondary, fontSize: 11 }}>
                    {formatTime(item.last_message_at)}
                  </Text>
                  <Text style={{ color: Colors.textPrimary, fontSize: 15, fontWeight: '600', textAlign: 'right' }}>
                    {item.market_name_ar || item.market_name}
                  </Text>
                </View>
                {(item.product_name_ar || item.product_name) && (
                  <Text style={{ color: Colors.primary, fontSize: 12, textAlign: 'right', marginBottom: 2 }}>
                    {item.product_name_ar || item.product_name}
                  </Text>
                )}
                <Text
                  style={{ color: Colors.textSecondary, fontSize: 13, textAlign: 'right' }}
                  numberOfLines={1}
                >
                  {item.last_message || '...'}
                </Text>
              </View>
            </TouchableOpacity>
          )}
        />
      )}
    </SafeAreaView>
  );
}