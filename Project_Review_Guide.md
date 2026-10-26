# Driver Drowsiness Detection System — Project Review Guide

This guide explains the project in simple English and is designed to help you
prepare for a project review or presentation.

## 1. Project in one sentence

This is a desktop demonstration that uses a regular webcam to estimate signs
of driver drowsiness from facial landmarks, show the measurements and warnings
in a dashboard, and demonstrate a software-only emergency parking response.

## 2. The problem it addresses

Sleepiness can affect a driver's eyes, blinking, mouth, and head posture. This
project watches those visible signals and gives warnings when its rules suggest
possible drowsiness. It also shows what a fail-safe response could look like in
a simulated driving scene.

It is a demonstration and learning project, not a certified safety device. It
does not control a real car and should not be used to decide whether someone is
safe to drive.

## 3. Main features

- **Webcam monitoring:** Uses a standard camera, when available, to capture
  frames. The user can start, pause, resume, or stop the webcam.
- **Face landmarks:** Uses dlib's 68-point facial landmark predictor to locate
  features around the eyes, eyebrows, nose, and mouth.
- **Eye monitoring:** Calculates Eye Aspect Ratio (EAR), estimates blinks and
  eye-closure duration, and calculates PERCLOS after enough tracking history
  has been collected.
- **Personal calibration:** A guided one-minute calibration learns an
  individual's open-eye reference and usual head position. This is intended to
  help accommodate different eye sizes and naturally different resting
  postures. The calibration reports whether it collected enough samples.
- **Head-pose estimate:** Displays approximate pitch, yaw, and roll. Sustained
  pitch/roll deviation is compared with the calibrated posture; looking
  sideways by itself is not treated as head droop.
- **Mouth and yawn estimate:** Measures mouth opening and tracks sustained
  opening as a possible yawn.
- **Conversation-aware filtering:** Repeated mouth opening and closing is
  treated as *likely talking*, not confirmed speech. Yawn-based warnings are
  suppressed during this pattern, while eye-closure warnings remain active.
- **Staged warnings:** The dashboard shows increasing drowsiness levels and
  plays increasingly urgent warning tones. Continuous eye closure and
  head-pitch/roll deviation have warning stages at 5, 8, and 12 seconds.
- **Critical and unresponsive demonstrations:** The default critical repeated
  beep threshold is 35 seconds of continuous eye closure. The default
  simulated-parking timeout is 45 seconds without a response to an active
  warning or from continuous eye closure. These demonstration thresholds can
  be changed in Settings and are not safe real-world response times.
- **Driver response:** The “I'm alert” control records a response and restarts
  the unanswered-warning timer; it does not erase live risk measurements.
- **Camera guidance:** Shows visual framing/lighting hints. If a face is not
  found or is partly out of frame continuously for 5 seconds, the app speaks
  “Please set the camera properly” twice for that loss episode. Off-center and
  dim-light messages remain visual.
- **In-car-style dashboard:** Presents a separate illustrated driver, cabin,
  steering wheel, mirrors, dashboard, road, and driving status. Day/night and
  clear/rain/fog scene choices are visual simulation options.
- **Software-only parking:** Shows a simulated stop, including a speed decrease
  and hazard indication. No car, steering, braking, or autonomous-driving
  hardware is connected.
- **Test scenarios:** Provides labeled mock scenarios and an accelerated demo
  clock to review alerts and parking without waiting for the full timeouts.
  Mock values are marked as simulated, not webcam measurements.
- **Accessibility:** Offers larger text, high contrast, keyboard navigation,
  help, and a sound test.
- **Privacy and export:** Video frames are not recorded or included in reports.
  Session event history is held in memory unless the user explicitly exports
  a JSON summary. The history can be cleared and is discarded when the app
  closes.
- **Responsive processing:** Webcam capture and face analysis run outside the
  main GUI thread so the interface can remain responsive.
- **Simulation without a camera:** The dashboard and labeled test scenarios
  remain available when a webcam cannot be opened.

## 4. How the live detection works

