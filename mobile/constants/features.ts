/**
 * Feature switches for the mobile app. Change a value here and rebuild.
 *
 * PHONE_AUTH_ENABLED: sign-up and sign-in with a phone number.
 *   Off until phone verification codes can be delivered: WhatsApp authentication
 *   templates require a Meta-verified business. The backend has a matching switch
 *   (PHONE_SIGNUP_ENABLED in backend/.env). Turn both on together.
 *   While off, the app shows no phone sign-in options or wording anywhere; the
 *   phone code paths stay in place, unused, so enabling them is this one change.
 */
export const PHONE_AUTH_ENABLED = false;
