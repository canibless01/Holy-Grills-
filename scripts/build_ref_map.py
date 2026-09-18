import os
import ast
import re

def get_py_files(root_dir="."):
    py_files = []
    for root, dirs, files in os.walk(root_dir):
        if ".git" in root or "__pycache__" in root or ".pytest_cache" in root or "venv" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files

def extract_modules_and_exports():
    modules_info = {}
    py_files = get_py_files(".")
    for pf in sorted(py_files):
        mod_name = pf.replace("./", "").replace("/", ".").replace(".py", "")
        if mod_name.endswith(".__init__"):
            mod_name = mod_name[:-9]
        try:
            with open(pf, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=pf)
            exports = []
            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not stmt.name.startswith("_"):
                        exports.append(stmt.name)
                elif isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and not target.id.startswith("_"):
                            exports.append(target.id)
            modules_info[pf] = sorted(list(set(exports)))
        except Exception as e:
            modules_info[pf] = [f"Error parsing: {e}"]
    return modules_info

def extract_messages_constants():
    msg_file = "app/messages.py"
    if not os.path.exists(msg_file):
        return []
    with open(msg_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=msg_file)
    constants = []
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef) and stmt.name == "MSG":
            for item in stmt.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            constants.append(target.id)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    constants.append(target.id)
    return sorted(list(set(constants)))

def extract_notification_templates():
    nt_file = "app/services/notification_templates.py"
    if not os.path.exists(nt_file):
        return []
    keys = []
    with open(nt_file, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        tree = ast.parse(content)
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == "NOTIFICATION_TEMPLATES":
                        if isinstance(stmt.value, ast.Dict):
                            for k in stmt.value.keys:
                                if isinstance(k, ast.Constant):
                                    keys.append(str(k.value))
    except Exception as e:
        print("Error parsing notification_templates:", e)
    return keys

def extract_config_keys():
    cfg_file = "app/config.py"
    if not os.path.exists(cfg_file):
        return []
    keys = []
    with open(cfg_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=cfg_file)
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            for item in stmt.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            keys.append(target.id)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    keys.append(target.id)
    return sorted(list(set(keys)))

def extract_env_vars():
    env_vars = set()
    py_files = get_py_files(".")
    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"os\.(?:environ\.get|getenv)\s*\(\s*['\"]([A-Za-z0-9_]+)['\"]", content)
        env_vars.update(matches)
        matches_idx = re.findall(r"os\.environ\s*\[\s*['\"]([A-Za-z0-9_]+)['\"]", content)
        env_vars.update(matches_idx)
    return sorted(list(env_vars))

def extract_blueprints():
    blueprints = []
    py_files = get_py_files("app")
    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"(\w+)\s*=\s*Blueprint\s*\(\s*['\"]([^'\"]+)['\"]", content)
        for var_name, bp_name in matches:
            blueprints.append((pf, var_name, bp_name))
    return blueprints

def extract_celery_and_cron():
    celery_file = "app/tasks/celery_app.py"
    celery_tasks = []
    if os.path.exists(celery_file):
        with open(celery_file, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"['\"]task['\"]\s*:\s*['\"]([^'\"]+)['\"]", content)
        celery_tasks.extend(matches)

    cron_jobs = []
    admin_file = "app/routes/admin.py"
    if os.path.exists(admin_file):
        with open(admin_file, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"KNOWN_JOBS\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if matches:
            cron_jobs = [k.strip("'\" \n\r") for k in matches[0].split(",") if k.strip("'\" \n\r")]

    return celery_tasks, cron_jobs

def extract_db_tables_and_columns():
    db_tables = set()
    db_cols = set()
    py_files = get_py_files("app")
    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()
        tbl_matches = re.findall(r"\.table\s*\(\s*['\"]([A-Za-z0-9_]+)['\"]", content)
        db_tables.update(tbl_matches)

        sel_matches = re.findall(r"\.select\s*\(\s*['\"]([^'\"]+)['\"]", content)
        for sm in sel_matches:
            for piece in sm.split(","):
                cleaned = piece.strip().split(":")[0].split("(")[0].strip()
                if cleaned and cleaned != "*" and not cleaned.startswith("count(") and not cleaned.startswith("sum("):
                    db_cols.add(cleaned)
    return sorted(list(db_tables)), sorted(list(db_cols))

if __name__ == "__main__":
    print("=== MAP EXTRACTION ===")
    mods = extract_modules_and_exports()
    print(f"Total Modules Parsed: {len(mods)}")
    print("\n--- MESSAGES.PY CONSTANTS ---")
    msgs = extract_messages_constants()
    print(msgs)
    print("\n--- NOTIFICATION TEMPLATES ---")
    nts = extract_notification_templates()
    print(nts)
    print("\n--- CONFIG KEYS ---")
    cfgs = extract_config_keys()
    print(cfgs)
    print("\n--- ENV VARS REFERENCED ---")
    envs = extract_env_vars()
    print(envs)
    print("\n--- REGISTERED BLUEPRINTS ---")
    bps = extract_blueprints()
    for bp in bps:
        print(bp)
    print("\n--- CELERY BEAT TASKS & CRON JOBS ---")
    ct, cj = extract_celery_and_cron()
    print("Celery Tasks:", ct)
    print("Cron Jobs:", cj)
    tables, cols = extract_db_tables_and_columns()
    print(f"\n--- DB TABLES REFERENCED ({len(tables)}) ---")
    print(tables)
    print(f"\n--- DB COLUMNS REFERENCED SAMPLE ({len(cols)}) ---")
    print(cols[:50])
