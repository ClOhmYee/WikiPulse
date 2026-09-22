# Authentication UI handoff

Preserve the inherited dark navy workspace surfaces, teal actions, typography, and focus treatment. This is a narrow extension of the workspace, not a new visual direction. Input borders use `#5b707b` for at least 3:1 contrast against both the input and dialog surfaces.

`AuthModal` uses a native modal dialog with an accessible name and description, focus containment, initial field focus, and restoration to the opening control. Login and signup share the dialog. Required fields, email format, signup password length, password confirmation, and nonblank nickname are validated. Pending requests disable form controls; closing aborts the request, and requests time out after 15 seconds.

`client.js` targets the future draft contract documented in `docs/api-v0.3.md`: `/auth/login`, `/auth/signup`, and `/me`, under `VITE_API_BASE_URL` or `/api/v1`. These endpoints are not implemented by this frontend work. Unsupported services display an error; there is no local authentication fallback.

Only a login response containing a token and valid member establishes the authenticated UI. The token is stored in `sessionStorage` and restored identity is revalidated through `/me`. Passwords are not stored. Logout clears the token and member state. My Page and Saved navigation entries and their route content require a member.

Bookmarks remain browser-local and shared across accounts on the same browser. Authentication gates access to the Saved page; it does not make bookmarks account-owned or synchronize them with a server.

`frontend/e2e/auth.spec.js` contains four intercepted auth tests covering guest navigation and keyboard/mobile dialog behavior; login, session restoration, and logout; signup validation and request fields; and unsupported/malformed login responses. These checks verify client behavior against intercepted responses, not live backend authentication.
