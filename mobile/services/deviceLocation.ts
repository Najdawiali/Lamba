/**
 * The phone's location services for the store location form: one GPS fix (with its accuracy) and the
 * phone's own reverse geocoder, turned into an editable prefill. The rules for reading the geocoder's
 * answer are in utils/jordanAddress.ts.
 */

import * as Location from 'expo-location';
import { EMPTY_PREFILL, prefillFromDeviceAddress, type AddressPrefill } from '../utils/jordanAddress';

export interface GpsFix {
  latitude: number;
  longitude: number;
  /** Metres, or null when the device does not say. */
  accuracy: number | null;
}

export class LocationPermissionDenied extends Error {}
export class LocationTimeout extends Error {}

const FIX_TIMEOUT_MS = 20000;

/** Asks for permission if needed, then returns one high-accuracy GPS fix. */
export async function getCurrentFix(): Promise<GpsFix> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') throw new LocationPermissionDenied();

  const position = await Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
    new Promise<never>((_, reject) => setTimeout(() => reject(new LocationTimeout()), FIX_TIMEOUT_MS)),
  ]);
  const accuracy = position.coords.accuracy;
  return {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: typeof accuracy === 'number' && Number.isFinite(accuracy) ? accuracy : null,
  };
}

/** The phone's geocoder as governorate / area / street suggestions; empty ones when it has nothing or fails. */
export async function reverseGeocodeDevice(latitude: number, longitude: number): Promise<AddressPrefill> {
  try {
    const [geo] = await Location.reverseGeocodeAsync({ latitude, longitude });
    return prefillFromDeviceAddress(geo);
  } catch {
    return { ...EMPTY_PREFILL };
  }
}
