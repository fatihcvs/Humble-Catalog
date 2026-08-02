"""Enumerate every site where a function-local binding shadows a module
imported at the top of the same file.

This lists the IDIOM, not the fix: it walks every function in the package
and reports any name it binds that is also a module-level import in that
file. A grep for the corrected names would only ever match sites already
repaired and would be blind to the unrepaired ones, which is the
enumeration mistake recorded in the Settled classes line for C1.

Binding forms counted: assignment, augmented assignment, annotated
assignment, for-target, with-target, except-as, walrus, comprehension
target, import-as inside the function, and parameter names. A parameter
is a binding too, but it shadows only deliberately and is reported
separately so the count of real hazards stays honest.

Exit 0 when no non-parameter site remains, 1 otherwise.
"""
import ast
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[3] / "humble_catalog"


def imported_modules(tree):
    """Names bound by module-level imports that refer to a module.

    `from x import y` binds y, which may be a module or a function; both
    are reported, because shadowing either one is the same hazard.
    """
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
    return names


def bound_names(fn):
    """Every name the function body binds, as (name, lineno, is_param)."""
    out = []
    args = fn.args
    for group in (args.posonlyargs, args.args, args.kwonlyargs):
        for arg in group:
            out.append((arg.arg, arg.lineno, True))
    for arg in (args.vararg, args.kwarg):
        if arg is not None:
            out.append((arg.arg, arg.lineno, True))

    def targets(node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out.append((node.id, node.lineno, False))
        for child in ast.iter_child_nodes(node):
            # A nested def or lambda opens its own scope; its bindings are
            # that function's business and it is visited in its own right.
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                continue
            targets(child)

    for stmt in fn.body:
        targets(stmt)
    for node in ast.walk(fn):
        if isinstance(node, ast.ExceptHandler) and node.name:
            out.append((node.name, node.lineno, False))
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and node is not fn:
            for alias in node.names:
                if alias.name != "*":
                    out.append((alias.asname or alias.name.split(".")[0],
                                node.lineno, False))
    return out


def main():
    hazards, params = [], []
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = imported_modules(tree)
        if not imports:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for name, lineno, is_param in bound_names(node):
                if name not in imports:
                    continue
                site = (f"{path.relative_to(PKG.parent)}:{lineno} "
                        f"{node.name} binds {name}")
                (params if is_param else hazards).append(site)

    for site in params:
        print(f"param   {site}")
    for site in hazards:
        print(f"HAZARD  {site}")
    print(f"\n{len(hazards)} shadowing binding(s), "
          f"{len(params)} parameter(s) sharing an imported name")
    return 1 if hazards else 0


if __name__ == "__main__":
    sys.exit(main())
