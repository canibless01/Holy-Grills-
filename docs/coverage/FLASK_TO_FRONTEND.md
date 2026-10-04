# Flask → Frontend coverage

Every registered Flask route, and the frontend call site that reaches it.
`unused (dead from the FE)` = no call site in this frontend; the route may still serve
webhooks, the admin tooling, mobile clients or tests — check before deleting.

| # | Flask route (file:line) | Method | Auth | FE caller (file:line) | Status |
|---|---|---|---|---|---|
| 1 | `holy-grills-backend/app/routes/academic_calendar.py:59` | GET | public | — | unused (dead from the FE) |
| 2 | `holy-grills-backend/app/routes/academic_calendar.py:83` | GET | public | — | unused (dead from the FE) |
| 3 | `holy-grills-backend/app/routes/academic_levels.py:44` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1247` | correct |
| 4 | `holy-grills-backend/app/routes/academic_levels.py:90` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1249` | correct |
| 5 | `holy-grills-backend/app/routes/admin.py:1703` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:715` | correct |
| 6 | `holy-grills-backend/app/routes/admin.py:1724` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:716` | correct |
| 7 | `holy-grills-backend/app/routes/academic_calendar.py:114` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:634` | correct |
| 8 | `holy-grills-backend/app/routes/academic_calendar.py:142` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:635` | correct |
| 9 | `holy-grills-backend/app/routes/academic_calendar.py:200` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:636` | correct |
| 10 | `holy-grills-backend/app/routes/academic_levels.py:128` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1105` | correct |
| 11 | `holy-grills-backend/app/routes/academic_levels.py:152` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1106` | correct |
| 12 | `holy-grills-backend/app/routes/academic_levels.py:224` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1107` | correct |
| 13 | `holy-grills-backend/app/routes/academic_levels.py:315` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1110` | correct |
| 14 | `holy-grills-backend/app/routes/academic_levels.py:337` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1111` | correct |
| 15 | `holy-grills-backend/app/routes/admin.py:1786` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:736` | correct |
| 16 | `holy-grills-backend/app/routes/admin.py:2335` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:623` | correct |
| 17 | `holy-grills-backend/app/routes/admin.py:2806` | PATCH | require_role | — | unused (dead from the FE) |
| 18 | `holy-grills-backend/app/routes/admin.py:2776` | GET | require_role | — | unused (dead from the FE) |
| 19 | `holy-grills-backend/app/routes/admin.py:1861` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:737` | correct |
| 20 | `holy-grills-backend/app/routes/admin.py:1969` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:753` | correct |
| 21 | `holy-grills-backend/app/routes/admin.py:1075` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:687` | correct |
| 22 | `holy-grills-backend/app/routes/admin.py:1160` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:688` | correct |
| 23 | `holy-grills-backend/app/routes/admin.py:1261` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:689` | correct |
| 24 | `holy-grills-backend/app/routes/admin.py:1352` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:690` | correct |
| 25 | `holy-grills-backend/app/routes/admin.py:1119` | GET | require_role | — | unused (dead from the FE) |
| 26 | `holy-grills-backend/app/routes/admin.py:1400` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:691` | correct |
| 27 | `holy-grills-backend/app/routes/admin.py:616` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:674` | correct |
| 28 | `holy-grills-backend/app/routes/admin.py:580` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:673` | correct |
| 29 | `holy-grills-backend/app/routes/admin.py:724` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:675` | correct |
| 30 | `holy-grills-backend/app/routes/admin.py:826` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:676` | correct |
| 31 | `holy-grills-backend/app/routes/admin.py:848` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:677` | correct |
| 32 | `holy-grills-backend/app/routes/departments.py:204` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1102` | correct |
| 33 | `holy-grills-backend/app/routes/departments.py:176` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1101` | correct |
| 34 | `holy-grills-backend/app/routes/departments.py:262` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1103` | correct |
| 35 | `holy-grills-backend/app/routes/departments.py:352` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1104` | correct |
| 36 | `holy-grills-backend/app/routes/departments.py:374` | POST | require_role | — | unused (dead from the FE) |
| 37 | `holy-grills-backend/app/routes/admin_economics.py:49` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1194` | correct |
| 38 | `holy-grills-backend/app/routes/admin_economics.py:77` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1196` | correct |
| 39 | `holy-grills-backend/app/routes/admin_economics.py:65` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1195` | correct |
| 40 | `holy-grills-backend/app/routes/admin.py:2470` | POST | require_role | — | unused (dead from the FE) |
| 41 | `holy-grills-backend/app/routes/admin.py:2439` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1220` | correct |
| 42 | `holy-grills-backend/app/routes/admin.py:2425` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1218` | correct |
| 43 | `holy-grills-backend/app/routes/admin.py:2606` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1221` | correct |
| 44 | `holy-grills-backend/app/routes/admin.py:2572` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1219` | correct |
| 45 | `holy-grills-backend/app/routes/admin_feature_flags.py:432` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1226` | correct |
| 46 | `holy-grills-backend/app/routes/admin_feature_flags.py:451` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1227` | correct |
| 47 | `holy-grills-backend/app/routes/admin_feature_flags.py:167` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1046` | correct |
| 48 | `holy-grills-backend/app/routes/admin_feature_flags.py:152` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1049` | correct |
| 49 | `holy-grills-backend/app/routes/admin_feature_flags.py:208` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1048` | correct |
| 50 | `holy-grills-backend/app/routes/admin_feature_flags.py:183` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1047` | correct |
| 51 | `holy-grills-backend/app/routes/admin_gifts.py:21` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1147` | correct |
| 52 | `holy-grills-backend/app/routes/admin_gifts.py:52` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1148` | correct |
| 53 | `holy-grills-backend/app/routes/admin_feature_flags.py:382` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1058` | correct |
| 54 | `holy-grills-backend/app/routes/admin_feature_flags.py:401` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1059` | correct |
| 55 | `holy-grills-backend/app/routes/admin.py:2082` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:661` | correct |
| 56 | `holy-grills-backend/app/routes/admin.py:2272` | GET | require_role | — | unused (dead from the FE) |
| 57 | `holy-grills-backend/app/routes/admin.py:2237` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:662` | correct |
| 58 | `holy-grills-backend/app/routes/admin_feature_flags.py:328` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1054` | correct |
| 59 | `holy-grills-backend/app/routes/admin_feature_flags.py:350` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1055` | correct |
| 60 | `holy-grills-backend/app/routes/admin.py:856` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:682` | correct |
| 61 | `holy-grills-backend/app/routes/admin.py:896` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:683` | correct |
| 62 | `holy-grills-backend/app/routes/admin.py:993` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:684` | correct |
| 63 | `holy-grills-backend/app/routes/admin.py:168` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:667`<br>`holy-grills-frontend/src/lib/liveApi.ts:1081` | correct |
| 64 | `holy-grills-backend/app/routes/admin.py:1521` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:721`<br>`holy-grills-frontend/src/lib/liveApi.ts:725`<br>`holy-grills-frontend/src/lib/liveApi.ts:1083` | correct |
| 65 | `holy-grills-backend/app/routes/admin.py:1540` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:722` | correct |
| 66 | `holy-grills-backend/app/routes/admin.py:1576` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:723`<br>`holy-grills-frontend/src/lib/liveApi.ts:728` | correct |
| 67 | `holy-grills-backend/app/routes/admin.py:1620` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:733` | correct |
| 68 | `holy-grills-backend/app/routes/admin.py:2355` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1062` | correct |
| 69 | `holy-grills-backend/app/routes/admin_gifts.py:232` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:782` | correct |
| 70 | `holy-grills-backend/app/routes/admin_gifts.py:125` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:781`<br>`holy-grills-frontend/src/lib/liveApi.ts:786` | correct |
| 71 | `holy-grills-backend/app/routes/admin_gifts.py:141` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:783`<br>`holy-grills-frontend/src/lib/liveApi.ts:787`<br>`holy-grills-frontend/src/lib/liveApi.ts:1211` | correct |
| 72 | `holy-grills-backend/app/routes/kitchen.py:71` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1231` | correct |
| 73 | `holy-grills-backend/app/routes/kitchen.py:136` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1230` | correct |
| 74 | `holy-grills-backend/app/routes/kitchen.py:279` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1234` | correct |
| 75 | `holy-grills-backend/app/routes/kitchen.py:162` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1232` | correct |
| 76 | `holy-grills-backend/app/routes/kitchen.py:219` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1233` | correct |
| 77 | `holy-grills-backend/app/routes/admin.py:104` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:639`<br>`holy-grills-frontend/src/lib/liveApi.ts:1080` | correct |
| 78 | `holy-grills-backend/app/routes/admin.py:135` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:640` | correct |
| 79 | `holy-grills-backend/app/routes/admin.py:473` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:643` | correct |
| 80 | `holy-grills-backend/app/routes/admin.py:396` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:642` | correct |
| 81 | `holy-grills-backend/app/routes/admin.py:333` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:645` | correct |
| 82 | `holy-grills-backend/app/routes/admin.py:216` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:660` | correct |
| 83 | `holy-grills-backend/app/routes/admin.py:262` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:641` | correct |
| 84 | `holy-grills-backend/app/routes/admin.py:366` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:659` | correct |
| 85 | `holy-grills-backend/app/routes/admin.py:2635` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:630` | correct |
| 86 | `holy-grills-backend/app/routes/analytics.py:1497` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:596` | correct |
| 87 | `holy-grills-backend/app/routes/analytics.py:882` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:607` | correct |
| 88 | `holy-grills-backend/app/routes/analytics.py:277` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:599` | correct |
| 89 | `holy-grills-backend/app/routes/analytics.py:1099` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:616` | correct |
| 90 | `holy-grills-backend/app/routes/analytics.py:1041` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:615` | correct |
| 91 | `holy-grills-backend/app/routes/analytics.py:1062` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:617` | correct |
| 92 | `holy-grills-backend/app/routes/analytics.py:1163` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:585` | correct |
| 93 | `holy-grills-backend/app/routes/analytics.py:355` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:600` | correct |
| 94 | `holy-grills-backend/app/routes/analytics.py:489` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:602` | correct |
| 95 | `holy-grills-backend/app/routes/analytics.py:587` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:603` | correct |
| 96 | `holy-grills-backend/app/routes/analytics.py:1355` | GET | require_role | — | unused (dead from the FE) |
| 97 | `holy-grills-backend/app/routes/analytics.py:1466` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:592` | correct |
| 98 | `holy-grills-backend/app/routes/analytics.py:731` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1166` | correct |
| 99 | `holy-grills-backend/app/routes/analytics.py:730` | GET | require_role | — | unused (dead from the FE) |
| 100 | `holy-grills-backend/app/routes/analytics.py:813` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:588` | correct |
| 101 | `holy-grills-backend/app/routes/analytics.py:812` | GET | require_role | — | unused (dead from the FE) |
| 102 | `holy-grills-backend/app/routes/analytics.py:1528` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:594` | correct |
| 103 | `holy-grills-backend/app/routes/analytics.py:981` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:609` | correct |
| 104 | `holy-grills-backend/app/routes/analytics.py:221` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:598` | correct |
| 105 | `holy-grills-backend/app/routes/analytics.py:1256` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:587` | correct |
| 106 | `holy-grills-backend/app/routes/analytics.py:163` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:604` | correct |
| 107 | `holy-grills-backend/app/routes/analytics.py:678` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:611` | correct |
| 108 | `holy-grills-backend/app/routes/analytics.py:1132` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1186` | correct |
| 109 | `holy-grills-backend/app/routes/analytics.py:1671` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:590` | correct |
| 110 | `holy-grills-backend/app/routes/analytics.py:622` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:613` | correct |
| 111 | `holy-grills-backend/app/routes/analytics.py:93` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:605` | correct |
| 112 | `holy-grills-backend/app/routes/analytics.py:92` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:586`<br>`holy-grills-frontend/src/lib/liveApi.ts:1164` | correct |
| 113 | `holy-grills-backend/app/routes/analytics.py:430` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:601` | correct |
| 114 | `holy-grills-backend/app/routes/analytics.py:1571` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:589` | correct |
| 115 | `holy-grills-backend/app/routes/auth.py:732` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:49` | correct |
| 116 | `holy-grills-backend/app/routes/auth.py:524` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:70` | correct |
| 117 | `holy-grills-backend/app/routes/auth.py:473` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:69` | correct |
| 118 | `holy-grills-backend/app/routes/auth.py:641` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:72` | correct |
| 119 | `holy-grills-backend/app/routes/auth.py:581` | PATCH | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:71` | correct |
| 120 | `holy-grills-backend/app/routes/auth.py:667` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:46` | correct |
| 121 | `holy-grills-backend/app/routes/auth.py:930` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:59` | correct |
| 122 | `holy-grills-backend/app/routes/auth.py:221` | POST | public | — | unused (dead from the FE) |
| 123 | `holy-grills-backend/app/routes/auth.py:457` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:47` | correct |
| 124 | `holy-grills-backend/app/routes/auth.py:1045` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:48` | correct |
| 125 | `holy-grills-backend/app/routes/auth.py:380` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:38` | correct |
| 126 | `holy-grills-backend/app/routes/auth.py:419` | PATCH | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:41` | correct |
| 127 | `holy-grills-backend/app/routes/auth.py:399` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:45` | correct |
| 128 | `holy-grills-backend/app/routes/auth.py:282` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:40` | correct |
| 129 | `holy-grills-backend/app/routes/auth.py:135` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:39` | correct |
| 130 | `holy-grills-backend/app/routes/auth.py:851` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:51` | correct |
| 131 | `holy-grills-backend/app/routes/auth.py:879` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:57` | correct |
| 132 | `holy-grills-backend/app/routes/auth.py:1023` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:60` | correct |
| 133 | `holy-grills-backend/app/routes/auth.py:1071` | GET | require_auth | — | unused (dead from the FE) |
| 134 | `holy-grills-backend/app/routes/auth.py:807` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:58` | correct |
| 135 | `holy-grills-backend/app/routes/campuses.py:14` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1257` | correct |
| 136 | `holy-grills-backend/app/routes/cart.py:65` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:88` | correct |
| 137 | `holy-grills-backend/app/routes/cart.py:18` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:87` | correct |
| 138 | `holy-grills-backend/app/routes/cart.py:344` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:91` | correct |
| 139 | `holy-grills-backend/app/routes/cart.py:310` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:90` | correct |
| 140 | `holy-grills-backend/app/routes/cart.py:240` | PATCH | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:89` | correct |
| 141 | `holy-grills-backend/app/routes/challenges.py:49` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1306` | correct |
| 142 | `holy-grills-backend/app/routes/challenges.py:135` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1312` | correct |
| 143 | `holy-grills-backend/app/routes/challenges.py:437` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1158` | correct |
| 144 | `holy-grills-backend/app/routes/challenges.py:398` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1157` | correct |
| 145 | `holy-grills-backend/app/routes/challenges.py:522` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1160` | correct |
| 146 | `holy-grills-backend/app/routes/challenges.py:488` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1159` | correct |
| 147 | `holy-grills-backend/app/routes/challenges.py:547` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1161` | correct |
| 148 | `holy-grills-backend/app/routes/challenges.py:87` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1307` | correct |
| 149 | `holy-grills-backend/app/routes/challenges.py:116` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1308` | correct |
| 150 | `holy-grills-backend/app/routes/challenges.py:259` | POST | require_auth | — | unused (dead from the FE) |
| 151 | `holy-grills-backend/app/routes/challenges.py:214` | POST | require_auth | — | unused (dead from the FE) |
| 152 | `holy-grills-backend/app/routes/challenges.py:375` | GET | require_auth | — | unused (dead from the FE) |
| 153 | `holy-grills-backend/app/routes/challenges.py:168` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1314` | correct |
| 154 | `holy-grills-backend/app/routes/delivery.py:512` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1204` | correct |
| 155 | `holy-grills-backend/app/routes/delivery.py:489` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1203` | correct |
| 156 | `holy-grills-backend/app/routes/delivery.py:575` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1205`<br>`holy-grills-frontend/src/lib/liveApi.ts:1207` | correct |
| 157 | `holy-grills-backend/app/routes/delivery.py:614` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1206` | correct |
| 158 | `holy-grills-backend/app/routes/delivery.py:329` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1199` | correct |
| 159 | `holy-grills-backend/app/routes/delivery.py:352` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1200` | correct |
| 160 | `holy-grills-backend/app/routes/delivery.py:406` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1201` | correct |
| 161 | `holy-grills-backend/app/routes/delivery.py:440` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1202` | correct |
| 162 | `holy-grills-backend/app/routes/delivery.py:193` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:1264` | correct |
| 163 | `holy-grills-backend/app/routes/delivery.py:166` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1263` | correct |
| 164 | `holy-grills-backend/app/routes/delivery.py:139` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1262` | correct |
| 165 | `holy-grills-backend/app/routes/departments.py:51` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1244` | correct |
| 166 | `holy-grills-backend/app/routes/departments.py:138` | GET | public | — | unused (dead from the FE) |
| 167 | `holy-grills-backend/app/routes/departments.py:105` | GET | public | — | unused (dead from the FE) |
| 168 | `holy-grills-backend/app/routes/events.py:1093` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:931` | correct |
| 169 | `holy-grills-backend/app/routes/events.py:64` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:202` | correct |
| 170 | `holy-grills-backend/app/routes/events.py:412` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:939` | correct |
| 171 | `holy-grills-backend/app/routes/events.py:93` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:203`<br>`holy-grills-frontend/src/lib/liveApi.ts:212`<br>`holy-grills-frontend/src/lib/liveApi.ts:930` | correct |
| 172 | `holy-grills-backend/app/routes/events.py:324` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:932`<br>`holy-grills-frontend/src/lib/liveApi.ts:937` | correct |
| 173 | `holy-grills-backend/app/routes/events.py:132` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:205` | correct |
| 174 | `holy-grills-backend/app/routes/events.py:1557` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1074` | correct |
| 175 | `holy-grills-backend/app/routes/events.py:450` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:206`<br>`holy-grills-frontend/src/lib/liveApi.ts:948` | correct |
| 176 | `holy-grills-backend/app/routes/events.py:490` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:204` | correct |
| 177 | `holy-grills-backend/app/routes/events.py:1380` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:980`<br>`holy-grills-frontend/src/lib/liveApi.ts:981`<br>`holy-grills-frontend/src/lib/liveApi.ts:1069` | correct |
| 178 | `holy-grills-backend/app/routes/events.py:1581` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:982`<br>`holy-grills-frontend/src/lib/liveApi.ts:1070` | correct |
| 179 | `holy-grills-backend/app/routes/events.py:751` | GET | public | — | unused (dead from the FE) |
| 180 | `holy-grills-backend/app/routes/events.py:1171` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:208`<br>`holy-grills-frontend/src/lib/liveApi.ts:950` | correct |
| 181 | `holy-grills-backend/app/routes/events.py:1194` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:951` | correct |
| 182 | `holy-grills-backend/app/routes/events.py:1695` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:214`<br>`holy-grills-frontend/src/lib/liveApi.ts:961` | correct |
| 183 | `holy-grills-backend/app/routes/events.py:290` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:930`<br>`holy-grills-frontend/src/lib/liveApi.ts:934` | correct |
| 184 | `holy-grills-backend/app/routes/events.py:904` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1066` | correct |
| 185 | `holy-grills-backend/app/routes/events.py:1024` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:207` | correct |
| 186 | `holy-grills-backend/app/routes/events.py:939` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1067` | correct |
| 187 | `holy-grills-backend/app/routes/events.py:1786` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:212` | correct |
| 188 | `holy-grills-backend/app/routes/events.py:1283` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:955` | correct |
| 189 | `holy-grills-backend/app/routes/events.py:1345` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:956` | correct |
| 190 | `holy-grills-backend/app/routes/events.py:1759` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:216` | correct |
| 191 | `holy-grills-backend/app/routes/exclusive_spin.py:154` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:267` | correct |
| 192 | `holy-grills-backend/app/routes/exclusive_spin.py:177` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:276` | correct |
| 193 | `holy-grills-backend/app/routes/free_sides.py:39` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:298` | correct |
| 194 | `holy-grills-backend/app/routes/free_sides.py:130` | POST | require_role | — | unused (dead from the FE) |
| 195 | `holy-grills-backend/app/routes/free_sides.py:72` | GET | require_role | — | unused (dead from the FE) |
| 196 | `holy-grills-backend/app/routes/free_sides.py:96` | POST | require_role | — | unused (dead from the FE) |
| 197 | `holy-grills-backend/app/routes/free_sides.py:232` | PATCH | require_role | — | unused (dead from the FE) |
| 198 | `holy-grills-backend/app/routes/free_sides.py:266` | DELETE | require_role | — | unused (dead from the FE) |
| 199 | `holy-grills-backend/app/routes/free_sides.py:299` | POST | require_auth | — | unused (dead from the FE) |
| 200 | `holy-grills-backend/app/routes/free_sides.py:347` | DELETE | require_auth | — | unused (dead from the FE) |
| 201 | `holy-grills-backend/app/routes/graduation.py:20` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1319` | correct |
| 202 | `holy-grills-backend/app/routes/health.py:34` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1352` | correct |
| 203 | `holy-grills-backend/app/routes/hp.py:144` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:664` | correct |
| 204 | `holy-grills-backend/app/routes/hp.py:90` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:663` | correct |
| 205 | `holy-grills-backend/app/routes/hp.py:13` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:251` | correct |
| 206 | `holy-grills-backend/app/routes/hp.py:253` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:258` | correct |
| 207 | `holy-grills-backend/app/routes/hp.py:287` | POST | require_auth | — | unused (dead from the FE) |
| 208 | `holy-grills-backend/app/routes/hp.py:366` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:259` | correct |
| 209 | `holy-grills-backend/app/routes/hp.py:189` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:255` | correct |
| 210 | `holy-grills-backend/app/routes/hp.py:69` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:253` | correct |
| 211 | `holy-grills-backend/app/routes/hp.py:32` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:252` | correct |
| 212 | `holy-grills-backend/app/routes/hp.py:480` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:254` | correct |
| 213 | `holy-grills-backend/app/routes/hp.py:223` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:256` | correct |
| 214 | `holy-grills-backend/app/routes/kitchen.py:629` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:462` | correct |
| 215 | `holy-grills-backend/app/routes/kitchen.py:670` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:479` | correct |
| 216 | `holy-grills-backend/app/routes/kitchen.py:554` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:467` | correct |
| 217 | `holy-grills-backend/app/routes/kitchen.py:430` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:422` | correct |
| 218 | `holy-grills-backend/app/routes/kitchen.py:502` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:455` | correct |
| 219 | `holy-grills-backend/app/routes/kitchen.py:322` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:474` | correct |
| 220 | `holy-grills-backend/app/routes/kitchen.py:380` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:478` | correct |
| 221 | `holy-grills-backend/app/routes/kitchen.py:348` | GET | require_role | — | unused (dead from the FE) |
| 222 | `holy-grills-backend/app/routes/kitchen.py:466` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:468` | correct |
| 223 | `holy-grills-backend/app/routes/leaderboard.py:35` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:385` | correct |
| 224 | `holy-grills-backend/app/routes/leaderboard.py:141` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:388` | correct |
| 225 | `holy-grills-backend/app/routes/leaderboard.py:190` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:390` | correct |
| 226 | `holy-grills-backend/app/routes/leaderboard.py:239` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:392` | correct |
| 227 | `holy-grills-backend/app/routes/leaderboard.py:287` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:386` | correct |
| 228 | `holy-grills-backend/app/routes/leaderboard.py:374` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:387` | correct |
| 229 | `holy-grills-backend/app/routes/leaderboard.py:420` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:394` | correct |
| 230 | `holy-grills-backend/app/routes/marketplace.py:140` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:314` | correct |
| 231 | `holy-grills-backend/app/routes/marketplace.py:182` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:315`<br>`holy-grills-frontend/src/lib/liveApi.ts:317` | correct |
| 232 | `holy-grills-backend/app/routes/marketplace.py:223` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:316` | correct |
| 233 | `holy-grills-backend/app/routes/marketplace.py:1262` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1024` | correct |
| 234 | `holy-grills-backend/app/routes/marketplace.py:815` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1009` | correct |
| 235 | `holy-grills-backend/app/routes/marketplace.py:778` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1005` | correct |
| 236 | `holy-grills-backend/app/routes/marketplace.py:1046` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1011` | correct |
| 237 | `holy-grills-backend/app/routes/marketplace.py:742` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1008` | correct |
| 238 | `holy-grills-backend/app/routes/marketplace.py:959` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1010` | correct |
| 239 | `holy-grills-backend/app/routes/marketplace.py:925` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1019` | correct |
| 240 | `holy-grills-backend/app/routes/marketplace.py:904` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1015` | correct |
| 241 | `holy-grills-backend/app/routes/marketplace.py:393` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1025` | correct |
| 242 | `holy-grills-backend/app/routes/marketplace.py:437` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1029`<br>`holy-grills-frontend/src/lib/liveApi.ts:1030` | correct |
| 243 | `holy-grills-backend/app/routes/marketplace.py:587` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1033` | correct |
| 244 | `holy-grills-backend/app/routes/marketplace.py:614` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1034` | correct |
| 245 | `holy-grills-backend/app/routes/marketplace.py:1161` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1020` | correct |
| 246 | `holy-grills-backend/app/routes/marketplace.py:1198` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1022`<br>`holy-grills-frontend/src/lib/liveApi.ts:1023` | correct |
| 247 | `holy-grills-backend/app/routes/marketplace.py:903` | POST | require_role | — | unused (dead from the FE) |
| 248 | `holy-grills-backend/app/routes/marketplace.py:356` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:317` | correct |
| 249 | `holy-grills-backend/app/routes/marketplace.py:527` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:322` | correct |
| 250 | `holy-grills-backend/app/routes/marketplace.py:1078` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:319` | correct |
| 251 | `holy-grills-backend/app/routes/kitchen.py:55` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1237` | correct |
| 252 | `holy-grills-backend/app/routes/menu.py:1377` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:81`<br>`holy-grills-frontend/src/lib/liveApi.ts:821` | correct |
| 253 | `holy-grills-backend/app/routes/menu.py:1409` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:824`<br>`holy-grills-frontend/src/lib/liveApi.ts:915` | correct |
| 254 | `holy-grills-backend/app/routes/menu.py:1467` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:825` | correct |
| 255 | `holy-grills-backend/app/routes/menu.py:1510` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:826`<br>`holy-grills-frontend/src/lib/liveApi.ts:908` | correct |
| 256 | `holy-grills-backend/app/routes/menu.py:406` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:80` | correct |
| 257 | `holy-grills-backend/app/routes/menu.py:249` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:791` | correct |
| 258 | `holy-grills-backend/app/routes/menu.py:318` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:792` | correct |
| 259 | `holy-grills-backend/app/routes/menu.py:378` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:793` | correct |
| 260 | `holy-grills-backend/app/routes/menu.py:433` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:77`<br>`holy-grills-frontend/src/lib/liveApi.ts:796`<br>`holy-grills-frontend/src/lib/liveApi.ts:800` | correct |
| 261 | `holy-grills-backend/app/routes/menu.py:801` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:797` | correct |
| 262 | `holy-grills-backend/app/routes/menu.py:542` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:78`<br>`holy-grills-frontend/src/lib/liveApi.ts:840` | correct |
| 263 | `holy-grills-backend/app/routes/menu.py:887` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:480`<br>`holy-grills-frontend/src/lib/liveApi.ts:481`<br>`holy-grills-frontend/src/lib/liveApi.ts:798` | correct |
| 264 | `holy-grills-backend/app/routes/menu.py:644` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:910` | correct |
| 265 | `holy-grills-backend/app/routes/menu.py:760` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:860` | correct |
| 266 | `holy-grills-backend/app/routes/menu.py:708` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:905` | correct |
| 267 | `holy-grills-backend/app/routes/menu.py:599` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:79`<br>`holy-grills-frontend/src/lib/liveApi.ts:841` | correct |
| 268 | `holy-grills-backend/app/routes/menu.py:1039` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:805` | correct |
| 269 | `holy-grills-backend/app/routes/menu.py:958` | PATCH | require_role | — | unused (dead from the FE) |
| 270 | `holy-grills-backend/app/routes/menu.py:866` | POST | require_role | — | unused (dead from the FE) |
| 271 | `holy-grills-backend/app/routes/menu.py:1072` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:879` | correct |
| 272 | `holy-grills-backend/app/routes/menu.py:1342` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:855` | correct |
| 273 | `holy-grills-backend/app/routes/menu.py:1133` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:874` | correct |
| 274 | `holy-grills-backend/app/routes/menu.py:1184` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:884` | correct |
| 275 | `holy-grills-backend/app/routes/menu.py:1246` | PATCH | require_role | — | unused (dead from the FE) |
| 276 | `holy-grills-backend/app/routes/menu.py:1304` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:876` | correct |
| 277 | `holy-grills-backend/app/routes/menu.py:991` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:807` | correct |
| 278 | `holy-grills-backend/app/routes/menu.py:1531` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:82`<br>`holy-grills-frontend/src/lib/liveApi.ts:816` | correct |
| 279 | `holy-grills-backend/app/routes/menu.py:1551` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:817` | correct |
| 280 | `holy-grills-backend/app/routes/notifications.py:137` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:364` | correct |
| 281 | `holy-grills-backend/app/routes/notifications.py:185` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:365` | correct |
| 282 | `holy-grills-backend/app/routes/notifications.py:333` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1041` | correct |
| 283 | `holy-grills-backend/app/routes/notifications.py:405` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1040` | correct |
| 284 | `holy-grills-backend/app/routes/notifications.py:374` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1043` | correct |
| 285 | `holy-grills-backend/app/routes/notifications.py:261` | PATCH | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:368` | correct |
| 286 | `holy-grills-backend/app/routes/notifications.py:227` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:367` | correct |
| 287 | `holy-grills-backend/app/routes/notifications.py:209` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:366` | correct |
| 288 | `holy-grills-backend/app/routes/order_locks.py:140` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1273` | correct |
| 289 | `holy-grills-backend/app/routes/order_locks.py:27` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1275` | correct |
| 290 | `holy-grills-backend/app/routes/order_locks.py:267` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1276` | correct |
| 291 | `holy-grills-backend/app/routes/order_locks.py:165` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1274` | correct |
| 292 | `holy-grills-backend/app/routes/order_locks.py:197` | PATCH | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1277` | correct |
| 293 | `holy-grills-backend/app/routes/order_locks.py:308` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:718` | correct |
| 294 | `holy-grills-backend/app/routes/orders.py:166` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:120` | correct |
| 295 | `holy-grills-backend/app/routes/orders.py:48` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:117` | correct |
| 296 | `holy-grills-backend/app/routes/orders.py:210` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:121`<br>`holy-grills-frontend/src/lib/liveApi.ts:127`<br>`holy-grills-frontend/src/lib/liveApi.ts:180` | correct |
| 297 | `holy-grills-backend/app/routes/orders.py:292` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:190` | correct |
| 298 | `holy-grills-backend/app/routes/orders.py:1125` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:124` | correct |
| 299 | `holy-grills-backend/app/routes/orders.py:575` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:174` | correct |
| 300 | `holy-grills-backend/app/routes/orders.py:1757` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:172`<br>`holy-grills-frontend/src/lib/liveApi.ts:670` | correct |
| 301 | `holy-grills-backend/app/routes/orders.py:647` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:171`<br>`holy-grills-frontend/src/lib/liveApi.ts:669` | correct |
| 302 | `holy-grills-backend/app/routes/orders.py:1294` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:168` | correct |
| 303 | `holy-grills-backend/app/routes/orders.py:466` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:125` | correct |
| 304 | `holy-grills-backend/app/routes/orders.py:432` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:188` | correct |
| 305 | `holy-grills-backend/app/routes/orders.py:836` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:182` | correct |
| 306 | `holy-grills-backend/app/routes/orders.py:1399` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:169` | correct |
| 307 | `holy-grills-backend/app/routes/orders.py:1705` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:195` | correct |
| 308 | `holy-grills-backend/app/routes/orders.py:1499` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:170` | correct |
| 309 | `holy-grills-backend/app/routes/orders.py:1716` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:196` | correct |
| 310 | `holy-grills-backend/app/routes/orders.py:1730` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:197` | correct |
| 311 | `holy-grills-backend/app/routes/orders.py:329` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:122`<br>`holy-grills-frontend/src/lib/liveApi.ts:668` | correct |
| 312 | `holy-grills-backend/app/routes/orders.py:372` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:123` | correct |
| 313 | `holy-grills-backend/app/routes/orders.py:952` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:180`<br>`holy-grills-frontend/src/lib/liveApi.ts:440` | correct |
| 314 | `holy-grills-backend/app/routes/orders.py:978` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:127` | correct |
| 315 | `holy-grills-backend/app/routes/orders.py:1000` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:129` | correct |
| 316 | `holy-grills-backend/app/routes/orders.py:1043` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:186` | correct |
| 317 | `holy-grills-backend/app/routes/orders.py:791` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:184` | correct |
| 318 | `holy-grills-backend/app/routes/orders.py:1064` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:126` | correct |
| 319 | `holy-grills-backend/app/routes/notifications.py:18` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:379` | correct |
| 320 | `holy-grills-backend/app/routes/notifications.py:93` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:380` | correct |
| 321 | `holy-grills-backend/app/routes/referrals.py:82` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:346` | correct |
| 322 | `holy-grills-backend/app/routes/referrals.py:201` | POST | require_role | — | unused (dead from the FE) |
| 323 | `holy-grills-backend/app/routes/referrals.py:153` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:344` | correct |
| 324 | `holy-grills-backend/app/routes/rewards.py:568` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:986` | correct |
| 325 | `holy-grills-backend/app/routes/rewards.py:128` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:281`<br>`holy-grills-frontend/src/lib/liveApi.ts:985` | correct |
| 326 | `holy-grills-backend/app/routes/rewards.py:181` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:283`<br>`holy-grills-frontend/src/lib/liveApi.ts:285` | correct |
| 327 | `holy-grills-backend/app/routes/rewards.py:707` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:988` | correct |
| 328 | `holy-grills-backend/app/routes/rewards.py:668` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:987` | correct |
| 329 | `holy-grills-backend/app/routes/rewards.py:643` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1002` | correct |
| 330 | `holy-grills-backend/app/routes/rewards.py:211` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:282` | correct |
| 331 | `holy-grills-backend/app/routes/rewards.py:765` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1000` | correct |
| 332 | `holy-grills-backend/app/routes/rewards.py:309` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:989` | correct |
| 333 | `holy-grills-backend/app/routes/rewards.py:392` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:994`<br>`holy-grills-frontend/src/lib/liveApi.ts:995` | correct |
| 334 | `holy-grills-backend/app/routes/rewards.py:743` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:283` | correct |
| 335 | `holy-grills-backend/app/routes/rewards.py:849` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:291` | correct |
| 336 | `holy-grills-backend/app/routes/riders.py:750` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:709` | correct |
| 337 | `holy-grills-backend/app/routes/riders.py:860` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:710` | correct |
| 338 | `holy-grills-backend/app/routes/riders.py:801` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:707` | correct |
| 339 | `holy-grills-backend/app/routes/riders.py:830` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:708` | correct |
| 340 | `holy-grills-backend/app/routes/riders.py:920` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:711` | correct |
| 341 | `holy-grills-backend/app/routes/riders.py:941` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:712` | correct |
| 342 | `holy-grills-backend/app/routes/riders.py:449` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:527` | correct |
| 343 | `holy-grills-backend/app/routes/riders.py:624` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:566` | correct |
| 344 | `holy-grills-backend/app/routes/riders.py:569` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:535` | correct |
| 345 | `holy-grills-backend/app/routes/riders.py:492` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:564` | correct |
| 346 | `holy-grills-backend/app/routes/riders.py:409` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:577` | correct |
| 347 | `holy-grills-backend/app/routes/riders.py:184` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:487` | correct |
| 348 | `holy-grills-backend/app/routes/riders.py:328` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:526` | correct |
| 349 | `holy-grills-backend/app/routes/riders.py:296` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:525`<br>`holy-grills-frontend/src/lib/liveApi.ts:572` | correct |
| 350 | `holy-grills-backend/app/routes/riders.py:369` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:524` | correct |
| 351 | `holy-grills-backend/app/routes/riders.py:664` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:706` | correct |
| 352 | `holy-grills-backend/app/routes/riders.py:534` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:551` | correct |
| 353 | `holy-grills-backend/app/routes/saved_for_later.py:47` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1295` | correct |
| 354 | `holy-grills-backend/app/routes/saved_for_later.py:23` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1294` | correct |
| 355 | `holy-grills-backend/app/routes/saved_for_later.py:151` | PATCH | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1298` | correct |
| 356 | `holy-grills-backend/app/routes/saved_for_later.py:201` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1296` | correct |
| 357 | `holy-grills-backend/app/routes/saved_for_later.py:235` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1299` | correct |
| 358 | `holy-grills-backend/app/routes/saved_for_later.py:304` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1301` | correct |
| 359 | `holy-grills-backend/app/routes/squads.py:20` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1285` | correct |
| 360 | `holy-grills-backend/app/routes/squads.py:76` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1284` | correct |
| 361 | `holy-grills-backend/app/routes/squads.py:92` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1286` | correct |
| 362 | `holy-grills-backend/app/routes/squads.py:141` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1288` | correct |
| 363 | `holy-grills-backend/app/routes/squads.py:188` | DELETE | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1289` | correct |
| 364 | `holy-grills-backend/app/routes/squads.py:130` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:1287` | correct |
| 365 | `holy-grills-backend/app/routes/storefront.py:910` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1114`<br>`holy-grills-frontend/src/lib/liveApi.ts:1330` | correct |
| 366 | `holy-grills-backend/app/routes/storefront.py:934` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1116` | correct |
| 367 | `holy-grills-backend/app/routes/storefront.py:987` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1140` | correct |
| 368 | `holy-grills-backend/app/routes/storefront.py:1015` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1115` | correct |
| 369 | `holy-grills-backend/app/routes/storefront.py:1054` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1139` | correct |
| 370 | `holy-grills-backend/app/routes/storefront.py:176` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1338` | correct |
| 371 | `holy-grills-backend/app/routes/storefront.py:715` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1117`<br>`holy-grills-frontend/src/lib/liveApi.ts:1332` | correct |
| 372 | `holy-grills-backend/app/routes/storefront.py:751` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1118` | correct |
| 373 | `holy-grills-backend/app/routes/storefront.py:814` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1132` | correct |
| 374 | `holy-grills-backend/app/routes/storefront.py:865` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1119` | correct |
| 375 | `holy-grills-backend/app/routes/storefront.py:886` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1133` | correct |
| 376 | `holy-grills-backend/app/routes/storefront.py:1086` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:1334` | correct |
| 377 | `holy-grills-backend/app/routes/storefront.py:1189` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1120` | correct |
| 378 | `holy-grills-backend/app/routes/storefront.py:1311` | GET | require_role | — | unused (dead from the FE) |
| 379 | `holy-grills-backend/app/routes/storefront.py:1263` | POST | require_role | — | unused (dead from the FE) |
| 380 | `holy-grills-backend/app/routes/storefront.py:1326` | GET | require_role | — | unused (dead from the FE) |
| 381 | `holy-grills-backend/app/routes/storefront.py:1337` | POST | require_role | — | unused (dead from the FE) |
| 382 | `holy-grills-backend/app/routes/storefront.py:1354` | POST | require_role | — | unused (dead from the FE) |
| 383 | `holy-grills-backend/app/routes/storefront.py:1152` | POST | public | `holy-grills-frontend/src/lib/liveApi.ts:1121` | correct |
| 384 | `holy-grills-backend/app/routes/storefront.py:466` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1127`<br>`holy-grills-frontend/src/lib/liveApi.ts:1336` | correct |
| 385 | `holy-grills-backend/app/routes/storefront.py:497` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1128` | correct |
| 386 | `holy-grills-backend/app/routes/storefront.py:571` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1129` | correct |
| 387 | `holy-grills-backend/app/routes/storefront.py:634` | POST | require_auth | — | unused (dead from the FE) |
| 388 | `holy-grills-backend/app/routes/storefront.py:332` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1096` | correct |
| 389 | `holy-grills-backend/app/routes/storefront.py:236` | GET | public | `holy-grills-frontend/src/lib/liveApi.ts:1095`<br>`holy-grills-frontend/src/lib/liveApi.ts:1327` | correct |
| 390 | `holy-grills-backend/app/routes/storefront.py:253` | PATCH | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1097` | correct |
| 391 | `holy-grills-backend/app/routes/storefront.py:387` | DELETE | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1098` | correct |
| 392 | `holy-grills-backend/app/routes/storefront.py:415` | POST | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1138` | correct |
| 393 | `holy-grills-backend/app/routes/uploads.py:19` | POST | require_auth | — | unused (dead from the FE) |
| 394 | `holy-grills-backend/app/routes/auth.py:1070` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:244` | correct |
| 395 | `holy-grills-backend/app/routes/wallet.py:16` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:332` | correct |
| 396 | `holy-grills-backend/app/routes/wallet.py:263` | GET | require_role | `holy-grills-frontend/src/lib/liveApi.ts:1143` | correct |
| 397 | `holy-grills-backend/app/routes/wallet.py:129` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:334` | correct |
| 398 | `holy-grills-backend/app/routes/wallet.py:54` | POST | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:333` | correct |
| 399 | `holy-grills-backend/app/routes/wallet.py:297` | GET | require_auth | `holy-grills-frontend/src/lib/liveApi.ts:335` | correct |
| 400 | `holy-grills-backend/app/routes/webhooks.py:122` | POST | public | — | unused (dead from the FE) |
| 401 | `holy-grills-backend/app/routes/webhooks.py:22` | POST | public | — | unused (dead from the FE) |
