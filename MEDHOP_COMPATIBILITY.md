# MedHop compatibility branch

This branch packages the local TurboDrone changes used by [MedHop](https://github.com/ijunsu2082-hue/medhop). It is based on upstream `master` at `2c09cf8`.

## Checkout

```sh
git clone https://github.com/ijunsu2082-hue/turbodrone-medhop.git
cd turbodrone-medhop
git switch medhop-integration
```

Point MedHop at this checkout by setting `MEDHOP_TURBODRONE_BACKEND` to its `backend` directory.

## Changes in this branch

- WiFi UAV command, telemetry, and MCU packet handling used by MedHop.
- Flight controller calibration and speed behavior.
- Updated web video command handling.
- Follow-target tracking, status UI, and video recording additions.

MedHop currently uses the calibration/speed behavior, held WiFi UAV command pulses, MCU telemetry hook, and command-aware video request. The follow UI and recorder are included from the local work but are not required by MedHop's current integration.

## Limitations and local setup

This software is experimental. Passing unit tests does not establish flight safety; verify behavior with the aircraft secured and follow the drone's safe-use instructions before any flight.

The web backend exposes control and recording endpoints without authentication and configures permissive CORS. Run it only on a trusted local network and do not expose it to the public internet.

Local credentials, video files, model weights, and the local Netlify site binding are excluded from this branch.
