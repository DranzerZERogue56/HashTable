# Debug signing key

`debug.keystore` is the **stable** debug-signing key for the Android build.
It is committed on purpose. Here is why, and what it does and does not
protect.

## Why it is committed

`buildozer android debug` does not declare a signing config, so the Android
Gradle Plugin falls back to its default debug key at
`$HOME/.android/debug.keystore` — and generates a fresh one if that file is
missing. CI starts from a clean runner and only caches `~/.buildozer` and
`.buildozer`, so `~/.android` was never restored: **every build signed with a
brand-new key**.

That is invisible in the build log and produces a perfectly valid APK, so it
looked fine. On the phone it is fatal. Android identifies an installed app by
package name *and* signing certificate, so installing a newer build over an
older one fails the signature check, and One UI reports it as a bare
"App not installed" with no reason given. The certificate in the APK
published on 2026-09-09 has `notBefore = 06:07:09`, inside that run's own
build window — the proof that the key was minted during the build.

Caching `~/.android` would not fix it: a cache miss (eviction, a key change,
a cleared cache) silently rotates the key again, which is exactly how the
stale-dist cache bug happened earlier. A committed file cannot miss.

## What it is not

This is a **debug** key with the conventional debug credentials
(store/key password `android`, alias `androiddebugkey`, `CN=Android Debug`),
the same identity every Android SDK generates locally. It is not secret and
gives no one anything they could not already do: a debug-signed APK is
refused by Play and warned about by Play Protect.

The only thing it confers is the ability to build an APK that Android would
accept as an upgrade to a sideloaded copy of `org.hashtable.gogame`, which is
the point of having it.

**Never reuse this key for a Play Store release.** A release key must be
generated privately and kept out of the repository — losing it or leaking it
is unrecoverable, because the store identity of an app is its signing key.

## Details

    alias      androiddebugkey
    store type PKCS12
    passwords  android  (both store and key)
    key        RSA 2048, valid until 2056-09-04
    SHA-256    B7:E7:29:8E:F0:A1:C8:6D:BE:C1:8F:2A:21:4A:C0:62:EF:E1:65:1A:8A:41:15:7A:FC:87:96:C3:6B:32:22:DA

The workflow copies this file to `~/.android/debug.keystore` before building
and then asserts that the APK's certificate matches that fingerprint, so a
rotation fails the build loudly instead of shipping an APK that will not
install.
