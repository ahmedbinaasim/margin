// Firebase Web SDK init. Lazy-imported from the sign-in handler so the
// ~80 KB chunk only loads when the user clicks "Continue with Google".

import { initializeApp, getApps } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY!,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN!,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID!,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID!,
};

export const firebaseApp = getApps()[0] ?? initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);
