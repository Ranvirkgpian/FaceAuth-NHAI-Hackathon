import { initializeApp } from 'firebase/app';
import { getFirestore, collection, addDoc } from 'firebase/firestore';

const firebaseConfig = {
  apiKey: "AIzaSyApLbyfUQfeqOvxI467ze9-Fkp0Ow-c818",
  authDomain: "faceauthapp-28d3a.firebaseapp.com",
  projectId: "faceauthapp-28d3a",
  storageBucket: "faceauthapp-28d3a.firebasestorage.app",
  messagingSenderId: "49542684964",
  appId: "1:49542684964:web:817f16a920025285bf13b1"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);

export const syncToFirebase = async (records: any[]) => {
  try {
    for (const record of records) {
      await addDoc(collection(db, 'attendance'), {
        name: record.name,
        timestamp: record.timestamp,
        synced: true
      });
    }
    console.log(`✅ Synced ${records.length} records to Firebase`);
    return true;
  } catch (e) {
    console.log('Firebase sync error:', e);
    return false;
  }
};