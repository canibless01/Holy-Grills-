import os
import ast
import re

def get_py_files(root_dir="app"):
    py_files = []
    for root, dirs, files in os.walk(root_dir):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files

def audit_query_efficiency():
    py_files = get_py_files("app")
    n_plus_one_findings = []
    unbounded_queries = []

    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            lines = f.readlines()
            content = "".join(lines)

        try:
            tree = ast.parse(content, filename=pf)
            # Find loops
            for node in ast.walk(tree):
                if isinstance(node, (ast.For, ast.While)):
                    # check if db.table or .table is inside loop body
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                            if inner.func.attr == "table":
                                n_plus_one_findings.append((pf, inner.lineno, "Query inside loop (.table call)"))
                                break

                # Check .execute() calls without .limit() or .single() or .count()
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
                    # trace back call chain
                    chain = ast.unparse(node)
                    if ".limit(" not in chain and ".single(" not in chain and "count=" not in chain:
                        # check if it's on a known large table like profiles, hp_transactions, orders, etc.
                        for tbl in ["hp_transactions", "orders", "profiles", "notifications", "order_items", "cart_items", "audit_logs"]:
                            if f"'{tbl}'" in chain or f'"{tbl}"' in chain:
                                unbounded_queries.append((pf, node.lineno, f"Unbounded query on {tbl}: {chain[:60]}..."))
                                break
        except Exception as e:
            pass

    return n_plus_one_findings, unbounded_queries


def audit_production_risks_and_security():
    py_files = get_py_files("app")
    missing_campus_checks = []
    sensitive_data_leaks = []
    routes_missing_auth = []

    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            lines = f.readlines()
            content = "".join(lines)

        if pf.startswith("app/routes/"):
            try:
                tree = ast.parse(content, filename=pf)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # check if decorator is a route e.g. @bp.route(...)
                        is_route = False
                        has_auth = False
                        has_role = False
                        for dec in node.decorator_list:
                            dec_str = ast.unparse(dec)
                            if "route(" in dec_str:
                                is_route = True
                            if "require_auth" in dec_str:
                                has_auth = True
                            if "require_role" in dec_str:
                                has_role = True

                        if is_route and not (has_auth or has_role):
                            # verify if endpoint should be public or missing auth
                            if not any(pub in node.name for pub in ["health", "login", "register", "public", "storefront", "webhook", "docs", "swagger", "openapi"]):
                                routes_missing_auth.append((pf, node.lineno, f"Route `{node.name}` missing @require_auth or @require_role"))

            except Exception:
                pass

        # check sensitive data leaks or non-atomic operations
        for idx, line in enumerate(lines):
            lineno = idx + 1
            if "password_hash" in line and ("return" in line or "jsonify" in line or "response" in line):
                sensitive_data_leaks.append((pf, lineno, line.strip()))
            if "raw_token" in line or "secret_key" in line:
                if "jsonify" in line or "return" in line:
                    sensitive_data_leaks.append((pf, lineno, line.strip()))

    return missing_campus_checks, sensitive_data_leaks, routes_missing_auth


if __name__ == "__main__":
    print("=== AUDIT EFFICIENCY & PRODUCTION RISKS ===")
    nplus1, unbounded = audit_query_efficiency()
    print(f"\n1. N+1 QUERIES IN LOOPS ({len(nplus1)}):")
    for item in nplus1[:15]:
        print(" ", item)

    print(f"\n2. UNBOUNDED QUERIES ON LARGE TABLES ({len(unbounded)}):")
    for item in unbounded[:15]:
        print(" ", item)

    mc, leak, no_auth = audit_production_risks_and_security()
    print(f"\n3. ROUTES MISSING AUTH/ROLE DECORATOR ({len(no_auth)}):")
    for item in no_auth:
        print(" ", item)

    print(f"\n4. POTENTIAL SENSITIVE DATA LEAKS ({len(leak)}):")
    for item in leak:
        print(" ", item)
