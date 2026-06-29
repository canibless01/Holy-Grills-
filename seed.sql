-- menu_categories
INSERT INTO menu_categories (id, name, slug, description, sort_order, is_active) VALUES
('10000001-cafe-cafe-cafe-000000000001', 'Burgers', 'burgers', 'Juicy hand-pressed beef and chicken burgers', 1, true),
('10000001-cafe-cafe-cafe-000000000002', 'Grills', 'grills', 'Charcoal-grilled chicken, beef and fish', 2, true),
('10000001-cafe-cafe-cafe-000000000003', 'Rice Dishes', 'rice', 'Nigerian classics — jollof, fried and ofada rice', 3, true),
('10000001-cafe-cafe-cafe-000000000004', 'Pasta', 'pasta', 'Freshly cooked pasta with rich sauces', 4, true),
('10000001-cafe-cafe-cafe-000000000005', 'Sides', 'sides', 'Fries, plantain, moi moi and more', 5, true),
('10000001-cafe-cafe-cafe-000000000006', 'Drinks', 'drinks', 'Fresh juices, zobo, chapman and chilled water', 6, true),
('10000001-cafe-cafe-cafe-000000000007', 'Desserts', 'desserts', 'Sweet treats to round off your meal', 7, true),
('10000001-cafe-cafe-cafe-000000000008', 'Holy Specials', 'specials', 'Exclusive combos and platters — best value on campus', 8, true)

ON CONFLICT (id) DO NOTHING;

