# Ada SMS Gateway — بوابة رسائل أدا (Android)

Sends Ada's sign-in codes from the SIM card of the owner's Android phone, with no third party involved.

- **Pairing:** in Ada go to Settings → SMS phone → *Show pairing code*, or use *First-time setup* on the login screen. Scan the QR, or paste the code.
- **Protocol:** the app long-polls `POST /api/v1/sms-gateway/claim?wait=25`, sends each SMS, and then reports the result with `POST /api/v1/sms-gateway/{id}/ack`.
- **Safety:** HTTPS only, the token is encrypted in the Keystore, the app only texts numbers on the allow-list from the pairing code, it sends at most 30 per hour, and it never backs up its data.
- **Build:** `./gradlew assembleRelease` (JDK 17, Android SDK 35). CI publishes the APK as an artifact, and as a release asset on `ada-v*` tags.
- **Tips:** keep the phone charging and online, disable battery optimisation (there's a button for this in the app), and make sure the SIM has SMS credit.
