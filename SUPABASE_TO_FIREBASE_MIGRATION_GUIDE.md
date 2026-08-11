# Holy Grills — Supabase to Firebase Migration Guide

This blueprint details the step-by-step technical plan to migrate the **Holy Grills** backend from Supabase (PostgreSQL relational DB + Supabase Auth) to Firebase (Cloud Firestore NoSQL + Firebase Authentication).

---

## 🗺️ Architectural Transition Overview

```
      SUPABASE ECOSYSTEM                     FIREBASE ECOSYSTEM
┌──────────────────────────────┐       ┌──────────────────────────────┐
│ PostgreSQL Relational Tables │  ──►  │ Cloud Firestore Collections  │
│ Supabase Auth (JWT payload)  │  ──►  │ Firebase Auth (Custom Claims)│
│ Database Triggers & Policies │  ──►  │ Cloud Functions & Rules      │
│ PostgREST REST API Client    │  ──►  │ Firebase Admin / Client SDK  │
└──────────────────────────────┘       └──────────────────────────────┘
```

---

## 1. 📂 Data Modeling: Relational SQL to Document-Based NoSQL

Firestore is a document-based NoSQL database composed of **documents** organized inside **collections**. There are no SQL `JOIN`s, so we must denormalize or use nested sub-collections where appropriate.

### A. Core Collection Mappings

| PostgreSQL Table | Firestore Collection Path | Document Schema (JSON) |
|---|---|---|
| `profiles` | `profiles/{uid}` | `{ "full_name": "John Doe", "email": "john@mail.com", "role": "student", "hp_balance": 500, "wallet_balance": 2500.0, "is_active": true, "created_at": TIMESTAMP }` |
| `orders` | `orders/{orderId}` | `{ "user_id": "uid", "status": "received", "total_amount": 1200.0, "is_squad_order": false, "created_at": TIMESTAMP, "items": [...] }` (Denormalized order items inline) |
| `menu_items` | `menu_items/{itemId}` | `{ "name": "Hot Dog", "price": 450.0, "is_featured": true, "category": "combos", "is_active": true }` |
| `menu_addon_groups` | `menu_items/{itemId}/addon_groups/{groupId}` | `{ "name": "Sides", "is_required": false, "min_select": 0, "max_select": 3 }` (Sub-collection) |
| `menu_addons` | `menu_items/{itemId}/addon_groups/{groupId}/addons/{addonId}` | `{ "name": "Coleslaw", "price_delta": 50.0, "is_active": true }` (Sub-collection) |
| `daily_checkins` | `daily_checkins/{checkinId}` | `{ "user_id": "uid", "checkin_date": "2026-07-16", "created_at": TIMESTAMP }` |
| `feature_flags` | `feature_flags/{flagName}` | `{ "is_active": true, "description": "Enables spin prizes", "updated_at": TIMESTAMP }` |

### B. Handling Relationships without Foreign Keys
* **Embedded Sub-collections:** For data scoped to a parent document (e.g., addon groups scoped to a specific menu item, or ticket tiers scoped to an event), use nested collections: `/menu_items/{itemId}/addon_groups/{groupId}`.
* **Denormalization:** For order items and selections, store them directly as a nested array inside the order document (`items: [...]`) rather than a separate table. This prevents multi-collection fetching during order history loading.

---

## 2. 🔑 Authentication & Role-Based Custom Claims

Supabase Auth relies on JWT tokens. In Firebase, we implement role-based access control (RBAC) using **Firebase Auth Custom User Claims**.

### Setting Roles on Firebase Auth (Cloud Functions / Admin SDK)
Create an admin function to set claims. This securely embeds the user's role directly into their Firebase ID token, which cannot be forged.

```javascript
// Node.js Firebase Admin SDK snippet to set role claims
const admin = require('firebase-admin');

async function setUserRole(uid, role) {
  await admin.auth().setCustomUserClaims(uid, { role: role });

  // Force update the profile document in Firestore to stay in sync
  await admin.firestore().collection('profiles').doc(uid).update({ role: role });
}
```

### Accessing Claims inside Client & Middleware
When a client authenticates, the Firebase ID token is sent in the header (`Authorization: Bearer <token>`). The server verifies the token and extracts the custom claims:

```python
# python backend mock middleware using firebase-admin
from firebase_admin import auth
from flask import request, g, abort

def require_role(*allowed_roles):
    def decorator(f):
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                abort(401, "Missing or malformed Authorization header")
            token = auth_header.split(" ", 1)[1]
            try:
                decoded_token = auth.verify_id_token(token)
                g.user_id = decoded_token['uid']
                g.user_role = decoded_token.get('role', 'student')
            except Exception:
                abort(401, "Invalid Firebase token")

            if g.user_role not in allowed_roles:
                abort(403, "Access Denied: Insufficient Permissions")

            return f(*args, **kwargs)
        return decorated
    return decorator
```

---

## 3. 🛡️ Security Rules: Securing NoSQL Databases

Firestore does not have PostgreSQL's Row Level Security (RLS). Instead, data authorization is handled at the API boundaries using **Firestore Security Rules**.