1. OpenCV reads a frame from the webcam.
2. The frame is converted to grayscale for face and landmark analysis.
3. dlib detects a face and estimates its 68 facial landmarks.
4. The application measures the eye, mouth, and face geometry.
5. The detector updates rolling measurements and timers.
6. The dashboard receives the latest measurements and tracking status.
7. The alert manager updates the displayed risk state and warning sound.
8. If the configured unresponsive timeout is reached, the dashboard starts
   the simulated parking sequence.

If the face or eyes cannot be tracked, the system reports uncertainty. It does
not assume that missing eye data means the eyes are closed.

## 5. Important measurements in plain English

### Eye Aspect Ratio (EAR)

EAR compares eye height with eye width using landmark distances. In simple
terms, it estimates whether the eye looks open or closed while reducing the
effect of how large the face appears in the image. Calibration learns an
individual open-eye reference and sets a closure threshold below that
reference.

### Blink rate and closure duration

The program tracks eye-state changes over time to estimate blinks and how long
the eyes remain continuously closed. Brief eye closures are given a grace
period; a sustained closure can move through warning stages.

### PERCLOS

PERCLOS is the percentage of recent tracked time that the eyes were estimated
to be closed. This implementation uses a rolling 15-second window and waits
until that window is nearly full before showing a value. It is not available
immediately at camera startup.

### Mouth aperture

Mouth aperture compares mouth opening with mouth width. Sustained opening can
be counted as a possible yawn. Repeated open/close movement is only a
conversation-like heuristic; it does not listen to or recognize speech.

### Head pose

Approximate pitch, yaw, and roll come from facial landmarks. After calibration,
pose is compared with the user's usual posture. Current head-deviation alerts
use sustained pitch/roll deviation; yaw/side-looking alone is not treated as
head droop.

## 6. Calibration and different users

The one-minute guided calibration is intended to learn the driver's usual
comfortable posture and open-eye appearance:

- Keep the face visible and use the posture that is natural for you.
- Follow the on-screen prompts for natural blinking, gentle glances, and gentle
  tilts.
- The application collects eye and posture samples and displays sample counts.
- It reports whether eye and posture calibration succeeded; if not, improve
  framing or lighting and try again.

Calibration can improve tolerance for naturally smaller eyes or a habitual
head angle, but it cannot guarantee accurate tracking for every face, pose,
camera, lighting condition, or pair of glasses.

## 7. Alert and simulation behavior

| Situation | Demonstration behavior |
|---|---|
| Normal tracked state | Shows live measurements and an attentive status. |
| Possible drowsiness | Raises the displayed level and plays a warning tone. |
| Continuous eye closure | Starts escalating stages at 5, 8, and 12 seconds. |
| Sustained pitch/roll deviation | Starts escalating stages at 5, 8, and 12 seconds. |
| Eye closure longer than the configured critical limit | Repeats a high-urgency beep; default is 35 seconds. |
| No response or continuous closure reaches the configured timeout | Starts the simulated parking sequence; default is 45 seconds. |
| Eyes reopen / risk recovers | Relevant timers and alerts can reset according to the live state. |
| Face tracking is lost | Shows tracking uncertainty, clears applicable detection timers, and does not count missing measurements as closed eyes. |
| Face is not found or partly out of frame for 5 seconds | Speaks the camera-placement reminder twice once for that loss episode. |
| Driver selects “I'm alert” | Records the response and restarts the unanswered-warning timer; measurements remain active. |

The warning tones can become faster and more urgent as severity rises. The
program does not override the computer's master volume. The critical eye
closure and unresponsive parking timeouts are adjustable demonstration
settings, not validated safety thresholds.

## 8. Interface and user flow

1. Launch the dashboard.
2. Start the webcam and allow camera access.
3. Follow the guided eye/posture calibration if using personalized thresholds.
4. Observe the live preview, landmark overlay, tracking status, and metric
   cards.
5. Use the camera framing hints if face tracking is unreliable.
6. Pause/resume/stop the camera as needed; stop releases the camera.
7. Review labeled scenarios or accelerated mode to demonstrate alerts and
   simulated parking.
8. Review the session summary and export JSON only if needed.

The camera image and the illustrated driver are separate. The illustrated
driver is not generated from the camera image.

## 9. Project structure

