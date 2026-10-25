# Dynamic profiles migration

The existing database uses SQLAlchemy's `records(id, kind, data)` table. That architecture is retained. Student IDs are the stable `data.identity` values, exposed as `id` by `/students`; SQL record IDs are separate internal storage keys.

Before any application data changes, SQLite's backup API copied the workspace database to `backups/campusswap-before-profiles-20261025-014531.db`. The automatic startup migration also creates a timestamped `backups/*-before-students-*.db` copy for an existing populated database. Backups include private negotiation limits/session tokens and are ignored by Git.

The original database contained 2 students, 8 listings, 14 negotiations, and 28 sessions. `dynamic_students_v1` performs a transactional, additive upgrade:

- Keep `student-a` and `student-b` stable, preserving every listing owner, negotiation participant, session reference, and approval key.
- Map the known original Alex Rivera demo profile to the display name Abbhijit and the known Maya Chen demo profile to Shorya Moses. Retain the original name and legacy display-name metadata on disk. Custom display names are preserved.
- Add Oumar under `student-c`, once. The three initial role hints are descriptive; every student may buy or sell.
- Enrich profiles with optional university, optional course/major, and a creation timestamp. For legacy profiles without a creation time, that timestamp is the upgrade time.
- Preserve any referenced legacy student ID missing a profile by creating a compatibility profile rather than reassigning ownership.
- Add a unique SQLite index on student identity values and a versioned migration marker. No table/column is removed, no database reset occurs, and no listing or negotiation record is rewritten.

After startup, a direct comparison against the pre-upgrade backup verified that every existing listing, negotiation (including private preferences, transcript, status, and approval flags), and session was identical on disk. SQLite integrity_check returned `ok`. Public display names resolve through the profile relationship, so existing history now displays the team names while preserving historical storage.

New profiles use generated `student-<UUID>` IDs. Creating a listing derives its seller ID from the server-managed cookie; starting a negotiation derives the buyer from that cookie and the seller from the listing. No endpoint accepts a name or role as authorization. Input includes only public profile metadata; private seller limits and buyer preferences remain in their original backend records.

Automated coverage creates a separate legacy database, migrates it in a fresh Python interpreter, compares the original records, verifies its backup, repeats startup without changes, and reuses an old session token to inspect the preserved confirmed negotiation. Other tests cover arbitrary student pairs, reversed buyer/seller roles, correct agent context assignment, private data isolation, and unrelated third-party rejection.

Production authentication, normalized SQL foreign keys, profile deletion/editing, and multiple-worker transactions remain future work. The public local demo switcher intentionally lets a person select any profile; it is not proof of real-world student identity. APP_ENV=production disables demo profile/session operations. Judge Mode is a separately opt-in local diagnostic and is disabled by default.
