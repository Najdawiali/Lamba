/**
 * Lamba API — Offers
 *
 * Merchant offer CRUD (percentage, fixed, buy-x-get-y, quantity-price)
 * and customer-facing offer discovery feed.
 */

import api from './client';
import type { AddressParts } from '../../utils/jordanAddress';

// ── Merchant Offer Types ───────────────────────────────────────
export interface OfferConfig {
  percent?: number;
  amount?: number;
  buy?: number;
  get?: number;
  quantity?: number;
  price?: number;
}

export interface OfferResponse {
  id: string;
  market_id: string;
  market_item_id: string;
  offer_type: 'percentage' | 'fixed_amount' | 'buy_x_get_y' | 'quantity_price';
  config: OfferConfig;
  description?: string;
  is_active: boolean;
  starts_at: string;
  expires_at?: string;
  created_at: string;
  item_name?: string;
  item_name_ar?: string;
  item_price?: number;
  item_image_url?: string;
}

export interface OfferCreatePayload {
  market_item_id: string;
  offer_type: string;
  config: OfferConfig;
  description?: string;
  expires_at?: string;
}

// ── Customer Offer Types ───────────────────────────────────────
export interface CustomerSpecialOfferResponse {
  id: string;
  market_item_id: string;
  offer_type: string;
  config?: Record<string, any> | null;
  discount_percentage: number | null;
  description: string | null;
  offer_summary?: string | null;
  power: number;
  is_active: boolean;
  created_at: string;
  expires_at?: string | null;
  product_id: string;
  product_name: string;
  product_name_ar?: string | null;
  product_name_en?: string | null;
  product_description: string | null;
  price: number | null;
  discounted_price?: number | null;
  category: string | null;
  category_name_ar?: string | null;
  category_name_en?: string | null;
  image_url: string | null;
  stock_count: number;
  in_stock: boolean;
  shop_id: string;
  shop_name: string;
  shop_address: string;
  shop_address_parts?: AddressParts | null;
  latitude: number;
  longitude: number;
  shop_is_open: boolean;
  distance_km: number;
  sorting_score: number;
}

export interface CustomerOffersFilters {
  query?: string;
  offer_type?: string;
  max_distance_km?: number;
  category_id?: string;
}

// ── Merchant Functions ─────────────────────────────────────────
export async function createOffer(payload: OfferCreatePayload): Promise<OfferResponse> {
  const { data } = await api.post<OfferResponse>('/api/v1/merchant/offers', payload);
  return data;
}

export async function getOffers(): Promise<OfferResponse[]> {
  const { data } = await api.get<OfferResponse[]>('/api/v1/merchant/offers');
  return data;
}

export async function updateOffer(
  offerId: string, payload: { is_active?: boolean; description?: string; expires_at?: string },
): Promise<OfferResponse> {
  const { data } = await api.patch<OfferResponse>(`/api/v1/merchant/offers/${offerId}`, payload);
  return data;
}

export async function deleteOffer(offerId: string): Promise<void> {
  await api.delete(`/api/v1/merchant/offers/${offerId}`);
}

// ── Customer Functions ─────────────────────────────────────────
export async function getCustomerSpecialOffers(
  latitude: number, longitude: number, filters?: CustomerOffersFilters,
): Promise<CustomerSpecialOfferResponse[]> {
  try {
    const params: Record<string, any> = { latitude, longitude };
    if (filters) {
      if (filters.query) params.query = filters.query;
      if (filters.offer_type && filters.offer_type !== 'All') params.offer_type = filters.offer_type;
      if (filters.max_distance_km !== undefined) params.max_distance_km = filters.max_distance_km;
      if (filters.category_id) params.category_id = filters.category_id;
    }
    const { data } = await api.get<CustomerSpecialOfferResponse[]>('/api/v1/customer/offers', { params });
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}