| File or folder | Purpose |
|---|---|
| `main.py` | Starts the PyQt application, runs the webcam worker, processes frames, and connects detections to the dashboard. |
| `perclos_calculation.py` | Detects facial landmarks and calculates eye, mouth, calibration, tracking, and head-pose measurements. |
| `wideScreen.py` | Implements the dashboard, illustrated driving scene, controls, warning behavior, scenarios, and report interface. |
| `posture_deviation.py` | Optional standalone MediaPipe posture utility; it is not the main per-frame webcam detector. |
| `tests/test_driverguard_safety.py` | Automated tests for selected alert, tracking, calibration, privacy, and simulation behaviors. |
| `shape_predictor_68_face_landmarks.dat` | dlib model file required for facial landmarks. |
| `training_model.ipynb` | Separate model-training material. |
| `Testing_main_program.ipynb` | Notebook-based testing or experimentation material. |
| `asset/`, `images/`, `top_bar_images/` | Visual resources used by the project. |

## 10. Live runtime versus the YOLO training material

The live `main.py` webcam application uses OpenCV and dlib facial landmarks.
It does **not** use the YOLOv8 model for its live drowsiness decision. YOLOv8
training and inference notebooks, a model file, and reported training metrics
are separate project materials. Do not present those reported metrics as
accuracy results for the current live webcam application. The automated tests
also do not validate real-world detection accuracy.

## 11. Technology used

- **Python:** application logic.
- **OpenCV:** webcam capture and image processing.
- **dlib:** face detection and the 68-point facial landmark predictor.
- **NumPy and SciPy:** numeric calculations and landmark distances.
- **PyQt5:** desktop interface, signals, timers, and threaded worker setup.
- **MediaPipe:** used by the optional standalone posture utility, not the main
  per-frame face measurement path.
- **Unittest:** automated deterministic safety/behavior tests.
- **Ultralytics YOLOv8 / PyTorch:** separate training or notebook materials;
  not required for the live dashboard runtime described above.

## 12. Privacy, limits, and safety

- The application analyzes webcam frames locally and does not save video
  frames.
- Explicit JSON export contains session counts, coverage, and event messages,
  not images or raw facial measurements.
- A normal webcam can lose facial landmarks because of pose, low light,
  distance, occlusion, glasses glare, or camera placement.
- The frontal-face detector may fail during a long side-facing turn. The
  five-second spoken reminder delay does not prove that the driver left the
  frame; a turn and a framing problem can look similar to the detector.
- Head/neck overlay lines are an estimate based on face geometry, not
  independently detected neck landmarks or a full-body posture model.
- Mouth movement is not speech recognition.
- Unit tests use mocked detection behavior and cannot prove reliable
  real-person detection, safe driving performance, or physical audio volume.
- The simulated stop does not control a real vehicle.
- Drowsiness is dangerous well before the demo's 35- and 45-second limits.
  This project is not a replacement for rest, safe driving practices, or a
  validated driver monitoring system.

## 13. How to run and test

From PowerShell in the project folder:

```powershell
.\.venv\Scripts\python.exe main.py
```

To run the automated tests without a webcam:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover selected behaviors such as calibration sample reporting,
personalized thresholds, tracking-loss resets, camera-reminder delay,
conversation-like mouth motion, staged warnings, user acknowledgement, and
simulated parking. They do not certify real-world performance.

For a review demonstration, show these items:

1. Dashboard startup and its separate camera and illustrated-driver areas.
2. Webcam status, face landmarks, and live measurement cards.
3. Calibration instructions and resulting personal eye/posture values.
4. A labeled test scenario with its alert level and event history.
5. The accelerated critical alert and simulated parking response.
6. A tracking-loss state and the uncertainty message.
7. Privacy controls and a sample JSON summary, if appropriate.

Use labeled scenarios for predictable timing. Do not simulate dangerous actions
while driving a real vehicle.

## 14. Review questions and simple answers

**Q: What does the project do?**  
A: It watches facial landmarks from a webcam, estimates possible drowsiness,
shows alerts in a desktop dashboard, and demonstrates a simulated parking
response.

**Q: What is EAR?**  
A: EAR is a ratio based on eye height and width. A lower value can indicate an
eye is closing. Calibration sets a personal open-eye reference.

**Q: Why use calibration?**  
A: People have different eye shapes and natural head positions. Calibration
helps set personal reference values instead of relying only on one fixed
baseline.

