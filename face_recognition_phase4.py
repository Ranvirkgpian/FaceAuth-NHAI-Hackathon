import cv2
import numpy as np
import mediapipe as mp
import insightface
from insightface.app import FaceAnalysis
import os
import pickle
import time

# ─────────────────────────────────────────────
#  SETTINGS
# ─────────────────────────────────────────────
EMBEDDINGS_FILE   = "embeddings_v2.pkl"  # separate from Phase 3
MATCH_THRESHOLD   = 0.5                  # cosine distance (lower = stricter)
REGISTER_SAMPLES  = 30                   # frames captured during registration
LIVENESS_BLINKS   = 2                    # blinks required to pass liveness check

# ─────────────────────────────────────────────
#  LOAD INSIGHTFACE (MobileFaceNet via ONNX)
#  Downloads ~30MB model automatically on
#  first run, then works fully offline.
# ─────────────────────────────────────────────
print("Loading InsightFace (MobileFaceNet)...")
app = FaceAnalysis(name="buffalo_sc",
                   providers=["CPUExecutionProvider"])
app.prepare(ctx_id=0, det_size=(320, 320))
print("✅ InsightFace loaded")

# ─────────────────────────────────────────────
#  LOAD MEDIAPIPE FACE MESH (for liveness)
# ─────────────────────────────────────────────
mp_face_mesh = mp.solutions.face_mesh
face_mesh    = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)
print("✅ MediaPipe Face Mesh loaded")

# ─────────────────────────────────────────────
#  EYE LANDMARKS (MediaPipe 468-point model)
# ─────────────────────────────────────────────
LEFT_EYE_TOP    = [159, 160, 161]
LEFT_EYE_BOTTOM = [145, 144, 163]
RIGHT_EYE_TOP   = [386, 387, 388]
RIGHT_EYE_BOTTOM= [374, 373, 380]

def eye_aspect_ratio(landmarks, top_ids, bottom_ids, w, h):
    """EAR — smaller value means eye is closed."""
    top    = np.mean([[landmarks[i].x * w, landmarks[i].y * h] for i in top_ids],    axis=0)
    bottom = np.mean([[landmarks[i].x * w, landmarks[i].y * h] for i in bottom_ids], axis=0)
    return abs(top[1] - bottom[1])

EAR_THRESHOLD = 8.0   # pixels — below this = eye closed

# ─────────────────────────────────────────────
#  EMBEDDINGS DATABASE
# ─────────────────────────────────────────────
def load_embeddings():
    if os.path.exists(EMBEDDINGS_FILE):
        with open(EMBEDDINGS_FILE, "rb") as f:
            return pickle.load(f)
    return {}

def save_embeddings(db):
    with open(EMBEDDINGS_FILE, "wb") as f:
        pickle.dump(db, f)
    total = sum(len(v) for v in db.values())
    print(f"✅ Saved {total} embeddings for {list(db.keys())}")

# ─────────────────────────────────────────────
#  RECOGNITION
# ─────────────────────────────────────────────
def cosine_distance(a, b):
    a = a / (np.linalg.norm(a) + 1e-6)
    b = b / (np.linalg.norm(b) + 1e-6)
    return 1.0 - float(np.dot(a, b))

def recognize(embedding, db):
    best_name = "Unknown"
    best_dist = float("inf")
    for name, embs in db.items():
        for e in embs:
            d = cosine_distance(embedding, e)
            if d < best_dist:
                best_dist = d
                best_name = name
    if best_dist <= MATCH_THRESHOLD:
        confidence = round((1 - best_dist) * 100, 1)
        return best_name, confidence
    return "Unknown", round((1 - best_dist) * 100, 1)

