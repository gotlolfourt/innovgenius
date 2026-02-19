# Quick Testing Guide - Admin Panel Data Flow

## Start Here

### 1. Clear Database & Start Fresh
```bash
cd "d:\Coding\Projects\Hackathon Projects\Innovegenius Hackathon"
rm instance/nexabank.db
python app.py
```

### 2. Open Browser
- **Customer Portal**: http://localhost:5000
- **Admin Panel**: http://localhost:5000/admin
- **Admin Login**: admin / admin123

### 3. Open Browser Console
- Press `F12` or Right-Click → Inspect → Console tab
- This is where you'll see all the data flow logs

## Step-by-Step Test

### Step 1: Identity Entry
```
👉 Click "Start Verification"
💬 You'll see the onboarding chat
📝 Enter your name (e.g., "John Doe")
📝 Enter DOB (e.g., "1995-03-15")
📝 Enter email (e.g., "john@test.com")
📝 Enter phone (e.g., "+91-9876543210")

✅ In Console, look for:
   [Identity] Submitting: {app_id: 'NXB-...', name: 'John Doe', email: 'john@test.com'}
   [Identity] Response: {success: true, application_id: 'NXB-...'}

✅ In Flask Server output, look for:
   [Identity] Received submission: app_id=NXB-..., from_session=True
   [Identity] ✓ Verified saved to DB: name=John Doe, email=john@test.com
```

### Step 2: Document Upload
```
📄 Click to upload or simulate document (Aadhaar/PAN/Passport)
⏳ Wait for OCR processing
✅ In Console, look for:
   [Document] Uploading Aadhaar for app_id: NXB-...
   [Document] Upload response: {success: true, file_hash: '...', ...}

✅ In Flask Server, look for:
   [Document] Saving to database
   [Document] ✓ Verified saved to DB
```

### Step 3: Selfie Capture
```
📸 Click to take selfie or simulate
⏳ Wait for facial recognition
✅ In Console, look for:
   [Selfie] Uploading for app_id: NXB-...
   [Selfie] Upload response: {success: true, face_score: 85, selfie_stored: 'NXB-..._selfie.jpg'}

✅ In Flask Server, look for:
   [Selfie] Storing selfie for app_id=NXB-...
   [Selfie] ✓ Verified saved to DB: path=NXB-..._selfie.jpg, score=85
```

### Step 4: OTP Verification
```
🔐 You'll see OTP code in message (e.g., "123456")
📝 Enter the 6-digit code
⏳ Wait for verification

✅ In Console, look for:
   [verifyOTP] Verification request: {app_id: 'NXB-...', hash: '...'}
   Success: "✅ OTP verified! Identity confirmed"
```

### Step 5: Risk Evaluation
```
⏳ Wait as system analyzes 5 factors:
   - Analyzing document integrity
   - AML watchlist screening
   - Cross-referencing CIBIL
   - Computing biometric confidence
   - Generating composite risk score

✅ In Console, look for:
   [runRiskEval] Starting, S.appId: NXB-...
   [runRiskEval] Calling /api/risk/evaluate with appId: NXB-...
   [runRiskEval] Response received: {risk_level: 'Low', account_number: '1234 5678 9012', ...}

✅ In Flask Server, look for:
   [Risk] Computed risk for NXB-...: level=Low, score=28
   [Risk] Generated account 1234 5678 9012 for Low risk
   [Risk] ✓ Verified saved to DB: risk=Low, status=Approved, account=1234 5678 9012
```

### Step 6: Success Page
```
✅ You should see:
   - Account created confirmation
   - Application ID: NXB-...
   - Account Number: 1234 5678 9012
   - IFSC: NXBA0001234
```

### Step 7: Admin Panel View
```
👉 Go to http://localhost:5000/admin
🔑 Login: admin / admin123
📋 You should see the application in the recent list
🔍 Click "Review" button on your application

✅ Modal should show ALL fields populated:
   ✓ Name: John Doe
   ✓ Email: john@test.com
   ✓ DOB: 1995-03-15
   ✓ ID Type: Aadhaar
   ✓ Face Score: 85% (Matched)
   ✓ Risk: Low (28/100)
   ✓ Status: Approved
   ✓ Account: 1234 5678 9012
   ✓ IFSC: NXBA0001234

✅ IMPORTANT: NO "undefined" values should appear!

✅ In Console, look for:
   [Admin] Loading application details for: NXB-...
   [Admin] Application data received: {application: {...}, documents: [...], ...}
   [Admin] Application fields: id,name,email,dob,phone,id_type,selfie_path,face_score,face_status,otp_verified,risk_level,risk_score,status,account_number,ifsc,...
```

## Debugging Undefined Values

### If Admin Shows "undefined" for Name/Email
```
1. Check browser console for [Admin] logs
2. Check Flask output for [Admin] Application fields: ...
3. If fields are missing from the list, they weren't saved to DB
4. Look back at [Identity], [Document], [Selfie], [Risk] logs for ✗ failures
```

### If Account Number is Missing
```
1. Check [Risk] output: "Computed risk for NXB-...: level=..."
2. Account numbers only generated for Low/Medium risk
3. If risk is High, status will be "Escalated" and no account generated (expected)
4. Check [Risk] "Generated account..." log
```

### If Risk Score Shows 0
```
1. Check [Risk] "Computed risk..." in Flask output
2. May indicate missing document or face score data
3. Verify [Document] and [Selfie] were successful
```

## Console Log Cheatsheet

Copy these into browser console to filter logs:

```javascript
// Show only Identity logs
console.log = (function() {
  const orig = console.log;
  return function(...args) {
    if (args[0]?.includes?.('[Identity]')) orig.apply(console, args);
  };
})();

// Show all custom logs (prefixed with [])
for (const prefix of ['[Identity]', '[Document]', '[Selfie]', '[doOTP]', '[runRiskEval]', '[Admin]', '[API']) {
  // search for them
}
```

## Common Issues & Fixes

| Issue | Check | Fix |
|-------|-------|-----|
| Admin shows all undefined | Is app loaded at all? | Complete full onboarding first |
| Name/Email undefined | [Identity] logs | Check Flask log for ✓ Verified saved |
| Account number undefined | [Risk] logs | Is risk Low/Medium? (not High) |
| No data in admin list | Did onboarding succeed? | Check success screen appeared |
| 404 when viewing app | Is app_id correct? | Verify in console logs |
| Database locked errors | Server issue? | Restart Flask (python app.py) |

## Key Success Indicators

### Frontend (Browser Console)
```
✅ [Identity] Response: {success: true}
✅ [Document] Upload response: {success: true}
✅ [Selfie] Upload response: {success: true}
✅ [verifyOTP] Success page shown
✅ [runRiskEval] Response received with all fields
✅ [Admin] Application fields: ...shows many fields...
```

### Backend (Flask Server Output)
```
✅ [Identity] Received submission
✅ [Identity] ✓ Verified saved to DB
✅ [Selfie] ✓ Verified saved to DB
✅ [Risk] Computed risk...
✅ [Risk] ✓ Verified saved to DB
✅ [Admin] Application loaded with fields
```

## Test Complete When:
- ✅ Full onboarding flow completes without errors
- ✅ Success page shows all account details
- ✅ Admin panel loads application
- ✅ Admin panel shows NO undefined values
- ✅ All fields populated: name, email, risk, account, etc.
- ✅ Logs show ✓ success indicators throughout
