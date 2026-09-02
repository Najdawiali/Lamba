/**
 * Lamba API — Barrel Export
 *
 * Re-exports all domain modules so existing imports like
 *   import { getMyMarket, SearchResultItem } from '../services/api'
 * continue to work without changes.
 */

export * from './client';
export * from './auth';
export * from './merchant';
export * from './customer';
export * from './search';
export * from './offers';
export * from './chat';
export { default } from './client';
