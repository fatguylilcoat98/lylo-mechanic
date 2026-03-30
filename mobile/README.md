# LYLO Mechanic — Mobile (React Native / Android)

OBD-II diagnostic app for Android. Connects to OBDLink MX+ via Bluetooth Classic SPP,
reads fault codes and live data, and sends it to the LYLO backend for full 12-layer diagnosis.

## Architecture

```
Phone (React Native)          Backend (Flask)
┌──────────────────┐          ┌─────────────────────┐
│  BluetoothService│──BT SPP──│                     │
│  OBDService      │          │  12-Layer Pipeline:  │
│  (ELM327 cmds)   │──HTTP───▶│  Normalize → Conf   │
│                  │          │  → Hypothesis → Safe │
│  Screens:        │◀──JSON───│  → DIY → Cost → etc │
│  Home / Connect  │          │                     │
│  Scan / Results  │          └─────────────────────┘
└──────────────────┘
```

## Setup

```bash
cd mobile
npm install
npx react-native run-android
```

### Prerequisites
- Node.js 18+
- Android SDK (API 33+)
- Java 17 (for React Native build)
- Physical Android device with Bluetooth (emulator doesn't support BT Classic)

### Backend
Start the Flask backend on your development machine:
```bash
cd ../backend
pip install -r ../requirements.txt
python app.py
```
The mobile app connects to `http://10.0.2.2:5050` by default (Android emulator → host).
For a physical device, update `ApiClient.js` with your machine's local IP.

## Screens

1. **Home** — Connect to OBDLink or enter Demo Mode
2. **Connect** — Bluetooth device discovery, pairing, ELM327 initialization
3. **Scan** — Full OBD-II scan (DTCs + PIDs) with progress log
4. **Results** — Complete diagnosis: safety level, hypotheses, cost estimates, DIY eligibility

## OBD Protocol

The app speaks the ELM327 AT command set over Bluetooth Classic RFCOMM:

| Command | Purpose |
|---------|---------|
| `ATZ` | Reset adapter |
| `ATE0` | Echo off |
| `ATSP0` | Auto-detect vehicle protocol |
| `0101` | Monitor status (MIL + DTC count) |
| `03` | Read stored DTCs |
| `07` | Read pending DTCs |
| `0105` | Coolant temperature |
| `010C` | Engine RPM |
| `010D` | Vehicle speed |
| `0142` | Battery voltage |
| `0106/07` | Fuel trim (short/long) |

## Key Files

| File | Purpose |
|------|---------|
| `src/services/BluetoothService.js` | Bluetooth Classic SPP connection manager |
| `src/services/OBDService.js` | ELM327 command protocol + DTC/PID parsing |
| `src/services/ApiClient.js` | HTTP client for LYLO Flask backend |
| `src/screens/ConnectScreen.js` | Device discovery + pairing UI |
| `src/screens/ScanScreen.js` | Full vehicle scan with progress |
| `src/screens/ResultsScreen.js` | Diagnosis results display |

## Hardware

**OBDLink MX+** by OBD Solutions
- Bluetooth Classic (SPP/RFCOMM)
- Supports all OBD-II protocols (CAN, ISO 9141, KWP2000, J1850)
- ELM327-compatible command set

Pair the adapter in Android Bluetooth settings before opening the app.
The app will show it in the device list with an "OBDLink" badge.
