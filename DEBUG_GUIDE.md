# NexaBank Debug Guide - Session ID Persistence Issue

## Overview
This guide helps diagnose the issue where `S.appId` becomes undefined between `startOnboarding()` and `doOTP()`, causing "Missing application_id" errors in OTP verification.

## Comprehensive Logging Added

The following improvements have been made to track state flow:

### 1. **API Function Logging** 
Every API call now logs:
- Request method, path, and body
- Response data or error message
```
[API POST] /api/session/start
[API Response] /api/session/start {application_id: 'NXB-XXXX'}
```

### 2. **ensureAppId() Logging**
Clear indicators of session creation vs. reuse:
```
[ensureAppId] REUSING existing appId: NXB-12345678
[ensureAppId] Creating NEW session (S.appId is currently: undefined)
[ensureAppId] ✓ Session created: NXB-ABCDEF01
[ensureAppId] Returning appId: NXB-ABCDEF01
```

### 3. **startOnboarding() Logging**
Guards against accidental restarts + clear state tracking:
```
>>> START ONBOARDING - current S.appId: null
>>> Calling ensureAppId from startOnboarding
>>> ensureAppId returned, S.appId now: NXB-ABCD1234
>>> startOnboarding complete, S.appId: NXB-ABCD1234
```

### 4. **handleStep() Logging**
Tracks identity collection phase:
```
[handleStep] Ensuring appId, current value: NXB-ABCD1234
[handleStep] After ensureAppId, value is: NXB-ABCD1234
```

### 5. **OTP Flow Logging**
Critical debugging for doOTP() and verifyOTP():
```
[doOTP] Starting, current S.appId: NXB-ABCD1234
[doOTP] After ensureAppId, S.appId: NXB-ABCD1234
[doOTP] Proceeding with appId: NXB-ABCD1234
[doOTP] Generated OTP hash, storing with app_id: NXB-ABCD1234

[verifyOTP] Entered digits: 123456 Current S.appId: NXB-ABCD1234
[verifyOTP] After ensureAppId, S.appId: NXB-ABCD1234
[verifyOTP] Verification request: {app_id: 'NXB-ABCD1234', hash: '5f4dcc...'}
```

### 6. **Risk Evaluation Logging**
Final stage tracking:
```
[runRiskEval] Starting, S.appId: NXB-ABCD1234
[runRiskEval] Calling /api/risk/evaluate with appId: NXB-ABCD1234
[runRiskEval] Response received: {risk_level: 'Low', ...}
```

## How to Debug

1. **Open Browser Console**
   - Press `F12` or right-click → "Inspect" → "Console" tab
   - Filter for `[` to see only our custom logs

2. **Step Through the Flow**
   - Click "Start Verification"
   - Watch for `>>> START ONBOARDING` log
   - Check that `S.appId:` appears and has a value like `NXB-ABCDEF01`
   - Enter your name, DOB, email, phone
   - Check `[handleStep]` logs for each step
   - Upload documents and selfie
   - Watch for `[doOTP]` logs

3. **Key Things to Look For**
   
   ✅ **Good Signs:**
   - Initial `[ensureAppId] ✓ Session created: NXB-XXXXXXXX`appears once
   - All subsequent logs show `[ensureAppId] REUSING existing appId: NXB-XXXXXXXX`
   - Each function shows a valid appId like `NXB-ABCD1234`
   
   ❌ **Bad Signs:**
   - Multiple `✓ Session created` messages (means ensureAppId() called multiple times)
   - `S.appId: undefined` or `null` in critical functions
   - `[ensureAppId] Creating NEW session` appearing multiple times
   - `[API Error]` for /api/session/start repeatedly

4. **If S.appId Keeps Resetting**
   - Check if a page reload is happening (look for `>>> START ONBOARDING` appearing repeatedly)
   - Check if any JavaScript errors are clearing the S object
   - Verify that all `await ensureAppId()` calls are actually being awaited

5. **If OTP Store Fails with "Missing application_id"**
   - Check `[doOTP] After ensureAppId, S.appId:` to see what value it has
   - If undefined, then ensureAppId() didn't work properly
   - Check the backend server logs (Flask output) for any errors in `/api/session/start`

## Admin Panel Data Issue

The admin panel shows "undefined" for data fields because:
- S.appId wasn't being passed to API calls → applications table not seeded with proper IDs
- Identity/document/risk data wasn't saved because application_id was missing
- Once S.appId persistence is fixed, data should flow properly

**How to verify fix:**
1. Complete full onboarding flow
2. Go to Admin Panel (`/admin`)
3. Login with admin / admin123
4. Check if new applications appear with complete data

## Backend Debug Output

The Flask server logs also print debugging info:
```
DEBUG OTP Store: session.get("app_id") = NXB-ABCD1234, data.get("application_id") = NXB-ABCD1234
DEBUG: Session keys: ['app_id']
```

If these show `None` values, it means the frontend isn't sending appId correctly.

## Common Issues & Fixes

| Issue | Console Log | Likely Cause | Fix |
|-------|-------------|--------------|-----|
| OTP "Missing application_id" | `[doOTP] Starting, current S.appId: undefined` | ensureAppId() not working | Check network tab for /api/session/start failures |
| "Session created" repeating | Multiple `✓ Session created` logs | startOnboarding() being called repeatedly | Check for page reloads or JavaScript errors |
| Admin shows "undefined" | OTP verify succeeds but admin data missing | Data not saved to DB due to missing appId | Complete flow and verify identity endpoint responds with success |
| Offline mode triggering | `[ensureAppId] ✗ API failed` | Server not running or not accessible | Verify Flask server is running at localhost:5000 |

## Testing Checklist

- [ ] Start Verification button clicked
- [ ] See `>>> START ONBOARDING` and appId being created
- [ ] Enter name, DOB, email, phone - verify handleStep logs show appId
- [ ] Upload document and selfie
- [ ] See `[doOTP] Starting` with valid appId
- [ ] Enter OTP code (shown in message bubble)
- [ ] See `[verifyOTP] Verification request` with valid appId  
- [ ] Success page shows account number and confirmation
- [ ] Admin panel shows new application with complete data

## Still Having Issues?

1. **Screenshot the console** during the problematic step
2. **Note the exact error message** in the UI
3. **Check Flask server output** for backend errors
4. **Enable Network tab** (DevTools → Network) to see:
   - POST to /api/session/start → returns what?
   - POST to /api/otp/store → what error response?
   - POST to /api/otp/verify → what response?

## Implementation Notes

- S object is initialized with `appId: null` at page load
- ensureAppId() is a singleton pattern - checks if exists before creating
- All async operations that need appId should `await ensureAppId()` first
- Offline mode fallback uses `NXB-OFFLINE-` prefix for testing without server
- Flask sessions are cookie-based (credentials: 'include' in fetch calls)
