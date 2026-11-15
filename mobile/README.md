# The H.E. Jobs app on the App Store and Google Play

The store apps are the `/app/` page (job alerts, rotation tracker, EOD kit list) wrapped with [Capacitor](https://capacitorjs.com), so there's one app to look after, not three. What the store versions add:

- **Payments through the store.** Apple and Google require subscriptions bought inside an app to go through them, so the apps sell the same $10-a-year subscription (first month free) as an in-app purchase (shown as the local price, e.g. $5.99). [RevenueCat](https://www.revenuecat.com) (free up to $2,500 a month of revenue) keeps track of who has paid; the alerts Worker asks RevenueCat and switches the account on. Website (Stripe) subscribers can still type their code into the app.
- **Real phone notifications** through Firebase Cloud Messaging (free). The "Job alerts" Action sends them alongside the web ones.
- Offline rotation tracker, share sheet for the CSV and calendar files, links opening in an in-app browser, restore purchases, and delete-account (both stores require it).

## How it fits together

| Piece | Where |
| --- | --- |
| The page | `scripts/app.html` (shared with the website). It checks for `window.HEJNative` and uses store payments and Firebase when it's there. |
| Native helpers | `mobile/src/native.js`, bundled into `www/native.js` |
| Building `www/` | `mobile/build-www.mjs` takes `app/index.html`, points links at the website and drops the site menu |
| iPhone / Android projects | `mobile/ios`, `mobile/android` (made by Capacitor; icons from `mobile/assets` via `npm run assets`) |
| Payments check | `alerts/worker.js`: `POST /api/store/sync`, secret `REVENUECAT_SECRET_KEY` |
| Notifications | `alerts/send_alerts.py`, secret `FCM_SERVICE_ACCOUNT` |
| Builds and uploads | `.github/workflows/store-apps.yml` (free: the repository is public) |
| Store text | `mobile/store/listing.md` |

Product and entitlement names the code expects: entitlement **`alerts`**, product id **`hej_alerts_yearly`** (yearly auto-renewing), RevenueCat offering **default** with an **Annual** package.

## What Dobbo needs to do (Claude can't make accounts or pay)

Costs: Apple $99 a year, Google $25 once. Everything else is free at our size. Apple and Google keep 15% of each subscription (Apple only after you join the Small Business Program, step 1).

1. **Apple Developer Program**: enrol at developer.apple.com/programs/enroll with your Apple ID ($99/yr). Then join the App Store Small Business Program (developer.apple.com/app-store/small-business-program) so Apple takes 15% instead of 30%.
2. **Google Play Console**: sign up at play.google.com/console ($25 once, ID check). A new personal account must run a closed test with at least 12 testers for 14 days before the app can go public. The Facebook group can supply those.
3. **App Store Connect**: My Apps, + New App: platform iOS, name "HE Jobs: Hostile Environment", bundle ID `com.hostileenvironmentjobs.app` (register it under Certificates, Identifiers & Profiles first, ticking Push Notifications), SKU `hej-app`. Then under Monetization, Subscriptions: a group "Job alerts" with one auto-renewable subscription, product ID `hej_alerts_yearly`, 1 year, $5.99. Sign the Paid Apps agreement and add bank and tax details (Business section).
4. **Firebase** (console.firebase.google.com, free): new project "HE Jobs", add an Android app (`com.hostileenvironmentjobs.app`) and an iOS app (same ID). Download `google-services.json` and `GoogleService-Info.plist` and send them to Claude (or put them in `mobile/firebase/`). In Project settings, Cloud Messaging, upload an APNs key (made in Apple Developer, Keys, + with "Apple Push Notifications service"). In Service accounts, Generate new private key, and add the whole JSON file as the GitHub secret `FCM_SERVICE_ACCOUNT`.
5. **RevenueCat** (app.revenuecat.com, free): new project, add the App Store app (with an App Store Connect in-app purchase key) and the Play Store app (with a Google service account, their guide walks through it). Make entitlement `alerts`, attach both products, and an offering "default" with an Annual package. Then:
   - Add the two **public** SDK keys (appl_… and goog_…) as GitHub repository **variables** `REVENUECAT_IOS_KEY` and `REVENUECAT_ANDROID_KEY`.
   - Add a **secret** API key (v1, sk_…) to the Cloudflare Worker as the secret `REVENUECAT_SECRET_KEY`.
6. **Signing keys for the automatic builds** (GitHub repo, Settings, Secrets and variables, Actions):
   - Android upload key: in Terminal run `keytool -genkeypair -v -keystore upload.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000`, pick a password, then `base64 -i upload.jks | pbcopy` and paste as `ANDROID_KEYSTORE`; the password as `ANDROID_KEYSTORE_PASSWORD`. Keep `upload.jks` somewhere safe.
   - App Store Connect API key: Users and Access, Integrations, App Store Connect API, + with role App Manager. Secrets `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8` (the whole .p8 file text) and `APPLE_TEAM_ID` (Membership page).
   - Google Play upload key: in Play Console, Setup, API access, link a Google Cloud service account with Release permissions; its JSON as `PLAY_SERVICE_ACCOUNT`.
7. **First Android upload by hand**: Google insists the very first build is uploaded in Play Console. Run the "Store apps" Action, download the `.aab` from the run's artifacts and upload it to Internal testing. After that, every build goes up on its own.
8. **Store listings**: copy the text from `mobile/store/listing.md`, screenshots from the project files (`eod-jobs-site/store-apps/screenshots/`), fill in the privacy questionnaires with the answers in the same file, and submit for review.
9. When both are live, paste the store links into `STORE_LINKS` at the top of `scripts/app.html` (or ask Claude) so the website shows the badges.

## Building by hand

```
cd mobile
npm ci
npm run sync           # rebuild www/ from app/index.html and copy it into ios/ and android/
npx cap open ios       # Xcode (Mac only)
npx cap open android   # Android Studio
```
