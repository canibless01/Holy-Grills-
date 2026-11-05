# Holy Grills — Supabase Auth email templates

Paste these into Supabase → Authentication → Email Templates. Set the subject separately, then paste only the HTML inside its code block into the body field. SMTP is already configured by the owner; these templates do not change SMTP or enable signup confirmation.

Keep `{{ .ConfirmationURL }}` exactly as written: Supabase generates the private action URL. Disable provider click tracking for Auth emails. Do not replace it with the homepage. Supabase Site URL stays `https://holygrills.online`; keep the configured app password-reset redirect in the allowlist.

These templates were prepared for copying; no Auth management credential is connected here, so they have not been applied to the hosted Auth configuration.

## Reset Password

Subject: **Reset your Holy Grills password**

```html
<!doctype html>
<html lang="en">
<body style="margin:0;background:#fff5f0;font-family:Arial,sans-serif;color:#381800;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:20px;">
<tr><td style="padding:32px;">
<img src="https://holygrills.online/brand/wordmark.png" alt="Holy Grills" width="140" style="display:block;max-width:100%;height:auto;">
<h1 style="font-size:25px;line-height:1.3;margin-top:28px;">Reset your password</h1>
<p style="font-size:16px;line-height:1.7;">You asked to reset your Holy Grills password. Tap below to choose a new one. If you did not request this, you can ignore this email.</p>
<p style="margin:28px 0;"><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:15px 24px;background:#e01616;color:#fff;text-decoration:none;border-radius:12px;font-weight:bold;">Choose a new password</a></p>
<p style="font-size:13px;line-height:1.7;color:#715a4a;">For your security, do not share this link. If it expires, request a new one on the website.</p>
<p style="font-size:14px;line-height:1.7;margin-top:28px;">Made with more than flame ❤️‍🔥,<br>Holy Grills Team.</p>
<p style="font-size:12px;color:#715a4a;">Bring your people. We bring the fire.<br>Faith. Love. Energy. Flavor.</p>
</td></tr></table>
</td></tr></table>
</body>
</html>
```

## Confirm Signup

Subject: **Confirm your Holy Grills email**

```html
<!doctype html>
<html lang="en">
<body style="margin:0;background:#fff5f0;font-family:Arial,sans-serif;color:#381800;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:20px;">
<tr><td style="padding:32px;">
<img src="https://holygrills.online/brand/wordmark.png" alt="Holy Grills" width="140" style="display:block;max-width:100%;height:auto;">
<h1 style="font-size:25px;line-height:1.3;margin-top:28px;">Your people. Your fire.</h1>
<p style="font-size:16px;line-height:1.7;">Confirm your email address to finish joining Holy Grills. This template is used only if email confirmation is enabled later.</p>
<p style="margin:28px 0;"><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:15px 24px;background:#e01616;color:#fff;text-decoration:none;border-radius:12px;font-weight:bold;">Confirm my email</a></p>
<p style="font-size:13px;line-height:1.7;color:#715a4a;">For your security, do not share this link. If it expires, request a new one on the website.</p>
<p style="font-size:14px;line-height:1.7;margin-top:28px;">Made with more than flame ❤️‍🔥,<br>Holy Grills Team.</p>
<p style="font-size:12px;color:#715a4a;">Bring your people. We bring the fire.<br>Faith. Love. Energy. Flavor.</p>
</td></tr></table>
</td></tr></table>
</body>
</html>
```

## Magic Link

Subject: **Your Holy Grills sign-in link**

```html
<!doctype html>
<html lang="en">
<body style="margin:0;background:#fff5f0;font-family:Arial,sans-serif;color:#381800;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:20px;">
<tr><td style="padding:32px;">
<img src="https://holygrills.online/brand/wordmark.png" alt="Holy Grills" width="140" style="display:block;max-width:100%;height:auto;">
<h1 style="font-size:25px;line-height:1.3;margin-top:28px;">Welcome back to the fire</h1>
<p style="font-size:16px;line-height:1.7;">Use this private link to sign in to Holy Grills. If you did not request it, you can ignore this email.</p>
<p style="margin:28px 0;"><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:15px 24px;background:#e01616;color:#fff;text-decoration:none;border-radius:12px;font-weight:bold;">Sign in</a></p>
<p style="font-size:13px;line-height:1.7;color:#715a4a;">For your security, do not share this link. If it expires, request a new one on the website.</p>
<p style="font-size:14px;line-height:1.7;margin-top:28px;">Made with more than flame ❤️‍🔥,<br>Holy Grills Team.</p>
<p style="font-size:12px;color:#715a4a;">Bring your people. We bring the fire.<br>Faith. Love. Energy. Flavor.</p>
</td></tr></table>
</td></tr></table>
</body>
</html>
```

## Invite User

Subject: **You’re invited to Holy Grills**

```html
<!doctype html>
<html lang="en">
<body style="margin:0;background:#fff5f0;font-family:Arial,sans-serif;color:#381800;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:20px;">
<tr><td style="padding:32px;">
<img src="https://holygrills.online/brand/wordmark.png" alt="Holy Grills" width="140" style="display:block;max-width:100%;height:auto;">
<h1 style="font-size:25px;line-height:1.3;margin-top:28px;">Join the fire</h1>
<p style="font-size:16px;line-height:1.7;">You have been invited to Holy Grills. Accept the invitation to finish setting up your account.</p>
<p style="margin:28px 0;"><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:15px 24px;background:#e01616;color:#fff;text-decoration:none;border-radius:12px;font-weight:bold;">Accept invitation</a></p>
<p style="font-size:13px;line-height:1.7;color:#715a4a;">For your security, do not share this link. If it expires, request a new one on the website.</p>
<p style="font-size:14px;line-height:1.7;margin-top:28px;">Made with more than flame ❤️‍🔥,<br>Holy Grills Team.</p>
<p style="font-size:12px;color:#715a4a;">Bring your people. We bring the fire.<br>Faith. Love. Energy. Flavor.</p>
</td></tr></table>
</td></tr></table>
</body>
</html>
```

## Change Email Address

Subject: **Confirm your new Holy Grills email**

```html
<!doctype html>
<html lang="en">
<body style="margin:0;background:#fff5f0;font-family:Arial,sans-serif;color:#381800;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:20px;">
<tr><td style="padding:32px;">
<img src="https://holygrills.online/brand/wordmark.png" alt="Holy Grills" width="140" style="display:block;max-width:100%;height:auto;">
<h1 style="font-size:25px;line-height:1.3;margin-top:28px;">Confirm your new email</h1>
<p style="font-size:16px;line-height:1.7;">You requested an email address change for your Holy Grills account. Confirm the change below. If you did not request this, contact support@holygrills.online.</p>
<p style="margin:28px 0;"><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:15px 24px;background:#e01616;color:#fff;text-decoration:none;border-radius:12px;font-weight:bold;">Confirm email change</a></p>
<p style="font-size:13px;line-height:1.7;color:#715a4a;">For your security, do not share this link. If it expires, request a new one on the website.</p>
<p style="font-size:14px;line-height:1.7;margin-top:28px;">Made with more than flame ❤️‍🔥,<br>Holy Grills Team.</p>
<p style="font-size:12px;color:#715a4a;">Bring your people. We bring the fire.<br>Faith. Love. Energy. Flavor.</p>
</td></tr></table>
</td></tr></table>
</body>
</html>
```

