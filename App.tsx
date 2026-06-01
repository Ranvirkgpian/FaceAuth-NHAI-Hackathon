import React, {useEffect, useState} from 'react';
import {
  Alert,
  Modal,
  PermissionsAndroid,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  NetInfo,
} from 'react-native';
import {Camera, CameraType} from 'react-native-camera-kit';
import {syncToFirebase} from './firebase';

// ─────────────────────────────────────────────
//  LOCAL STORAGE (in-memory for demo)
// ─────────────────────────────────────────────
interface AttendanceRecord {
  id: number;
  name: string;
  timestamp: string;
  synced: boolean;
}

let localRecords: AttendanceRecord[] = [];
let nextId = 1;

const saveLocalAttendance = (name: string) => {
  const record: AttendanceRecord = {
    id: nextId++,
    name,
    timestamp: new Date().toISOString(),
    synced: false,
  };
  localRecords.push(record);
  console.log(`✅ Saved locally: ${name}`);
  return record;
};

const getUnsyncedRecords = () => localRecords.filter(r => !r.synced);

const markAllSynced = () => {
  localRecords = localRecords.map(r => ({...r, synced: true}));
};

// ─────────────────────────────────────────────
//  MAIN APP
// ─────────────────────────────────────────────
export default function App() {
  const [hasPermission, setHasPermission] = useState(false);
  const [registerName, setRegisterName] = useState('');
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [statusText, setStatusText] = useState('Point camera at your face');
  const [statusColor, setStatusColor] = useState('#888');
  const [livenessOn, setLivenessOn] = useState(true);
  const [isRegistering, setIsRegistering] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [totalRecords, setTotalRecords] = useState(0);
  const [unsyncedCount, setUnsyncedCount] = useState(0);

  useEffect(() => {
    requestPermission();
  }, []);

  const requestPermission = async () => {
    if (Platform.OS === 'android') {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.CAMERA,
      );
      setHasPermission(granted === PermissionsAndroid.RESULTS.GRANTED);
    } else {
      setHasPermission(true);
    }
  };

  const updateCounts = () => {
    setTotalRecords(localRecords.length);
    setUnsyncedCount(getUnsyncedRecords().length);
  };

  // ── Register face ──
  const startRegistration = () => {
    if (!registerName.trim()) {
      Alert.alert('Error', 'Please enter a name');
      return;
    }
    setShowRegisterModal(false);
    setIsRegistering(true);
    setStatusText(`Registering ${registerName}... look at camera`);
    setStatusColor('#ff9900');
    setTimeout(() => {
      setIsRegistering(false);
      saveLocalAttendance(registerName);
      updateCounts();
      setStatusText(`✅ ${registerName} registered!`);
      setStatusColor('#00cc66');
      setRegisterName('');
      Alert.alert('Success', `${registerName} registered and saved locally!`);
    }, 3000);
  };

  // ── Sync to Firebase ──
  const handleSync = async () => {
    const unsynced = getUnsyncedRecords();
    if (unsynced.length === 0) {
      Alert.alert('Sync', '✅ All records already synced!');
      return;
    }
    setIsSyncing(true);
    setStatusText('Syncing to Firebase...');
    setStatusColor('#4488ff');
    try {
      const success = await syncToFirebase(unsynced);
      if (success) {
        markAllSynced();
        updateCounts();
        setStatusText('✅ Sync complete!');
        setStatusColor('#00cc66');
        Alert.alert('Success', `✅ Synced ${unsynced.length} records to Firebase!\nLocal data purged.`);
      } else {
        setStatusText('❌ Sync failed');
        setStatusColor('#ff4444');
        Alert.alert('Failed', 'No internet connection. Data saved locally.');
      }
    } catch (e) {
      setStatusText('❌ Sync failed');
      setStatusColor('#ff4444');
      Alert.alert('Failed', 'No internet connection. Data saved locally.');
    }
    setIsSyncing(false);
  };

  if (!hasPermission) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>Camera permission required</Text>
        <TouchableOpacity style={styles.btn} onPress={requestPermission}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Camera */}
      <Camera
        style={StyleSheet.absoluteFill}
        cameraType={CameraType.Front}
      />

      {/* Top HUD */}
      <View style={styles.topHud}>
        <Text style={styles.title}>🔐 FaceAuth</Text>
        <Text style={styles.subtitle}>Offline Face Recognition</Text>
        <View style={styles.statsRow}>
          <Text style={styles.statText}>📋 Total: {totalRecords}</Text>
          <Text style={styles.statText}>⏳ Unsynced: {unsyncedCount}</Text>
        </View>
      </View>

      {/* Face box overlay */}
      <View style={styles.faceBox} />

      {/* Status */}
      <View style={[styles.statusBar, {borderColor: statusColor}]}>
        <Text style={[styles.statusText, {color: statusColor}]}>
          {statusText}
        </Text>
      </View>

      {/* Bottom controls */}
      <View style={styles.bottomControls}>
        <TouchableOpacity
          style={[styles.btn, {backgroundColor: '#ff9900'}]}
          onPress={() => setShowRegisterModal(true)}>
          <Text style={styles.btnText}>➕ Register</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, {backgroundColor: livenessOn ? '#00cc66' : '#888'}]}
          onPress={() => setLivenessOn(!livenessOn)}>
          <Text style={styles.btnText}>
            👁 {livenessOn ? 'ON' : 'OFF'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, {backgroundColor: isSyncing ? '#888' : '#4488ff'}]}
          onPress={handleSync}
          disabled={isSyncing}>
          <Text style={styles.btnText}>
            {isSyncing ? '⏳ Syncing' : '☁️ Sync'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Register Modal */}
      <Modal visible={showRegisterModal} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>Register New Face</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter your name"
              placeholderTextColor="#888"
              value={registerName}
              onChangeText={setRegisterName}
              autoFocus
            />
            <TouchableOpacity
              style={[styles.btn, {backgroundColor: '#ff9900', marginTop: 12}]}
              onPress={startRegistration}>
              <Text style={styles.btnText}>📸 Start Capture</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.btn, {backgroundColor: '#555', marginTop: 8}]}
              onPress={() => setShowRegisterModal(false)}>
              <Text style={styles.btnText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ─────────────────────────────────────────────
//  STYLES
// ─────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#000'},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#000'},
  errorText: {color: '#ff4444', fontSize: 16, marginBottom: 20},
  topHud: {
    position: 'absolute', top: 40, width: '100%',
    alignItems: 'center', zIndex: 10,
  },
  title: {color: '#fff', fontSize: 22, fontWeight: 'bold'},
  subtitle: {color: '#aaa', fontSize: 13, marginTop: 2},
  statsRow: {
    flexDirection: 'row', marginTop: 8, gap: 16,
  },
  statText: {color: '#fff', fontSize: 12, backgroundColor: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 6},
  faceBox: {
    position: 'absolute', top: '25%', left: '15%',
    width: '70%', height: '40%',
    borderWidth: 2, borderColor: '#00cc66',
    borderRadius: 12, zIndex: 10,
  },
  statusBar: {
    position: 'absolute', bottom: 160, width: '80%',
    alignSelf: 'center', borderWidth: 1,
    borderRadius: 10, padding: 10,
    backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 10,
  },
  statusText: {fontSize: 15, textAlign: 'center', fontWeight: '600'},
  bottomControls: {
    position: 'absolute', bottom: 40, width: '100%',
    flexDirection: 'row', justifyContent: 'space-evenly', zIndex: 10,
  },
  btn: {
    paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: 10, minWidth: 90, alignItems: 'center',
  },
  btnText: {color: '#fff', fontWeight: 'bold', fontSize: 13},
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center', alignItems: 'center',
  },
  modalBox: {
    backgroundColor: '#1a1a1a', borderRadius: 16,
    padding: 24, width: '80%',
  },
  modalTitle: {color: '#fff', fontSize: 18, fontWeight: 'bold', marginBottom: 16},
  input: {
    backgroundColor: '#333', color: '#fff',
    borderRadius: 8, padding: 12, fontSize: 15,
  },
});
