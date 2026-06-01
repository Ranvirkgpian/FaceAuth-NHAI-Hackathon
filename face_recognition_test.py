import cv2
import numpy as np
import mediapipe as mp
import os
import pickle
import time

# ─────────────────────────────────────────────
#  SETTINGS
# ─────────────────────────────────────────────
FACES_DIR        = "faces"          # folder to store registered face images
EMBEDDINGS_FILE  = "embeddings.pkl" # file to store face embeddings
MATCH_THRESHOLD  = 0.6              # cosine similarity threshold (higher = stricter)

# ─────────────────────────────────────────────
#  LOAD MEDIAPIPE FACE DETECTION
# ─────────────────────────────────────────────
mp_face_detection = mp.solutions.face_detection
mp_face_mesh      = mp.solutions.face_mesh
mp_drawing        = mp.solutions.drawing_utils

face_detector  = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.6)
face_mesh      = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1,
                                        min_detection_confidence=0.5, min_tracking_confidence=0.5)

print("✅ MediaPipe loaded")

# ─────────────────────────────────────────────
#  SIMPLE FACE EMBEDDING USING OPENCV
#  (We use a resized + flattened + normalized
#   face patch as a lightweight embedding.
#   In Phase 4 we swap this with MobileFaceNet.)
# ─────────────────────────────────────────────
def get_face_embedding(face_img):
    """Convert a face crop to a simple normalized embedding vector."""
    resized   = cv2.resize(face_img, (64, 64))
    gray      = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    flat      = gray.flatten().astype(np.float32)
    norm      = flat / (np.linalg.norm(flat) + 1e-6)
    return norm

def cosine_similarity(a, b):
    """Cosine similarity between two vectors (1.0 = identical)."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6))

# ─────────────────────────────────────────────
#  LOAD / SAVE EMBEDDINGS
# ─────────────────────────────────────────────
def load_embeddings():
    if os.path.exists(EMBEDDINGS_FILE):
        with open(EMBEDDINGS_FILE, "rb") as f:
            return pickle.load(f)
    return {}   # { "name": [embedding1, embedding2, ...] }

def save_embeddings(db):
    with open(EMBEDDINGS_FILE, "wb") as f:
        pickle.dump(db, f)
    print(f"✅ Embeddings saved — {sum(len(v) for v in db.values())} total faces")

# ─────────────────────────────────────────────
#  CROP FACE FROM FRAME
# ─────────────────────────────────────────────
def crop_face(frame, detection):
    h, w = frame.shape[:2]
    bbox = detection.location_data.relative_bounding_box
    x1 = max(0, int(bbox.xmin * w) - 20)
    y1 = max(0, int(bbox.ymin * h) - 20)
    x2 = min(w, int((bbox.xmin + bbox.width)  * w) + 20)
    y2 = min(h, int((bbox.ymin + bbox.height) * h) + 20)
    return frame[y1:y2, x1:x2], (x1, y1, x2, y2)

# ─────────────────────────────────────────────
#  RECOGNIZE FACE AGAINST DATABASE
# ─────────────────────────────────────────────
def recognize_face(embedding, db):
    best_name  = "Unknown"
    best_score = 0.0
    for name, embeddings in db.items():
        for stored_emb in embeddings:
            score = cosine_similarity(embedding, stored_emb)
            if score > best_score:
                best_score = score
                best_name  = name
    if best_score >= MATCH_THRESHOLD:
        return best_name, best_score
    return "Unknown", best_score

# ─────────────────────────────────────────────
#  DRAW OVERLAY ON FRAME
# ─────────────────────────────────────────────
def draw_overlay(frame, box, name, score, registering=False):
    x1, y1, x2, y2 = box
    if registering:
        color = (0, 165, 255)   # orange while registering
        label = "Registering..."
    elif name == "Unknown":
        color = (0, 0, 255)     # red for unknown
        label = f"Unknown ({score:.2f})"
    else:
        color = (0, 200, 0)     # green for recognized
        label = f"{name} ({score:.2f})"

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.rectangle(frame, (x1, y1 - 30), (x2, y1), color, -1)
    cv2.putText(frame, label, (x1 + 5, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def main():
    print("\n" + "="*50)
    print("  FACE RECOGNITION TEST — PHASE 3")
    print("="*50)
    print("CONTROLS:")
    print("  R = Register your face (enter your name first)")
    print("  Q = Quit")
    print("="*50 + "\n")

    db = load_embeddings()
    print(f"📦 Loaded {len(db)} registered person(s): {list(db.keys())}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open webcam. Check camera connection.")
        return

    print("✅ Webcam opened. Press R to register, Q to quit.\n")

    registering   = False
    register_name = ""
    register_count = 0
    REGISTER_SAMPLES = 30   # capture 30 frames when registering

    fps_time = time.time()
    fps      = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Cannot read from webcam.")
            break

        frame = cv2.flip(frame, 1)   # mirror effect
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # ── Face detection ──
        results = face_detector.process(rgb)

        if results.detections:
            detection        = results.detections[0]   # use first face only
            face_crop, box   = crop_face(frame, detection)

            if face_crop.size == 0:
                continue

            embedding = get_face_embedding(face_crop)

            # ── Registration mode ──
            if registering:
                if register_name not in db:
                    db[register_name] = []
                db[register_name].append(embedding)
                register_count += 1
                draw_overlay(frame, box, register_name, 1.0, registering=True)

                progress = int((register_count / REGISTER_SAMPLES) * (box[2] - box[0]))
                cv2.rectangle(frame, (box[0], box[3] + 5),
                              (box[0] + progress, box[3] + 15), (0, 165, 255), -1)
                cv2.putText(frame, f"Capturing {register_count}/{REGISTER_SAMPLES}",
                            (box[0], box[3] + 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)

                if register_count >= REGISTER_SAMPLES:
                    save_embeddings(db)
                    print(f"✅ Registered: {register_name} ({REGISTER_SAMPLES} samples)")
                    registering    = False
                    register_count = 0

            # ── Recognition mode ──
            else:
                name, score = recognize_face(embedding, db)
                draw_overlay(frame, box, name, score)
                if name != "Unknown":
                    cv2.putText(frame, f"Welcome, {name}!", (20, frame.shape[0] - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0), 2)

        else:
            cv2.putText(frame, "No face detected", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # ── FPS counter ──
        fps   = 1.0 / (time.time() - fps_time + 1e-6)
        fps_time = time.time()
        cv2.putText(frame, f"FPS: {fps:.1f}", (frame.shape[1] - 110, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

        # ── Instructions ──
        cv2.putText(frame, "R=Register  Q=Quit", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

        cv2.imshow("Face Recognition - Phase 3 Test", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            print("👋 Exiting...")
            break

        elif key == ord('r'):
            register_name = input("\n👤 Enter your name to register: ").strip()
            if register_name:
                registering    = True
                register_count = 0
                print(f"📸 Look at the camera — capturing {REGISTER_SAMPLES} frames for '{register_name}'...")
            else:
                print("❌ Name cannot be empty.")

    cap.release()
    cv2.destroyAllWindows()
    print("✅ Done.")

if __name__ == "__main__":
    main()
