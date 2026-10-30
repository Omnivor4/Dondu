/**
 * Dondu — Firebase Realtime Sync Client Module
 * Supports plug-and-play Firebase Firestore integration with automatic backend fallback
 */
window.DonduFirebase = (() => {
  "use strict";

  // Project configuration for Firebase
  const firebaseConfig = window.DONDU_FIREBASE_CONFIG || {
    apiKey: "",
    authDomain: "dondu-4421f.firebaseapp.com",
    projectId: "dondu-4421f",
    storageBucket: "dondu-4421f.firebasestorage.app",
    messagingSenderId: "",
    appId: ""
  };

  let dbInstance = null;
  const isConfigured = Boolean(firebaseConfig.projectId && firebaseConfig.apiKey);

  async function initFirebase() {
    if (!isConfigured) {
      return null;
    }
    try {
      const { initializeApp } = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js");
      const { getFirestore } = await import("https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js");
      const app = initializeApp(firebaseConfig);
      dbInstance = getFirestore(app);
      return dbInstance;
    } catch (_) {
      return null;
    }
  }

  return {
    isConfigured,
    initFirebase,
    getConfig: () => ({ ...firebaseConfig })
  };
})();
