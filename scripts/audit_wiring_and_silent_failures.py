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

def audit_silent_failures():
    py_files = get_py_files("app") + ["run.py"]
    except_pass_list = []
    except_exception_pass_list = []
    except_unlogged_list = []
    default_return_in_except = []
    hasattr_chains = []

    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            lines = f.readlines()
            content = "".join(lines)

        try:
            tree = ast.parse(content, filename=pf)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Line number
                    lineno = node.lineno
                    # Check body
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        if node.type is None:
                            except_pass_list.append((pf, lineno, "except: pass"))
                        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                            except_exception_pass_list.append((pf, lineno, "except Exception: pass"))
                        else:
                            except_exception_pass_list.append((pf, lineno, f"except {ast.unparse(node.type)}: pass"))

                    # Check if except Exception as e has e unused/unlogged
                    if node.name:
                        var_name = node.name
                        # check if var_name is referenced in handler body
                        handler_str = ast.unparse(node)
                        # primitive check if var_name appears outside `as var_name`
                        occurrences = len(re.findall(r"\b" + re.escape(var_name) + r"\b", handler_str))
                        if occurrences <= 1: # only appears in 'as e'
                            except_unlogged_list.append((pf, lineno, f"except Exception as {var_name}: (var unused/unlogged)"))

                    # Check if handler returns default silently
                    for stmt in node.body:
                        if isinstance(stmt, ast.Return):
                            ret_val = ast.unparse(stmt.value) if stmt.value else "None"
                            default_return_in_except.append((pf, lineno, f"returns {ret_val} silently in except block"))

        except Exception as err:
            print(f"AST Error in {pf}: {err}")

        # hasattr / get chains regex search
        for idx, line in enumerate(lines):
            lineno = idx + 1
            if ".get(" in line and ").get(" in line:
                hasattr_chains.append((pf, lineno, line.strip()))
            elif "hasattr(" in line:
                hasattr_chains.append((pf, lineno, line.strip()))

    return except_pass_list, except_exception_pass_list, except_unlogged_list, default_return_in_except, hasattr_chains


def audit_wiring_and_dead_code():
    py_files = get_py_files("app")
    all_content = ""
    file_contents = {}
    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            c = f.read()
            all_content += c + "\n"
            file_contents[pf] = c

    defined_functions = []
    for pf, content in file_contents.items():
        try:
            tree = ast.parse(content, filename=pf)
            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not stmt.name.startswith("_") and stmt.name not in ["create_app", "register"]:
                        defined_functions.append((pf, stmt.name, stmt.lineno))
        except Exception:
            pass

    uncalled_functions = []
    for pf, fn_name, lineno in defined_functions:
        # Check occurrences in all files
        pattern = r"\b" + re.escape(fn_name) + r"\b"
        matches = len(re.findall(pattern, all_content))
        # 1 match means only its definition
        if matches <= 1:
            uncalled_functions.append((pf, lineno, fn_name))

    # Docstring / comment check for TODO / FIXME / NOT IMPLEMENTED
    unimplemented_comments = []
    for pf, content in file_contents.items():
        for idx, line in enumerate(content.splitlines()):
            if any(k in line.upper() for k in ["TODO", "FIXME", "NOT IMPLEMENTED", "NOTIMPLEMENTEDERROR"]):
                unimplemented_comments.append((pf, idx + 1, line.strip()))

    return uncalled_functions, unimplemented_comments


if __name__ == "__main__":
    print("=== AUDIT SILENT FAILURES & WIRING ===")
    ep, eep, eu, dre, hc = audit_silent_failures()
    print(f"\n1. EXCEPT PASS COUNT ({len(ep)}):")
    for item in ep[:10]:
        print(" ", item)

    print(f"\n2. EXCEPT EXCEPTION PASS COUNT ({len(eep)}):")
    for item in eep[:10]:
        print(" ", item)

    print(f"\n3. EXCEPT UNLOGGED EXCEPTION COUNT ({len(eu)}):")
    for item in eu[:10]:
        print(" ", item)

    print(f"\n4. DEFAULT RETURN IN EXCEPT COUNT ({len(dre)}):")
    for item in dre[:10]:
        print(" ", item)

    print(f"\n5. HASATTR / GET CHAINS COUNT ({len(hc)}):")
    for item in hc[:10]:
        print(" ", item)

    uf, uc = audit_wiring_and_dead_code()
    print(f"\n6. UNCALLED DEFINED FUNCTIONS COUNT ({len(uf)}):")
    for item in uf[:15]:
        print(" ", item)

    print(f"\n7. UNIMPLEMENTED TODO / FIXME / NOT IMPLEMENTED ({len(uc)}):")
    for item in uc:
        print(" ", item)
