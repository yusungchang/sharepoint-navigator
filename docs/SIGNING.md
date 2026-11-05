# Signing

The macOS app is signed with the owner's Developer ID and notarized by Apple from 1.3.0 on, so it opens
without the "can't verify" warning and Open Anyway step. Windows stays unsigned (owner's decision, as for
PDF Epsilon): SmartScreen keeps asking More info, Run anyway.

The same Apple Developer Program membership, certificate and app-specific password serve PDF Epsilon
(see its docs/SIGNING.md for how they were made and the renewal dates).

## One-off setup (owner)

1. **The certificate as .p12.** The "Developer ID Application" certificate is already in the login
   keychain. The keychain holds other identities too, so export only this one: Keychain Access, login,
   My Certificates, right-click "Developer ID Application: …", Export, as `.p12` with a password. Keep
   it outside the project (the PDF Epsilon export works if it was kept).
2. **App-specific password** from https://account.apple.com (Sign-In and Security, App-Specific
   Passwords). The one made for PDF Epsilon works too.
3. **Run `tools/signing/setup-mac.sh`** in a terminal. It asks for the `.p12` path and password, the
   Apple ID and the app-specific password, checks them with Apple's notary service, and stores these
   repository secrets with `gh`:

   | Secret | Value |
   |---|---|
   | `APPLE_CERTIFICATE` | the `.p12`, base64-encoded |
   | `APPLE_CERTIFICATE_PASSWORD` | its password |
   | `APPLE_SIGNING_IDENTITY` | `Developer ID Application: <name> (<team id>)` |
   | `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` | the Apple ID, the app-specific password, the Team ID |

4. Try a build without releasing: `gh workflow run build.yml --ref main`, then download the zip from the
   run's artifacts and open the app on a Mac.

Repeat steps 1 and 3 when the certificate is renewed, steps 2 and 3 when the Apple ID password changes
(that revokes app-specific passwords).

## How the build signs (`build_app.py`)

- With `APPLE_SIGNING_IDENTITY` set, PyInstaller signs every bundled library and the launcher with it
  (`--codesign-identity`: hardened runtime, secure timestamp). The script then edits `Info.plist`
  (background app, version) and re-signs only the outer bundle, which that edit unsealed, and runs
  `codesign --verify --deep --strict`.
- With `APPLE_ID`, `APPLE_PASSWORD` and `APPLE_TEAM_ID` also set, after the self-check it zips the app,
  sends it to `notarytool submit --wait`, and staples the ticket to the `.app`. Anything but "Accepted"
  fails the build.
- From 1.4.0 the app is released in a `.dmg`, which is signed with the same identity, notarized and stapled
  as well (a second, short submission), so Gatekeeper accepts the dmg when it is opened and the app inside.
- No extra entitlements are needed: the libraries are plain Python extensions, and msal-extensions reaches
  the Keychain through ctypes without callbacks. Checked on 5 November 2026: the signed app passes the
  self-check and serves the page under the hardened runtime.
- Without the variables the app is signed ad hoc, as before 1.3.0.
- Locally the same works from a terminal, e.g.
  `APPLE_SIGNING_IDENTITY="Developer ID Application: …" python build_app.py` (signed, not notarized).

## How CI uses it (`.github/workflows/build.yml`)

- "Mac signing secrets" imports the `.p12` into a throwaway keychain, lets codesign use the key without a
  prompt, installs Apple's Developer ID G2 intermediate, and passes the identity and Apple ID values to the
  build. Without the secrets the build is ad hoc; a `v*` tag without them fails, so a release is never
  unsigned.
- "Check the Mac dmg and app" checks what people get: the dmg's signature, stapled ticket and Gatekeeper's
  verdict for opening it; then, mounted, the app inside: `codesign --verify`, the Developer ID authority,
  `xcrun stapler validate`, and `spctl --assess` must say "Notarized Developer ID" when Gatekeeper is on.
- If notarization ever seems stuck, `xcrun notarytool history` with the same three Apple values shows
  Apple's side.

## Effect on the Keychain prompt

The saved sign-in's key lives in the Keychain (msal-extensions). Its "Always Allow" is tied to the app's
signature. An ad hoc signature changes with every build, so each update asked again. A Developer ID
signature stays the same across versions, so after allowing the first signed version once, updates stop
asking.
