import os
import ast
import re

def check_msg_mismatches():
    # Load messages.py MSG constants
    from build_ref_map import extract_messages_constants, get_py_files
    defined_msgs = set(extract_messages_constants())

    used_msgs = set()
    py_files = get_py_files("app")
    usage_locations = {}

    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()
        # Find MSG.SOMETHING
        matches = re.finditer(r"MSG\.([A-Za-z0-9_]+)", content)
        for m in matches:
            msg_name = m.group(1)
            used_msgs.add(msg_name)
            if msg_name not in usage_locations:
                usage_locations[msg_name] = []
            usage_locations[msg_name].append(pf)

    undefined_used = used_msgs - defined_msgs
    defined_unused = defined_msgs - used_msgs

    return undefined_used, defined_unused, usage_locations

def check_notification_templates_and_calls():
    from build_ref_map import extract_notification_templates, get_py_files
    defined_templates = set(extract_notification_templates())

    # Load template body placeholders
    nt_file = "app/services/notification_templates.py"
    template_placeholders = {}
    if os.path.exists(nt_file):
        with open(nt_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == "NOTIFICATION_TEMPLATES":
                        if isinstance(stmt.value, ast.Dict):
                            for k, v in zip(stmt.value.keys, stmt.value.values):
                                template_key = str(k.value) if isinstance(k, ast.Constant) else None
                                placeholders = set()
                                if isinstance(v, ast.Dict):
                                    for sub_v in v.values:
                                        if isinstance(sub_v, ast.Constant) and isinstance(sub_v.value, str):
                                            # find {var} placeholders
                                            found = re.findall(r"\{([A-Za-z0-9_]+)\}", sub_v.value)
                                            placeholders.update(found)
                                template_placeholders[template_key] = placeholders

    used_types = set()
    notif_calls = [] # (file, type, supplied_keys)
    py_files = get_py_files("app")

    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()

        # Regex or AST search for send_notification or queue_notification or send_template_notification or send_blast calls
        # Matches send_notification(user_id, "type", template_data={...}) or similar
        matches = re.finditer(r"(?:send_notification|queue_notification|send_template_notification|send_notification_async)\s*\(\s*([^)]+)\)", content, re.DOTALL)
        for m in matches:
            call_str = m.group(1)
            # match notification_type or type string literal
            type_match = re.search(r"['\"]([a-z0-9_]+)['\"]", call_str)
            if type_match:
                ntype = type_match.group(1)
                # skip if it looks like an argument name or non-template string
                if ntype in ["user_id", "title", "body", "email", "sms", "push"]:
                    continue
                used_types.add(ntype)

                # Check template_data keys passed
                tpl_data_match = re.search(r"template_data\s*=\s*\{([^}]+)\}", call_str)
                keys_passed = set()
                if tpl_data_match:
                    keys_passed = set(re.findall(r"['\"]([A-Za-z0-9_]+)['\"]\s*:", tpl_data_match.group(1)))
                notif_calls.append((pf, ntype, keys_passed))

    undefined_types_used = used_types - defined_templates
    unused_templates = defined_templates - used_types

    # Placeholder mismatches
    placeholder_mismatches = []
    for pf, ntype, keys_passed in notif_calls:
        if ntype in template_placeholders:
            needed = template_placeholders[ntype]
            missing = needed - keys_passed
            extra = keys_passed - needed
            if missing or extra:
                placeholder_mismatches.append((pf, ntype, missing, extra))

    return undefined_types_used, unused_templates, placeholder_mismatches

def check_config_keys_and_env():
    from build_ref_map import extract_config_keys, extract_env_vars, get_py_files
    defined_configs = set(extract_config_keys())

    # current_app.config.get or current_app.config[...]
    py_files = get_py_files("app")
    used_configs = set()
    used_configs_locs = {}

    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"current_app\.config(?:\.get)?\s*[\(\[]\s*['\"]([A-Za-z0-9_]+)['\"]", content)
        for m in matches:
            used_configs.add(m)
            if m not in used_configs_locs:
                used_configs_locs[m] = []
            used_configs_locs[m].append(pf)

    undefined_configs = used_configs - defined_configs

    # env vars vs .env.example
    env_example_vars = set()
    if os.path.exists(".env.example"):
        with open(".env.example", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    v = line.split("=")[0].strip()
                    env_example_vars.add(v)

    code_env_vars = set(extract_env_vars())
    undocumented_envs = code_env_vars - env_example_vars

    return undefined_configs, used_configs_locs, undocumented_envs

def check_celery_and_cron_mismatches():
    celery_app_file = "app/tasks/celery_app.py"
    scheduled_py = "app/tasks/scheduled.py"

    beat_tasks = set()
    if os.path.exists(celery_app_file):
        with open(celery_app_file, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"['\"]task['\"]\s*:\s*['\"]([^'\"]+)['\"]", content)
        beat_tasks.update(matches)

    defined_tasks = set()
    if os.path.exists(scheduled_py):
        with open(scheduled_py, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"@celery_app\.task[^\n]*\ndef\s+([A-Za-z0-9_]+)", content)
        for m in matches:
            defined_tasks.add(f"app.tasks.scheduled.{m}")

    unregistered_beat_tasks = defined_tasks - beat_tasks
    undefined_beat_tasks = beat_tasks - defined_tasks

    # Check Admin Cron jobs KNOWN_JOBS vs task_map
    admin_py = "app/routes/admin.py"
    known_jobs = []
    task_map_jobs = []
    if os.path.exists(admin_py):
        with open(admin_py, "r", encoding="utf-8") as f:
            content = f.read()
        kj_match = re.search(r"KNOWN_JOBS\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if kj_match:
            known_jobs = [k.strip("'\" \n\r") for k in kj_match.group(1).split(",") if k.strip("'\" \n\r")]

        tm_match = re.search(r"task_map\s*=\s*\{(.*?)\}", content, re.DOTALL)
        if tm_match:
            task_map_jobs = re.findall(r"['\"]([A-Za-z0-9_\-]+)['\"]", tm_match.group(1))

    cron_mismatches = (set(known_jobs) - set(task_map_jobs)).union(set(task_map_jobs) - set(known_jobs))

    return unregistered_beat_tasks, undefined_beat_tasks, known_jobs, task_map_jobs, cron_mismatches

if __name__ == "__main__":
    print("=== AUDIT MISMATCHES ===")

    undef_msgs, unused_msgs, msg_locs = check_msg_mismatches()
    print(f"\n1. MSG CONSTANTS MISMATCHES:")
    print("  Undefined MSG referenced in code:", undef_msgs)
    print("  Defined MSG constants never used:", unused_msgs)

    undef_nts, unused_nts, placeholder_errs = check_notification_templates_and_calls()
    print(f"\n2. NOTIFICATION TEMPLATE MISMATCHES:")
    print("  Notification types referenced but missing in templates:", undef_nts)
    print("  Defined templates never referenced:", unused_nts)
    print(f"  Placeholder mismatches ({len(placeholder_errs)}):", placeholder_errs[:10])

    undef_cfgs, cfg_locs, undoc_envs = check_config_keys_and_env()
    print(f"\n3. CONFIG & ENV VAR MISMATCHES:")
    print("  current_app.config referenced but NOT in app/config.py:", undef_cfgs)
    print("  Env vars used in code but NOT in .env.example:", undoc_envs)

    unreg_celery, undef_celery, known_jobs, task_map_jobs, cron_mismatches = check_celery_and_cron_mismatches()
    print(f"\n4. CELERY & ADMIN CRON MISMATCHES:")
    print("  Defined Celery scheduled tasks NOT in beat schedule:", unreg_celery)
    print("  Beat schedule tasks NOT defined in scheduled.py:", undef_celery)
    print("  Admin Cron KNOWN_JOBS vs task_map mismatches:", cron_mismatches)