-- menu_items
INSERT INTO menu_items (id, category_id, name, slug, description, price, hp_earn, hp_earn_value, daily_limit, is_available, is_featured, tags, options) VALUES
('20000001-cafe-cafe-cafe-000000000001', '10000001-cafe-cafe-cafe-000000000001', 'Classic Beef Burger', 'classic-beef-burger', 'Single beef patty, lettuce, tomato, pickles and house sauce in a toasted bun', 2500, 1, 25, NULL, true, true, '["beef", "popular"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000002', '10000001-cafe-cafe-cafe-000000000001', 'Double Stack Burger', 'double-stack-burger', 'Two beef patties, double cheese, caramelised onion and secret sauce', 3800, 1, 38, NULL, true, false, '["beef", "indulgent"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000003', '10000001-cafe-cafe-cafe-000000000001', 'Crispy Chicken Burger', 'crispy-chicken-burger', 'Crispy fried chicken fillet, coleslaw and jalapeño mayo in a brioche bun', 2800, 1, 28, NULL, true, true, '["chicken", "spicy"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000004', '10000001-cafe-cafe-cafe-000000000002', 'Half Grilled Chicken', 'half-grilled-chicken', 'Charcoal-grilled half chicken with Holy Grills spice blend, served with a side', 3500, 1, 35, NULL, true, true, '["chicken", "grilled", "popular"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000005', '10000001-cafe-cafe-cafe-000000000002', 'Beef Suya Skewers', 'beef-suya-skewers', 'Tender beef strips on skewers with yaji spice and fresh onion rings', 2200, 1, 22, NULL, true, false, '["beef", "spicy", "street-food"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000006', '10000001-cafe-cafe-cafe-000000000002', 'Grilled Catfish', 'grilled-catfish', 'Whole catfish grilled over open flame with pepper sauce and herbs', 4200, 1, 42, NULL, true, false, '["fish", "grilled"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000007', '10000001-cafe-cafe-cafe-000000000003', 'Party Jollof Rice', 'party-jollof-rice', 'Smoky party jollof rice cooked over firewood with rich tomato base', 1800, 1, 18, NULL, true, true, '["rice", "nigerian", "popular"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000008', '10000001-cafe-cafe-cafe-000000000003', 'Special Fried Rice', 'special-fried-rice', 'Vegetable fried rice with shrimp, chicken liver and sweet corn', 2000, 1, 20, NULL, true, false, '["rice", "nigerian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000009', '10000001-cafe-cafe-cafe-000000000003', 'Ofada Rice & Stew', 'ofada-rice-stew', 'Authentic ofada rice with traditional green pepper stew and assorted meat', 2300, 1, 23, NULL, true, false, '["rice", "nigerian", "traditional"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000010', '10000001-cafe-cafe-cafe-000000000004', 'Spaghetti Bolognese', 'spaghetti-bolognese', 'Al-dente spaghetti in rich beef bolognese sauce topped with parmesan', 2100, 1, 21, NULL, true, false, '["pasta", "beef"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000011', '10000001-cafe-cafe-cafe-000000000004', 'Holy Mac & Cheese', 'holy-mac-cheese', 'Creamy four-cheese macaroni baked to golden perfection', 1900, 1, 19, NULL, true, false, '["pasta", "vegetarian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000012', '10000001-cafe-cafe-cafe-000000000005', 'Seasoned Fries', 'seasoned-fries', 'Crispy golden fries seasoned with Holy Grills spice blend', 900, 1, 9, NULL, true, false, '["sides", "vegetarian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000013', '10000001-cafe-cafe-cafe-000000000005', 'Creamy Coleslaw', 'creamy-coleslaw', 'Fresh cabbage and carrot slaw with house mayo dressing', 700, 1, 7, NULL, true, false, '["sides", "vegetarian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000014', '10000001-cafe-cafe-cafe-000000000005', 'Moi Moi', 'moi-moi', 'Steamed bean pudding with egg, crayfish and smoked fish', 800, 1, 8, NULL, true, false, '["sides", "nigerian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000015', '10000001-cafe-cafe-cafe-000000000005', 'Fried Plantain (Dodo)', 'fried-plantain-dodo', 'Sweet ripe plantain slices fried to caramelised perfection', 700, 1, 7, NULL, true, false, '["sides", "nigerian", "vegetarian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000016', '10000001-cafe-cafe-cafe-000000000006', 'Zobo Drink', 'zobo-drink', 'Chilled hibiscus zobo with ginger and pineapple — no preservatives', 600, 1, 6, NULL, true, false, '["drinks", "cold", "nigerian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000017', '10000001-cafe-cafe-cafe-000000000006', 'Fresh Orange Juice', 'fresh-orange-juice', 'Freshly squeezed orange juice — no added sugar', 1000, 1, 10, NULL, true, false, '["drinks", "cold", "healthy"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000018', '10000001-cafe-cafe-cafe-000000000006', 'Bottled Water (50cl)', 'bottled-water-50cl', 'Chilled 50cl mineral water', 300, 0, 0, NULL, true, false, '["drinks", "cold"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000019', '10000001-cafe-cafe-cafe-000000000006', 'Chapman Cocktail', 'chapman-cocktail', 'Classic Nigerian Chapman — Sprite, Fanta, Grenadine and cucumber', 1200, 1, 12, NULL, true, true, '["drinks", "cold", "popular"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000020', '10000001-cafe-cafe-cafe-000000000007', 'Crunchy Chin Chin', 'crunchy-chin-chin', 'Freshly fried crunchy chin chin in original and coconut flavours', 500, 1, 5, NULL, true, false, '["desserts", "snacks"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000021', '10000001-cafe-cafe-cafe-000000000007', 'Puff Puff (6 pieces)', 'puff-puff-6-pieces', 'Soft, fluffy Nigerian doughnuts lightly dusted with powdered sugar', 700, 1, 7, NULL, true, false, '["desserts", "snacks", "nigerian"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000022', '10000001-cafe-cafe-cafe-000000000008', 'Holy Combo', 'holy-combo', 'Burger + seasoned fries + drink — the student''s best deal on campus', 3500, 1, 45, 50, true, true, '["combo", "value", "popular"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000023', '10000001-cafe-cafe-cafe-000000000008', 'FUTA Platter', 'futa-platter', 'Jollof rice, grilled chicken quarter, plantain, coleslaw and a drink — feeds two', 6500, 1, 80, 30, true, true, '["platter", "sharing", "value"]'::jsonb, '[]'::jsonb),
('20000001-cafe-cafe-cafe-000000000024', '10000001-cafe-cafe-cafe-000000000008', 'Grills Feast Box', 'grills-feast-box', 'Half grilled chicken, suya skewers, moi moi and two drinks — perfect for a group', 9500, 1, 120, 20, true, false, '["platter", "sharing", "group"]'::jsonb, '[]'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- operating_hours
INSERT INTO operating_hours (weekday, opens_at, closes_at, is_closed) VALUES
(0, '08:00', '21:00', false),
(1, '08:00', '21:00', false),
(2, '08:00', '21:00', false),
(3, '08:00', '21:00', false),
(4, '08:00', '22:00', false),
(5, '10:00', '22:00', false),
(6, '12:00', '20:00', false)

ON CONFLICT (weekday) DO NOTHING;

-- storefront_sections
INSERT INTO storefront_sections (key, title, section_type, content, sort_order, is_active) VALUES
('hero_banner', 'Welcome to Holy Grills FUTA', 'hero', '{"headline": "Campus Food. Elevated.", "subheadline": "Order hot, earn Holy Points, eat happy.", "cta_text": "Order Now", "cta_link": "/menu"}'::jsonb, 1, true),
('featured_items', 'Fan Favourites', 'featured', '{"item_ids": ["20000001-cafe-cafe-cafe-000000000022", "20000001-cafe-cafe-cafe-000000000001", "20000001-cafe-cafe-cafe-000000000004", "20000001-cafe-cafe-cafe-000000000007", "20000001-cafe-cafe-cafe-000000000019"], "display_count": 5}'::jsonb, 2, true),
('promo_banner', 'HP Loyalty Programme', 'promo', '{"text": "Earn Holy Points on every order. Redeem for free food.", "badge_text": "1 HP per ₦10 spent", "cta_text": "Learn More", "cta_link": "/hp"}'::jsonb, 3, true),
('campus_delivery', 'Free Campus Delivery', 'info', '{"text": "Delivering to all FUTA hostels, halls and lecture areas.", "subtext": "Orders above ₦3,000 qualify for free delivery"}'::jsonb, 4, true)

ON CONFLICT (key) DO NOTHING;

-- delivery_windows
INSERT INTO delivery_windows (id, label, starts_at, ends_at, capacity, is_active, status) VALUES
('30000001-cafe-cafe-cafe-000000000001', 'Morning — 8 am to 10 am', '1970-01-01T08:00:00+00:00', '1970-01-01T10:00:00+00:00', 30, true, 'active'),
('30000001-cafe-cafe-cafe-000000000002', 'Lunch — 12 pm to 2 pm', '1970-01-01T12:00:00+00:00', '1970-01-01T14:00:00+00:00', 60, true, 'active'),
('30000001-cafe-cafe-cafe-000000000003', 'Afternoon — 4 pm to 6 pm', '1970-01-01T16:00:00+00:00', '1970-01-01T18:00:00+00:00', 50, true, 'active'),
('30000001-cafe-cafe-cafe-000000000004', 'Evening — 7 pm to 9 pm', '1970-01-01T19:00:00+00:00', '1970-01-01T21:00:00+00:00', 40, true, 'active')

ON CONFLICT (id) DO NOTHING;

-- promo_codes
INSERT INTO promo_codes (id, code, description, discount_type, discount_value, min_order_amount, max_uses, max_uses_per_user, scope, applicable_item_ids, applicable_category_ids, starts_at, ends_at, is_active, used_count) VALUES
('40000001-cafe-cafe-cafe-000000000001', 'WELCOME20', '20% off your first order — welcome to Holy Grills!', 'percentage', 20, 1500, 1000, 1, 'cart', '[]'::jsonb, '[]'::jsonb, NULL, NULL, true, 0),
('40000001-cafe-cafe-cafe-000000000002', 'STUDENT10', '10% off for FUTA students — valid always', 'percentage', 10, 1000, NULL, NULL, 'cart', '[]'::jsonb, '[]'::jsonb, NULL, NULL, true, 0),
('40000001-cafe-cafe-cafe-000000000003', 'HOLYGRILLS500', '₦500 flat discount on orders above ₦3,000', 'fixed', 500, 3000, 500, 2, 'cart', '[]'::jsonb, '[]'::jsonb, NULL, NULL, true, 0)

ON CONFLICT (id) DO NOTHING;

-- kitchen_settings
INSERT INTO kitchen_settings (key, value) VALUES
('max_active_orders', '40'),
('avg_prep_time_minutes', '20'),
('auto_accept_orders', 'true'),
('order_cutoff_minutes', '15'),
('max_items_per_order', '20'),
('delivery_fee_naira', '500')

ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- system_settings
INSERT INTO system_settings (key, value) VALUES
('platform_name', 'Holy Grills FUTA'),
('currency_code', 'NGN'),
('currency_symbol', '₦'),
('hp_redeem_rate', '100'),
('min_hp_redeem', '100'),
('welcome_bonus_hp', '50'),
('referral_hp_reward', '75'),
('free_delivery_threshold', '3000'),
('supabase_project_url', '')

ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
