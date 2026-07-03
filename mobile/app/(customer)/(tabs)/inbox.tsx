import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getChatSessions, getChatMessages, sendChatMessage, getUser, ChatSession, ChatMessage } from '../../../services/api';
import { Spacing, Typography, BorderRadius, Shadows } from '../../../constants/theme';
import { useThemeColors } from '../../../context/ThemeContext';
import { t, i18n } from '../../../services/i18n';
import { formatRelativeTime } from '../../../services/utils';

export default function CustomerInboxScreen() {
  const Colors = useThemeColors();
  const router = useRouter();
  const { sessionId: querySessionId } = useLocalSearchParams<{ sessionId?: string }>();
  const isAr = i18n.locale.includes('ar');

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

  const styles = useMemo(() => StyleSheet.create({
    container: { flex: 1, backgroundColor: Colors.background },
    headerInbox: {
      paddingHorizontal: Spacing.xl,
      paddingVertical: Spacing.lg,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: Spacing.lg,
      paddingVertical: Spacing.md,
      borderBottomWidth: 1,
      borderBottomColor: Colors.border,
    },
    backBtn: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...Typography.h1, color: Colors.textPrimary },
    titleThread: { ...Typography.h1, color: Colors.textPrimary, flex: 1, textAlign: 'center', fontSize: 20 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },

    // Empty State
    emptyContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      paddingHorizontal: Spacing.xxl,
    },
    emptyIconCircle: {
      width: 80,
      height: 80,
      borderRadius: 40,
      backgroundColor: Colors.surfaceElevated,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: Spacing.xl,
    },
    emptyText: { ...Typography.h2, color: Colors.textPrimary, marginBottom: Spacing.sm },
    emptySubtext: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginBottom: Spacing.xxl },
    exploreBtn: {
      backgroundColor: Colors.surfaceElevated,
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.xl,
      borderRadius: BorderRadius.full,
      borderWidth: 1,
      borderColor: Colors.border,
    },
    exploreBtnText: {
      ...Typography.button,
      color: Colors.primary,
    },

    listContent: { padding: Spacing.md, paddingBottom: Spacing.xl },

    // Inbox Card Styles
    chatCard: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: Spacing.md,
      paddingHorizontal: Spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: Colors.border,
    },
    cardLeft: {
      flexDirection: 'row',
      alignItems: 'center',
    },
    unreadDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: Colors.primary,
      marginRight: 8,
    },
    avatar: {
      width: 44,
      height: 44,
      borderRadius: 22,
      backgroundColor: 'rgba(108, 99, 255, 0.1)',
      justifyContent: 'center',
      alignItems: 'center',
      marginRight: Spacing.md,
    },
    chatInfo: { flex: 1, marginRight: Spacing.sm },
    partnerName: { ...Typography.body, fontWeight: '600', color: Colors.textPrimary, marginBottom: 2 },
    lastMessage: { ...Typography.caption, color: Colors.textSecondary },
    timestamp: {
      ...Typography.caption,
      color: Colors.textMuted,
      alignSelf: 'flex-start',
      marginTop: 4,
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
      borderTopColor: Colors.border,
    },
    input: {
      flex: 1,
      backgroundColor: Colors.surfaceElevated,
      color: Colors.textPrimary,
      minHeight: 44,
      maxHeight: 120,
      borderRadius: 22,
      paddingHorizontal: Spacing.lg,
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
  }), [Colors]);

  // Load current user ID for message alignment
  useEffect(() => {
    getUser().then(u => { if (u?.id) setUserId(u.id); });
  }, []);

  // Load chat sessions on mount
  useEffect(() => {
    fetchSessions();
    return () => stopPolling();
  }, []);

  // Listen for navigation with query parameter (e.g. from Product Card link)
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
    } catch (err: any) {
      if (err?.response?.status === 401) {
        console.warn('Failed to load chat sessions due to 401 Unauthorized. Logging out.');
        router.replace('/(auth)/gateway');
        return;
      }
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
    router.replace('/(customer)/inbox');
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
    // Unread badge — driven by the backend's real per-session unread_count
    // (messages from the other party not yet marked is_read), NOT a placeholder.
    const hasUnread = (item.unread_count ?? 0) > 0;

    return (
      <TouchableOpacity
        style={styles.chatCard}
        onPress={() => handleSelectSession(item)}
        activeOpacity={0.7}
      >
        <View style={styles.cardLeft}>
          {hasUnread && <View style={styles.unreadDot} />}
          <View style={styles.avatar}>
            <Ionicons name="storefront-outline" size={24} color={Colors.primary} />
          </View>
        </View>

        <View style={styles.chatInfo}>
          <Text style={styles.partnerName}>{item.partner_name || t('inbox.store')}</Text>
          <Text style={styles.lastMessage} numberOfLines={1}>
            {item.last_message || t('inbox.tap_to_view')}
          </Text>
        </View>

        {item.updated_at && (
          <Text style={styles.timestamp}>
            {formatRelativeTime(item.updated_at, isAr)}
          </Text>
        )}
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
          <Text style={styles.titleThread} numberOfLines={1}>{selectedSession.partner_name || 'Chat with Store'}</Text>
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
      <View style={styles.headerInbox}>
        <Text style={styles.title}>{t('inbox.title')}</Text>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : sessions.length === 0 ? (
        <View style={styles.emptyContainer}>
          <View style={styles.emptyIconCircle}>
            <Ionicons name="chatbubbles-outline" size={40} color={Colors.textSecondary} />
          </View>
          <Text style={styles.emptyText}>{t('inbox.empty')}</Text>
          <Text style={styles.emptySubtext}>{t('inbox.empty_desc')}</Text>
          <TouchableOpacity
            style={styles.exploreBtn}
            activeOpacity={0.8}
            onPress={() => router.replace('/(customer)/search')}
          >
            <Text style={styles.exploreBtnText}>{t('inbox.explore_shops')}</Text>
          </TouchableOpacity>
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