# ─────────────────────────────────────────────
#  DRAW OVERLAY
# ─────────────────────────────────────────────
def draw_box(frame, bbox, name, confidence, color):
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = f"{name} {confidence}%"
    cv2.rectangle(frame, (x1, y1 - 30), (x2, y1), color, -1)
    cv2.putText(frame, label, (x1 + 5, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    print("\n" + "="*55)
    print("  FACE RECOGNITION — PHASE 4 (MobileFaceNet + Liveness)")
    print("="*55)
    print("CONTROLS:")
    print("  R = Register face  |  Q = Quit")
    print("  L = Toggle liveness check ON/OFF")
    print("="*55 + "\n")

    db = load_embeddings()
    print(f"📦 Registered: {list(db.keys()) or 'nobody yet'}\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open webcam.")
        return

    # ── State ──
    registering      = False
    register_name    = ""
    register_count   = 0
    register_embs    = []

    liveness_on      = True
    liveness_passed  = False
    blink_count      = 0
    eye_was_closed   = False

    fps_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # ── Liveness: blink detection via MediaPipe ──
        mesh_results = face_mesh.process(rgb)
        blink_detected = False

        if mesh_results.multi_face_landmarks:
            lm = mesh_results.multi_face_landmarks[0].landmark
            left_ear  = eye_aspect_ratio(lm, LEFT_EYE_TOP,  LEFT_EYE_BOTTOM,  w, h)
            right_ear = eye_aspect_ratio(lm, RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM, w, h)
            avg_ear   = (left_ear + right_ear) / 2.0

            eye_closed = avg_ear < EAR_THRESHOLD
            if eye_closed and not eye_was_closed:
                blink_count   += 1
                blink_detected = True
            eye_was_closed = eye_closed

            if blink_count >= LIVENESS_BLINKS:
                liveness_passed = True

        # ── InsightFace detection + recognition ──
        faces = app.get(rgb)

        if faces:
            face      = faces[0]
            embedding = face.embedding
            bbox      = face.bbox   # [x1, y1, x2, y2]

            # ── Registration mode ──
            if registering:
                register_embs.append(embedding)
                register_count += 1

                x1, y1, x2, y2 = [int(v) for v in bbox]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 165, 255), 2)
                cv2.rectangle(frame, (x1, y1 - 30), (x2, y1), (0, 165, 255), -1)
                cv2.putText(frame, f"Registering... {register_count}/{REGISTER_SAMPLES}",
                            (x1 + 5, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

                # Progress bar
                prog = int((register_count / REGISTER_SAMPLES) * (x2 - x1))
                cv2.rectangle(frame, (x1, y2 + 5), (x1 + prog, y2 + 14),
                              (0, 165, 255), -1)

                if register_count >= REGISTER_SAMPLES:
                    db[register_name] = register_embs
                    save_embeddings(db)
                    print(f"✅ Registered '{register_name}' successfully!")
                    registering    = False
                    register_count = 0
                    register_embs  = []

            # ── Recognition mode ──
            else:
                name, confidence = recognize(embedding, db)

                if liveness_on and not liveness_passed:
                    color = (0, 165, 255)  # orange — waiting for liveness
                    draw_box(frame, bbox, "Blink to verify", confidence, color)
                    cv2.putText(frame,
                                f"Blinks: {blink_count}/{LIVENESS_BLINKS} — please blink!",
                                (20, h - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                else:
                    if name == "Unknown":
                        color = (0, 0, 255)   # red
                        draw_box(frame, bbox, name, confidence, color)
                    else:
                        color = (0, 200, 0)   # green
                        draw_box(frame, bbox, name, confidence, color)
                        cv2.putText(frame, f"Welcome, {name}!",
                                    (20, h - 20),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0), 2)

        else:
            cv2.putText(frame, "No face detected", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            # Reset liveness when face disappears
            if not registering:
                liveness_passed = False
                blink_count     = 0
                eye_was_closed  = False

        # ── HUD ──
        fps = 1.0 / (time.time() - fps_time + 1e-6)
        fps_time = time.time()

        cv2.putText(frame, f"FPS: {fps:.1f}", (w - 110, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.putText(frame, "R=Register  L=Liveness  Q=Quit", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)

        liveness_status = "ON" if liveness_on else "OFF"
        liveness_color  = (0, 200, 0) if liveness_on else (0, 0, 255)
        cv2.putText(frame, f"Liveness: {liveness_status}", (20, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, liveness_color, 2)

        cv2.imshow("Face Recognition - Phase 4 (MobileFaceNet)", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            print("👋 Exiting...")
            break

        elif key == ord('r'):
            register_name = input("\n👤 Enter name to register: ").strip()
            if register_name:
                registering    = True
                register_count = 0
                register_embs  = []
                print(f"📸 Look at camera — capturing {REGISTER_SAMPLES} frames for '{register_name}'...")
            else:
                print("❌ Name cannot be empty.")

        elif key == ord('l'):
            liveness_on     = not liveness_on
            liveness_passed = False
            blink_count     = 0
            print(f"🔁 Liveness check: {'ON' if liveness_on else 'OFF'}")

    cap.release()
    cv2.destroyAllWindows()
    print("✅ Done.")

if __name__ == "__main__":
    main()
