/**
 * Lamba API — Chat (V2 Conversations)
 */

import api from './client';

export const startConversation = (marketId: string, message?: string, productId?: string) =>
  api.post('/api/v1/chat/conversations', {
    market_id: marketId,
    ...(message ? { message } : {}),
    ...(productId ? { product_id: productId } : {}),
  });

export const getConversations = () =>
  api.get('/api/v1/chat/conversations');

export const getMessages = (conversationId: string) =>
  api.get(`/api/v1/chat/conversations/${conversationId}/messages`);

export const sendMessage = (conversationId: string, text: string) =>
  api.post(`/api/v1/chat/conversations/${conversationId}/messages`, { text });