### Firestore Security Rules Blueprint

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Helper: is user logged in?
    function isSignedIn() {
      return request.auth != null;
    }

    // Helper: is user accessing their own document?
    function isOwner(userId) {
      return request.auth.uid == userId;
    }

    // Helper: does the user have the specified role?
    function hasRole(role) {
      return request.auth.token.role == role;
    }

    // ── PROFILES ──────────────────────────────────────────────
    match /profiles/{userId} {
      allow read: if isSignedIn() && (isOwner(userId) || hasRole('admin'));
      allow write: if isSignedIn() && hasRole('admin'); // Only admins alter profile attributes
    }

    // ── ORDERS ────────────────────────────────────────────────
    match /orders/{orderId} {
      allow read: if isSignedIn() && (resource.data.user_id == request.auth.uid || hasRole('admin') || hasRole('kitchen') || hasRole('rider'));
      allow create: if isSignedIn(); // Users create orders
      allow update: if isSignedIn() && (hasRole('admin') || hasRole('kitchen') || hasRole('rider'));
    }

    // ── MENU ITEMS ────────────────────────────────────────────
    match /menu_items/{itemId} {
      allow read: if true; // Public view
      allow write: if isSignedIn() && hasRole('admin');
    }

    // Nested Addon Groups
    match /menu_items/{itemId}/addon_groups/{groupId} {
      allow read: if true;
      allow write: if isSignedIn() && hasRole('admin');
    }

    // ── FEATURE FLAGS ─────────────────────────────────────────
    match /feature_flags/{flagId} {
      allow read: if true;
      allow write: if isSignedIn() && hasRole('admin');
    }
  }
}
```

---

## 4. ⚡ Database Triggers: Cloud Functions

Supabase uses PostgreSQL triggers and procedural SQL (`plpgsql`). In Firebase, database triggers are handled via **Cloud Functions for Firebase** that run on Firestore document writes.

### A. Automatic Tier Recalculation Trigger (On Transaction Write)
Whenever an HP transaction document is created inside `/profiles/{uid}/hp_transactions/{txnId}`, we run a Cloud Function to calculate the user's rolling 120-day HP and update their tier.

```javascript
const functions = require('firebase-functions');
const admin = require('firebase-admin');

exports.recalculateTierOnHpTxn = functions.firestore
  .document('profiles/{uid}/hp_transactions/{txnId}')
  .onCreate(async (snap, context) => {
    const uid = context.params.uid;
    const db = admin.firestore();

    // Calculate 120 days ago boundary
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - 120);

    // Fetch active transactions inside rolling window
    const snapshot = await db.collection('profiles').doc(uid).collection('hp_transactions')
      .where('status', '==', 'active')
      .where('created_at', '>=', cutoffDate)
      .get();

    let totalPoints120d = 0;
    snapshot.forEach(doc => {
      const data = doc.data();
      totalPoints120d += (data.amount || 0);
    });

    // Update profile rolling count
    await db.collection('profiles').doc(uid).update({
      hp_earned_120day: totalPoints120d
    });

    // Assess appropriate tier
    let newTier = 'starter';
    if (totalPoints120d >= 12000) newTier = 'elite';
    else if (totalPoints120d >= 5000) newTier = 'champion';
    else if (totalPoints120d >= 1000) newTier = 'regular';

    await db.collection('profiles').doc(uid).update({ current_tier: newTier });
  });
```

---

## 5. 🛡️ Idempotency Guarantees inside NoSQL Databases

Unlike relational PostgreSQL databases, NoSQL databases do not offer nested relation table locks (`FOR UPDATE` SQL queries) out of the box. We implement idempotency guards using **Firestore Transactions** and **Idempotent Document Key Patterns**.

### A. Idempotency Keys (e.g., Daily Check-In, Webhook Processing)
To prevent a user from checking in multiple times on the same date, set the **document ID** explicitly to the idempotency target:

```javascript
// Setting doc ID to `userId_checkinDate` guarantees uniqueness automatically
async function recordDailyCheckin(userId, dateStr) {
  const docId = `${userId}_${dateStr}`;
  const db = admin.firestore();

  try {
    await db.collection('daily_checkins').doc(docId).create({
      user_id: userId,
      checkin_date: dateStr,
      created_at: admin.firestore.FieldValue.serverTimestamp()
    });
    return { success: true };
  } catch (err) {
    if (err.code === 6) { // ALREADY_EXISTS
      return { error: "Already checked in today" };
    }
    throw err;
  }
}
```

### B. Firestore Transactions (Atomicity)
When multiple documents must be read and updated atomically (e.g., deducting wallet balance and updating an order status), use a **Firestore Transaction**:

```javascript
async function processWalletPayment(userId, amount, orderId) {
  const db = admin.firestore();
  const profileRef = db.collection('profiles').doc(userId);
  const orderRef = db.collection('orders').doc(orderId);

  return db.runTransaction(async (transaction) => {
    const profileDoc = await transaction.get(profileRef);
    const balance = profileDoc.data().wallet_balance || 0;

    if (balance < amount) {
      throw new Error("Insufficient wallet balance");
    }

    // Deduct balance and update status atomically
    transaction.update(profileRef, { wallet_balance: balance - amount });
    transaction.update(orderRef, { payment_status: 'completed', status: 'preparing' });
  });
}
```

---

## 🏁 Step-by-Step Transition Checklist

1. **Setup Firebase Project:** Create a project inside the Firebase Console.
2. **Export Supabase Users:** Export user lists from Supabase Auth and import them into Firebase Authentication using `firebase auth:import`.
3. **Migrate PostgreSQL Tables:** Write a one-time migration script (using Python or Node.js) to query Supabase REST endpoints, convert row entities into JSON documents, and insert them into Firestore collections.
4. **Deploy Custom Claims:** Set up your Admin API or signup trigger to set roles ('admin', 'rider', 'kitchen', 'student') inside Firebase Auth custom claims.
5. **Deploy Firebase Security Rules:** Upload the completed security rules to firewalls.
6. **Deploy Cloud Functions:** Replace database trigger functions (like rolling HP totals or streak increments) with Firestore onCreate/onUpdate Cloud Functions.
7. **Refactor Backend Adapter:** Replace the PostgREST client implementation inside `app/db.py` with the standard Firebase Admin python SDK (`firebase-admin`).
