import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, KeyboardAvoidingView, Platform, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getMessages, sendMessage, getUser } from '../../../services/api';
import { useThemeColors } from '../../../context/ThemeContext';
import { Spacing, Typography } from '../../../constants/theme';
import { i18n } from '../../../services/i18n';

export default function ChatScreen() {
  const Colors = useThemeColors();
  const isAr = i18n.locale?.startsWith('ar');
  const { id, marketName, suggestion } = useLocalSearchParams<{ id: string; marketName?: string; suggestion?: string }>();
  const router = useRouter();
  const [messages, setMessages] = useState<any[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [myUserId, setMyUserId] = useState<string>('');
  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    getUser().then(u => { if (u?.id) setMyUserId(u.id); });
  }, []);

  const fetchMessages = useCallback(async () => {
    if (!id) return;
    try {
      const res = await getMessages(id as string);
      setMessages(res.data || []);
    } catch (e) {
      console.log('Failed to load messages', e);
    } finally {
      setRefreshing(false);
    }
  }, [id]);

  useEffect(() => {
    fetchMessages();
    const interval = setInterval(fetchMessages, 10000);
    return () => clearInterval(interval);
  }, [id, fetchMessages]);

  // Pre-fill the input with the suggestion on first load
  useEffect(() => {
    if (suggestion && typeof suggestion === 'string') {
      setNewMessage(suggestion);
    }
  }, []);

  const handleSend = async () => {
    if (!newMessage.trim() || sending || !id) return;

    const messageText = newMessage.trim();
    setSending(true);
    setNewMessage('');

    // Optimistic update
    const tempMsg = {
      id: `temp-${Date.now()}`,
      sender_id: 'me',
      is_me: true,
      text: messageText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempMsg]);

    try {
      const res = await sendMessage(id as string, messageText);
      // Replace temp message with real one
      setMessages((prev) =>
        prev.map((m) => (m.id === tempMsg.id ? res.data : m))
      );
    } catch (e) {
      // Remove temp message on failure
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id));
      setNewMessage(messageText);
      console.log('Failed to send message', e);
    } finally {
      setSending(false);
    }

    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  };

  const renderMessage = ({ item }: { item: any }) => {
    const isMine = Boolean(item.is_me || (myUserId && item.sender_id === myUserId));
    return (
      <View
        style={{
          alignSelf: isMine ? 'flex-end' : 'flex-start',
          backgroundColor: isMine ? Colors.primary : Colors.surface,
          borderRadius: 16,
          borderBottomRightRadius: isMine ? 4 : 16,
          borderBottomLeftRadius: isMine ? 16 : 4,
          borderWidth: isMine ? 0 : 1,
          borderColor: isMine ? 'transparent' : Colors.border,
          paddingVertical: 10,
          paddingHorizontal: 14,
          maxWidth: '78%',
          marginVertical: 4,
          marginHorizontal: 16,
        }}
      >
        <Text
          style={{
            color: isMine ? '#FFFFFF' : Colors.textPrimary,
            fontSize: 15,
            lineHeight: 20,
            textAlign: isAr ? 'right' : 'left',
          }}
        >
          {item.text}
        </Text>
        <Text
          style={{
            color: isMine ? 'rgba(255,255,255,0.7)' : Colors.textSecondary,
            fontSize: 10,
            textAlign: 'left',
            marginTop: 4,
          }}
        >
          {item.created_at ? new Date(item.created_at).toLocaleTimeString(isAr ? 'ar-JO' : 'en-US', {
            hour: '2-digit',
            minute: '2-digit',
          }) : ''}
        </Text>
      </View>
    );
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: Colors.background }} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {/* Header */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: Spacing.lg,
            paddingVertical: Spacing.md,
            borderBottomWidth: 1,
            borderBottomColor: Colors.border,
            backgroundColor: Colors.surface,
          }}
        >
          <TouchableOpacity onPress={() => router.back()} style={{ width: 40, height: 40, justifyContent: 'center', alignItems: 'center' }}>
            <Ionicons name={isAr ? 'arrow-forward' : 'arrow-back'} size={22} color={Colors.textPrimary} />
          </TouchableOpacity>
          <Text style={[Typography.h3, { color: Colors.textPrimary, textAlign: 'center', flex: 1 }]}>
            {decodeURIComponent((marketName as string) || '')}
          </Text>
          <View style={{ width: 40 }} />
        </View>

        {/* Messages list */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={renderMessage}
          contentContainerStyle={{ paddingVertical: 8, flexGrow: 1 }}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => {
                setRefreshing(true);
                fetchMessages();
              }}
              tintColor={Colors.primary}
            />
          }
          ListEmptyComponent={
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
              <Text style={{ color: Colors.textSecondary, fontSize: 14 }}>
                ابدأ المحادثة...
              </Text>
            </View>
          }
        />

        {/* Input bar */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            paddingHorizontal: 12,
            paddingVertical: 8,
            borderTopWidth: 1,
            borderTopColor: Colors.border,
            backgroundColor: Colors.surface,
            gap: 8,
          }}
        >
          <TouchableOpacity
            onPress={handleSend}
            disabled={!newMessage.trim() || sending}
            style={{
              width: 40,
              height: 40,
              borderRadius: 20,
              backgroundColor: newMessage.trim() ? Colors.primary : Colors.surfaceElevated,
              justifyContent: 'center',
              alignItems: 'center',
            }}
          >
            <Ionicons
              name="send"
              size={18}
              color={newMessage.trim() ? '#FFF' : Colors.textMuted}
            />
          </TouchableOpacity>
          <TextInput
            value={newMessage}
            onChangeText={setNewMessage}
            placeholder="اكتب رسالتك..."
            placeholderTextColor={Colors.textMuted}
            multiline
            style={{
              flex: 1,
              backgroundColor: Colors.surfaceElevated,
              borderRadius: 20,
              paddingHorizontal: 16,
              paddingVertical: 10,
              color: Colors.textPrimary,
              fontSize: 14,
              textAlign: 'right',
              maxHeight: 100,
            }}
            onSubmitEditing={handleSend}
          />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