**Q: What is PERCLOS?**  
A: It is the share of a recent time window during which the eyes were estimated
to be closed.

**Q: How does it respond to someone talking?**  
A: Repeated mouth open/close movement is treated as likely talking, so
yawn-only warnings are filtered during that pattern. It is not actual speech
recognition, and eye warnings are still active.

**Q: Does turning sideways trigger an alert?**  
A: Sideways yaw alone is not treated as head droop. However, a long turn can
make the frontal-face detector lose the face, and the app cannot always
distinguish that from leaving the camera view.

**Q: Does the app park a real car?**  
A: No. It only animates a software demonstration. It has no connection to a
vehicle or vehicle-control hardware.

**Q: Does the YOLO model power the live dashboard?**  
A: No. The current live runtime uses dlib landmarks. YOLO training and
inference are separate notebook/model materials.

**Q: How do you test it?**  
A: Run the unittest suite for predictable software behavior, then use the
labeled dashboard scenarios. A real webcam check is needed for camera-specific
behavior, but it is not proof of safety.

**Q: What are the main limitations?**  
A: Detection depends on visible, reliable facial landmarks; lighting, pose,
camera quality, glasses, and occlusion can affect it. It is a prototype, not a
certified safety product.

## 15. Short presentation script

“My project is a webcam-based driver drowsiness monitoring demonstration. It
uses OpenCV to capture frames and dlib's 68 facial landmarks to estimate eye
closure, blinking, mouth opening, and head pose. A one-minute calibration
learns a personal eye reference and usual posture. The PyQt5 dashboard displays
the camera, measurements, tracking status, and staged warnings. It also
contains an illustrated driving scene and a software-only parking
demonstration. The camera video is not recorded, and the parking scene does
not control a real vehicle. This is a prototype: its timeouts and test results
are not safety certification, and real-world reliability still depends on
camera and face-tracking conditions.”

## 16. Faculty demo: what to show and what to say

Use this as a calm walkthrough. Explain what the screen shows, what it means,
and what it does **not** prove. Use the labeled scenarios for predictable
outputs; do not wait for or imitate a dangerous real driving situation.

### A. Introduce the project

**Show:** The dashboard before starting the camera.

**Say:** “This is a software prototype for demonstrating webcam-based
drowsiness indicators. It combines facial measurements, warning rules, and an
illustrated driving simulation. It is not connected to a vehicle.”

### B. Explain the camera and tracking status

**Show:** Start the webcam and point out the live preview and face landmark
overlay.

**Say:** “OpenCV reads frames from a normal webcam. dlib locates a face and its
68 landmarks. The overlay helps us see which facial points are being
measured. The camera image is analyzed locally and is not saved as video.”

If the status says tracking is uncertain, explain: “The system does not have
reliable measurements right now, so it reports uncertainty instead of
pretending the eyes are closed.”

### C. Explain each measurement card

| Dashboard output | Plain-English explanation |
|---|---|
| **EAR** | A ratio comparing eye opening with eye width. It is used as an estimate of open versus closed eyes. It is a ratio, not a percentage score. |
| **PERCLOS** | The estimated share of a recent tracked window that the eyes were closed. It appears only after almost the full 15-second window has reliable data. |
| **Blink rate** | An estimate of detected blinks over time. It is one signal and is not a diagnosis by itself. |
| **Eye-closure duration** | How long the current continuous eye-closed state has lasted. It resets when eyes are tracked as open or tracking is lost. |
| **Mouth aperture** | Estimated mouth opening relative to mouth width. Sustained opening can contribute to a possible-yawn signal. |
| **Yawn count/duration** | The detected possible-yawn events and duration. These are estimates from mouth landmarks, not proof that a person yawned. |
| **Pitch, yaw, roll / head deviation** | Approximate head angles and their deviation from the calibrated posture. Side-looking by itself is not treated as head droop. |
| **Tracking status / coverage** | Whether the face and required landmarks could be measured reliably. Missing measurements are uncertainty, not evidence of sleep. |
| **Risk level / alert status** | The application's rule-based summary of the available signals. It is an alert state, not a medical assessment or probability of a crash. |
| **Event history** | A time-ordered record of application events and warnings. It helps explain what the software did during the session. |
| **Illustrated car / road** | A separate animation used to demonstrate the interface and parking response. It is not a live image of the driver or a vehicle simulator connected to a car. |

