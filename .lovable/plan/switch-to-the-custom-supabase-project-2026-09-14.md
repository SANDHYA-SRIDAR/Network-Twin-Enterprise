# Switch to the custom Supabase project

## Scope
- Add a browser-safe Supabase client initialized with `https://dgyhkcxnolueumekejkh.supabase.co` and the supplied publishable key.
- Preserve persistent sessions, token refresh, preview-safe storage, and opaque publishable-key request handling.
- Update all application authentication, topology, recommendations, realtime, and bearer-token imports to use the custom client.
- Leave Lovable’s generated client file unchanged because it is managed and may be regenerated.

## Validation
- Confirm the app compiles against the existing generated database types.
- Verify the public sign-in screen loads and requests target the custom project domain.
- Report if the custom project still needs the NexusTwin schema, auth providers, or realtime publication configured.

## Technical note
The supplied `sb_publishable_…` value is designed for browser use. No server-only secret will be introduced.
