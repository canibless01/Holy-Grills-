# Holy Grills Android acceptance build

Version 1.0.1 (build 2), package `com.holygrills.app`, signed with the permanent Holy Grills release identity. Source: `android-app`, commit `613bb61`. This branch hosts versioned APKs because the current connection cannot upload release assets.

This APK is for owner acceptance, not an activated customer download. It installs as **Holy Grills**, separately from the earlier **Holy Grills (Test)** package.

Includes native pull-to-refresh, bounded read recovery, Maps loading/retry/GPS fallback, native reward actions and branded notification artwork. The Maps key must allow `https://localhost/*`. Google Maps/GPS need physical-device confirmation. Backend Android reward compatibility and HTTPS App Links require deployment from PR #93. A completed Paystack card challenge/return still needs acceptance.

The APK contains no signing private key or signing passwords. Keep the separate owner signing backup private. Customer installation/update banners remain controlled by the website release manifest.
