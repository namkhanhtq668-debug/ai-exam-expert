# Login Refactor Plan: Custom Auth -> Supabase Auth

Goal: migrate `login_screen()` from custom username/password auth in `users_pro` to Supabase Auth with minimal downtime.

## Phase 1: Prepare
1. Create a staging Supabase project or staging environment on the same project.
2. Confirm the app uses the `anon` key only in Streamlit secrets.
3. Keep the current login flow running while the database migration is being applied.
4. Seed `admin_users` for the initial admin accounts.
5. Back up the database before any destructive cleanup.

## Phase 2: Database Cutover
1. Apply `supabase/migrations/20260401_security_hardening.sql`.
2. Backfill `users_pro.user_id` from existing users.
3. Backfill `exam_history.user_id` and `usage_events.user_id` from the mapped owner.
4. Verify RLS with a normal user and an admin user.
5. Verify the system report page only works for admin.

## Phase 3: App Refactor
1. Replace the login tab logic with Supabase Auth:
   - `sign_up`
   - `sign_in_with_password`
   - `sign_out`
2. Map the Supabase user into `st.session_state["user"]`.
3. Stop reading or writing passwords in `users_pro`.
4. Keep `users_pro` only for profile and business data.
5. Replace any direct password reset token UI with Supabase Auth password recovery or RPC-only reset flow.

## Phase 4: Dual Run / Low Downtime
1. Keep the old login path behind a temporary feature flag.
2. If the Supabase Auth login succeeds, prefer it; otherwise keep the old path only for fallback during transition.
3. Log every fallback usage so it can be measured and removed.
4. Do not show plaintext reset tokens in the UI at any time.

## Phase 5: Clean Up
1. Remove legacy custom password logic from `users_pro`.
2. Remove direct client writes to sensitive columns.
3. Drop plaintext token columns after the migration window closes.
4. Tighten grants if the app moves to RPC-only writes.

## Rollback Plan
1. Keep the old branch and the previous deployment ready.
2. If the new auth flow fails in production, switch the app back to the legacy login feature flag.
3. Do not roll back the RLS migration unless there is a critical production incident.

## Success Criteria
1. Users can log in with Supabase Auth.
2. Each user sees only their own rows.
3. Only admin can see system-wide metrics.
4. No plaintext reset token is ever rendered.
5. No service_role key is used by the Streamlit app.
