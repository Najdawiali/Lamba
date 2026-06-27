import React, { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getChatSessions, getChatMessages, sendChatMessage, getUser, ChatSession, ChatMessage } from '../../services/api';
import { Colors, Spacing, Typography, BorderRadius, Shadows } from '../../constants/theme';
import { t } from '../../services/i18n';

export default function MerchantInboxScreen() {
  const router = useRouter();
  const { sessionId: querySessionId } = useLocalSearchParams<{ sessionId?: string }>();
  
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Chat thread states
  const [selectedSession, setSelectedSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  
  const flatListRef = useRef<FlatList>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const [userId, setUserId] = useState<string | null>(null);

  // Load current user ID for message alignment
  useEffect(() => {
    getUser().then(u => { if (u?.id) setUserId(u.id); });
  }, []);

  // Load chat sessions on mount
  useEffect(() => {
    fetchSessions();
    return () => stopPolling();
  }, []);

  // Listen for navigation with query parameter
  useEffect(() => {
    if (querySessionId && sessions.length > 0) {
      const match = sessions.find(s => s.id === querySessionId);
      if (match) {
        handleSelectSession(match);
      }
    }
  }, [querySessionId, sessions]);

  const fetchSessions = async () => {
    try {
      const data = await getChatSessions();
      setSessions(data);
    } catch (err) {
      console.error('Failed to load chat sessions', err);
    } finally {
      setLoading(false);
    }
  };

  const startPolling = (sessionId: string) => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const data = await getChatMessages(sessionId);
        setMessages(data);
      } catch (err) {
        console.error('Polling failed:', err);
      }
    }, 10000);
  };

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const handleSelectSession = async (session: ChatSession) => {
    setSelectedSession(session);
    setLoadingMessages(true);
    stopPolling();
    try {
      const data = await getChatMessages(session.id);
      setMessages(data);
      startPolling(session.id);
    } catch (err) {
      console.error('Failed to fetch messages', err);
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleBackToInbox = () => {
    setSelectedSession(null);
    setMessages([]);
    stopPolling();
    fetchSessions(); // Refresh list to get new last_messages
    // Clean query param
    router.replace('/(merchant)/inbox');
  };

  const handleSend = async () => {
    if (!inputText.trim() || !selectedSession || sending) return;
    
    setSending(true);
    try {
      const newMsg = await sendChatMessage(selectedSession.id, inputText.trim());
      setMessages(prev => [...prev, newMsg]);
      setInputText('');
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (err) {
      console.error('Failed to send message', err);
    } finally {
      setSending(false);
    }
  };

  const renderSessionCard = ({ item }: { item: ChatSession }) => {
    const initial = (item.partner_name || 'C').charAt(0).toUpperCase();
    const timestamp = item.updated_at
      ? new Date(item.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '';
    return (
      <TouchableOpacity
        style={styles.chatCard}
        onPress={() => handleSelectSession(item)}
        activeOpacity={0.7}
      >
        <View style={styles.avatar}>
          <Text style={styles.avatarInitial}>{initial}</Text>
        </View>
        <View style={styles.chatInfo}>
          <View style={styles.chatRow}>
            <Text style={styles.partnerName} numberOfLines={1}>{item.partner_name || 'Customer'}</Text>
            <Text style={styles.timestamp}>{timestamp}</Text>
          </View>
          <View style={styles.chatRow}>
            <Text style={styles.lastMessage} numberOfLines={2}>
              {item.last_message || t('inbox.tap_to_view', 'Tap to view conversation')}
            </Text>
            {item.unread_count > 0 && (
              <View style={styles.unreadBadge}>
                <Text style={styles.unreadBadgeText}>{item.unread_count}</Text>
              </View>
            )}
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  const renderMessageBubble = ({ item }: { item: ChatMessage }) => {
    const isMe = item.sender_id === userId;
    return (
      <View style={[styles.messageBubble, isMe ? styles.messageMe : styles.messageThem]}>
        <Text style={[styles.messageText, isMe ? styles.messageTextMe : styles.messageTextThem]}>
          {item.text}
        </Text>
      </View>
    );
  };

  // ── Render Unified View ────────────────────────────────────────

  if (selectedSession) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Chat Thread Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={handleBackToInbox} style={styles.backBtn} activeOpacity={0.7}>
            <Ionicons name="arrow-back" size={24} color={Colors.textPrimary} />
          </TouchableOpacity>
          <Text style={styles.title} numberOfLines={1}>{selectedSession.partner_name || t('inbox.chat_with_customer', 'Chat with Customer')}</Text>
          <View style={{ width: 40 }} />
        </View>

        <KeyboardAvoidingView 
          style={{ flex: 1 }} 
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          {loadingMessages ? (
            <View style={styles.center}>
              <ActivityIndicator size="large" color={Colors.primary} />
            </View>
          ) : (
            <FlatList
              ref={flatListRef}
              data={messages}
              keyExtractor={item => item.id}
              renderItem={renderMessageBubble}
              contentContainerStyle={styles.listContent}
              onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
              onLayout={() => flatListRef.current?.scrollToEnd({ animated: true })}
            />
          )}

          <View style={styles.inputContainer}>
            <TextInput
              style={styles.input}
              value={inputText}
              onChangeText={setInputText}
              placeholder={t('inbox.type_message')}
              placeholderTextColor={Colors.textMuted}
              multiline
            />
            <TouchableOpacity 
              style={[styles.sendBtn, !inputText.trim() && styles.sendBtnDisabled]} 
              onPress={handleSend}
              disabled={!inputText.trim() || sending}
              activeOpacity={0.7}
            >
              {sending ? (
                <ActivityIndicator size="small" color="#FFF" />
              ) : (
                <Ionicons name="send" size={20} color="#FFF" />
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  // ── Inbox List View ──
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.inboxHeader}>
        <Text style={styles.inboxTitle}>{t('inbox.title')}</Text>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : sessions.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyIconCircle}>
            <Ionicons name="mail-outline" size={36} color={Colors.textMuted} />
          </View>
          <Text style={styles.emptyText}>{t('inbox.empty')}</Text>
          <Text style={styles.emptySubtext}>{t('inbox.empty_desc')}</Text>
        </View>
      ) : (
        <FlatList
          data={sessions}
          keyExtractor={(item) => item.id}
          renderItem={renderSessionCard}
          contentContainerStyle={styles.listContent}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.surface,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center' },
  title: { ...Typography.h1, color: Colors.textPrimary, flex: 1, textAlign: 'center' },
  inboxHeader: {
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.lg,
    paddingBottom: Spacing.md,
  },
  inboxTitle: {
    fontSize: 32,
    fontWeight: '700' as const,
    color: Colors.textPrimary,
  },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  emptyIconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    marginBottom: Spacing.md,
  },
  emptyText: { fontSize: 18, fontWeight: '600' as const, color: Colors.textPrimary, marginTop: Spacing.md },
  emptySubtext: { fontSize: 14, color: Colors.textSecondary, textAlign: 'center' as const, marginTop: Spacing.sm },
  listContent: { padding: Spacing.md, paddingBottom: Spacing.xl },
  
  // Inbox Card Styles
  chatCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.primary,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    marginRight: Spacing.md,
  },
  avatarInitial: {
    fontSize: 16,
    fontWeight: '700' as const,
    color: '#FFFFFF',
  },
  chatInfo: { flex: 1 },
  chatRow: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    marginBottom: 2,
  },
  partnerName: { fontSize: 15, fontWeight: '600' as const, color: Colors.textPrimary, flex: 1 },
  lastMessage: { fontSize: 13, color: Colors.textMuted, flex: 1 },
  timestamp: { fontSize: 12, color: Colors.textMuted, marginLeft: Spacing.sm },
  unreadBadge: {
    backgroundColor: Colors.secondary,
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    paddingHorizontal: 6,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    marginLeft: Spacing.sm,
  },
  unreadBadgeText: {
    fontSize: 11,
    fontWeight: '700' as const,
    color: '#FFFFFF',
  },

  // Chat Thread Bubble Styles
  messageBubble: {
    maxWidth: '80%',
    padding: Spacing.md,
    borderRadius: BorderRadius.lg,
    marginBottom: Spacing.sm,
  },
  messageMe: {
    alignSelf: 'flex-end',
    backgroundColor: Colors.primary,
    borderBottomRightRadius: 4,
  },
  messageThem: {
    alignSelf: 'flex-start',
    backgroundColor: Colors.surfaceElevated,
    borderBottomLeftRadius: 4,
  },
  messageText: { ...Typography.body },
  messageTextMe: { color: Colors.textOnPrimary },
  messageTextThem: { color: Colors.textPrimary },
  
  // Chat Thread Input Styles
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.05)',
  },
  input: {
    flex: 1,
    backgroundColor: Colors.background,
    color: Colors.textPrimary,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: 22,
    paddingHorizontal: Spacing.md,
    paddingTop: 12,
    paddingBottom: 12,
    marginRight: Spacing.sm,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    ...Shadows.small,
  },
  sendBtnDisabled: {
    backgroundColor: Colors.surfaceElevated,
    opacity: 0.5,
  },
});
