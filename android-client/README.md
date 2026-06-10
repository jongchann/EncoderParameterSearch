# Android Client MVP

This is the Step 11 Android client skeleton for the Encoder Parameter Search MVP.

Implemented components:

- `CapabilityReporter`: reports the first available H.264/AVC encoder capability.
- `EncoderParameterProxy`: maps backend parameters to `MediaFormat`.
- `NoOpExtensionStrategy`: leaves vendor extensions disabled for MVP.
- `TrialRunner`: registers capability, fetches a trial, runs encoding through a pluggable `SourceEncoder`, uploads result metadata/artifact, and reports failures.
- `BackendClient`: calls the existing backend JSON and multipart endpoints.
- `SyntheticSurfaceSourceEncoder`: produces a short synthetic H.264/AVC artifact for device smoke testing.
- `MainActivity`: minimal manual runner for session creation, capability registration, and one trial upload.

MVP parameter mapping:

| Backend parameter | Android mapping |
| --- | --- |
| `bitrate_kbps` | `MediaFormat.KEY_BIT_RATE` in bps |
| `i_frame_interval_sec` | `MediaFormat.KEY_I_FRAME_INTERVAL` |
| `profile` | `MediaFormat.KEY_PROFILE` when reported as supported |

The Android client intentionally does not measure VMAF. VMAF remains a backend evaluation responsibility.

Manual smoke-test flow:

1. Check Android tools with `./scripts/check_android_tools.sh`.
2. Start the backend for device access with `./scripts/run_server_for_device.sh`.
3. Build and install the Android app from `android-client/`.
4. Set the backend URL in the app.
   - Emulator default: `http://10.0.2.2:8000`
   - Physical device: use the host machine LAN IP, for example `http://192.168.0.10:8000`
5. Tap `Create session`.
6. Tap `Register capability`.
7. Tap `Run one trial`.
8. Confirm the backend stores `artifacts/{session_id}/trials/{trial_id}/output.h264`.

Remaining Step 11 verification:

- Make `adb`, `gradle`, and Android SDK tools available on the shell `PATH`, or build/install through Android Studio.
- Compile the Android project with a local Android SDK/Gradle installation.
- Run on one real Android device.
- Confirm one encoded artifact is uploaded successfully.
- Replace the synthetic source with the target input video source when moving beyond smoke testing.

Current checkpoint:

- Physical device connection has been prepared by the user.
- This shell could not run `adb devices` because `adb` is not installed or not on `PATH`.
- This shell could not compile the Android project because `gradle` is not installed or not on `PATH`.