If PERCLOS has no value at startup, say: “That is expected. The program waits
until it has nearly a complete 15-second reliable window instead of reporting
a misleading early percentage.”

### D. Explain personal calibration

**Show:** The calibration button, prompts/progress, and the final result if you
have calibrated ahead of time.

**Say:** “The guided session lasts one minute. It collects open-eye and
comfortable-posture samples, then sets personal reference values. This helps
with differences such as smaller eyes or a naturally tilted resting posture.
The sample counts tell us whether the session collected enough data.”

Add: “Calibration improves personalization but cannot guarantee that tracking
works for every face, pose, lighting condition, or glasses.”

### E. Demonstrate a normal state and a warning state

**Show:** First select the normal/attentive labeled scenario, then a mild or
warning scenario.

**Say:** “The normal scenario shows the baseline dashboard state. The next
scenario injects labeled test values so I can demonstrate how the risk status,
sound, and event history change. These values are mock inputs, not a live
measurement of a person.”

Point out that continuous eye closure and sustained pitch/roll deviation have
5-, 8-, and 12-second stages. Explain that the stages are deliberately delayed
to keep a brief blink or movement from immediately producing a warning.

### F. Demonstrate conversation and ordinary head turns

**Show:** If appropriate, use a labeled scenario or a stationary, safe webcam
demonstration; keep eyes open and move naturally.

**Say:** “Repeated mouth opening and closing is treated as likely conversation,
so yawn-only warnings are filtered during that pattern. This is a visual
heuristic, not speech recognition. Eye-closure evidence remains active.”

Be transparent: “A long side-facing turn can make the frontal face detector
lose the face. The app waits before speaking the camera reminder, but it
cannot always tell a turn from a face that has left the frame.”

### G. Demonstrate tracking loss

**Show:** Prefer a labeled tracking-loss scenario. If using the webcam, move
out of view only while stationary.

**Say:** “When the face cannot be tracked, the app shows uncertainty and clears
the applicable detection timers. It does not convert missing eye data into a
closed-eye result. A sustained no-face or partly-out-of-frame condition can
trigger the spoken camera-placement reminder after five seconds.”

### H. Demonstrate critical alert and simulated parking

**Show:** Use accelerated test mode and the labeled critical/unresponsive or
parking scenario.

**Say:** “The default demonstration repeats a critical beep after 35 seconds
of continuous eye closure. At the default 45-second unanswered-warning or
continuous-closure timeout, the illustration begins a parking sequence. The
scene shows a software response only; no vehicle control signal is sent.”

Explain: “The test clock can be accelerated so reviewers do not need to wait.
The UI labels these as simulated values.”

### I. Show response, settings, privacy, and report

**Show:** “I'm alert,” relevant settings, hide-preview/privacy controls, and
the session summary/export dialog if time allows.

**Say:** “Acknowledging a warning records a response and restarts the
unanswered timer; it does not disable measurement or erase live risk.
Settings allow the demonstration thresholds and accessibility options to be
configured. Video frames are not included in the JSON export; exporting is an
explicit user action.”

### J. Close with testing and limitations

**Say:** “The unittest suite checks selected software behavior using mocked
detection inputs. It does not prove real-world face detection accuracy or
safety. Real webcam performance still needs testing under varied users,
lighting, camera positions, head poses, and glasses. The project is a
prototype, not a certified driver-safety product.”

## 17. Likely faculty questions and confident answers

**Q: What exactly is the project output?**  
A: The output is a live dashboard containing the camera preview, facial
measurements, tracking state, risk level, warning sounds, event history, and a
separate animated driving/parking demonstration.

**Q: Is the result an AI prediction or a fixed rule?**  
A: The live application measures facial landmarks with dlib and applies
thresholds, rolling measurements, calibration, and timers to produce its alert
levels. It is not using the YOLO model to make the live dashboard decision.

**Q: What does a low EAR mean?**  
A: It means the detected eye opening is small relative to eye width. The
application compares it with a personal open-eye reference and uses time and
other signals; one low reading alone should not be presented as proof of
drowsiness.

