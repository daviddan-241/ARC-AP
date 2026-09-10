"""The agent's OWN email — a logged-in webmail tab in the persistent browser.

The operator logs into the agent's email account ONE time through the in-app
browser (the same persistent Chromium profile the agent uses). From then on
the agent opens the webmail on demand — completely headless and automatic:

  * reads the inbox,
  * extracts verification/OTP codes from fresh mail,
  * completes arena.ai (or any site's) code-based login by itself,
  * and can use the mailbox for signups/confirmations via tools.

No credential fields ever appear in the UI; access rides on cookies in the
shared browser profile.
"""
