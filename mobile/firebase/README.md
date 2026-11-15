Put the two Firebase files here (see mobile/README.md, step 4):

- `google-services.json` (Android app)
- `GoogleService-Info.plist` (iOS app)

They aren't secret (Google ships them inside every app), so they can live in the repository.
The "Store apps" Action copies them into the Android and iPhone projects before building.