**Q: Why does the system use multiple signals?**  
A: A single measurement can be affected by normal actions or tracking noise.
The application also considers time, eye history, mouth behavior, and
calibrated head-pose deviation. The combination is still an estimate, not a
guaranteed diagnosis.

**Q: How do you support people with small eyes or a naturally bent head?**  
A: The guided calibration learns an individual open-eye EAR reference and
usual head posture from valid samples. It can help personalize the thresholds,
but it cannot guarantee success if landmarks are not detected reliably.

**Q: Why can the system give no PERCLOS value at first?**  
A: It needs nearly a full 15 seconds of reliable tracked samples to make the
rolling percentage meaningful. Showing a value too early could be misleading.

**Q: How do you reduce false alerts when someone talks or turns?**  
A: Repeated mouth open/close motion is treated as likely talking and
yawn-derived warnings are filtered during that pattern. Side yaw alone is not
head-droop evidence. Eye-closure warnings remain enabled. A long side turn can
still cause tracking loss with the current frontal detector.

**Q: Does it recognize speech?**  
A: No. It uses mouth movement as a conversation-like heuristic and does not
record or analyze audio for speech recognition.

**Q: Does it detect the neck directly?**  
A: No. The neck/shoulder drawing is an estimated visual guide based on face
geometry. The main runtime does not independently detect neck landmarks or run
a full-body posture model on every frame.

**Q: Why did you choose a normal webcam?**  
A: It keeps the prototype low-cost and easy to demonstrate. The tradeoff is
that accuracy depends more on framing, light, face visibility, and camera
quality than a dedicated sensor system.

**Q: What happens if the camera fails or the face disappears?**  
A: The UI reports camera/tracking uncertainty and does not fabricate webcam
measurements or treat missing eyes as closed. The illustrated dashboard and
labeled test scenarios can still be demonstrated without a camera.

**Q: Are the 35- and 45-second limits safe thresholds?**  
A: No. They are configurable demonstration requirements. They are not safe
reaction times, validated medical limits, or evidence that it is safe to
continue driving.

**Q: What does the parking feature actually control?**  
A: It controls only the software illustration: for example, its displayed
speed and hazard/status animation. It sends no command to a real car.

**Q: How did you test the project?**  
A: Deterministic unit tests cover selected software behavior with mocked
detector data. Labeled scenarios demonstrate the dashboard flow. Separate
live-camera testing is needed to evaluate tracking under real conditions; the
unit tests do not measure real-world accuracy.

**Q: What do the YOLO accuracy numbers in the project materials describe?**  
A: They describe the separate YOLO training/evaluation material documented in
the repository. They are not accuracy measurements for this live dlib-based
dashboard.

**Q: How do you protect privacy?**  
A: The application processes frames locally and does not record video. A JSON
summary is exported only when the user requests it and contains session
summary/event information rather than camera images.

**Q: What is the biggest limitation?**  
A: Reliable facial landmarks are required. A side-facing pose, poor lighting,
glare, occlusion, distance, or camera placement can reduce tracking. The
project is a demonstration, not a certified safety system.

**Q: What would you improve next?**  
A: I would evaluate it with a larger and more varied set of consented
recordings, measure false positives and missed detections, improve profile-pose
tracking, and validate thresholds before making any safety claims. A real
vehicle-control integration would require a separate safety-engineering,
regulatory, and hardware validation effort; it is outside this project.

## 18. Review-day checklist

- Start the app before the review and verify the webcam permission, camera
  framing, microphone/speaker-independent warning sound, and display scaling.
- Keep a labeled normal, drowsy, tracking-loss, and parking scenario ready.
- Use accelerated mode to demonstrate time-based behavior predictably.
- Explain that scenario data is simulated and identify it as such on screen.
- Do not claim a detection-accuracy percentage for the live dlib runtime.
- Do not claim speech recognition, direct neck detection, or real autonomous
  control.
- State the limitations confidently; a clear limitation is better than an
  unsupported claim.
- If asked a question you have not tested, say: “I have not validated that
  case yet. It is a limitation/future test, and I would measure it before
  claiming the feature works reliably.”
