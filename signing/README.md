# Debug signing key

`debug.keystore` is the **stable** debug-signing key for the Android build.
It is committed on purpose. Here is why, and what it does and does not
protect.

## Why it is committed

`buildozer android debug` does not declare a signing config — p4a's
`build.tmpl.gradle` defines `signingConfigs.release` only, from the
`P4A_RELEASE_*` environment variables — so the Android Gradle Plugin falls
back to its own default debug key and generates a fresh one when it cannot
find an existing one. CI starts from a clean runner and caches only
`~/.buildozer` and `.buildozer`, so **every build signed with a brand-new
key**.

That is invisible in the build log and produces a perfectly valid APK, so it
looked fine. On the phone it is fatal. Android identifies an installed app by
package name *and* signing certificate, so installing a newer build over an
older one fails the signature check, and One UI reports it as a bare
"App not installed" with no reason given. The certificate in the APK
published on 2026-09-09 has `notBefore = 06:07:09`, inside that run's own
build window — the proof that the key was minted during the build.

Caching `~/.android` would not fix it either: a cache miss (eviction, a key
change, a cleared cache) silently rotates the key again, which is exactly how
the stale-dist cache bug bit this workflow once already. A committed file
cannot miss.

## Why the workflow re-signs instead of planting this file

The obvious approach is to copy this keystore to
`~/.android/debug.keystore` and let AGP pick it up. Run 8 of the workflow
did exactly that and AGP signed with a new key anyway — `90a88072…` where
the committed key is `b7e7298e…`. Neither buildozer nor p4a sets
`ANDROID_SDK_HOME`, `ANDROID_PREFS_ROOT` or `ANDROID_USER_HOME`, so where
AGP looked instead is unclear, and it is not something this workflow can
depend on.

So the build lets gradle sign with whatever throwaway key it likes, and
then replaces the signature with `apksigner sign --ks signing/debug.keystore`.
apksigner takes the key as an argument and cannot be wrong about which one
it used. Signing an APK twice is ordinary: the second signature replaces
the APK Signing Block outright.

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

After re-signing, the workflow asserts that the APK's certificate matches
that fingerprint and that the archive is still 4-byte aligned. Both are
checked rather than trusted, because a wrongly signed APK is still a
structurally valid APK — the failure shows up only on the phone, as
"App not installed" with no reason given.
