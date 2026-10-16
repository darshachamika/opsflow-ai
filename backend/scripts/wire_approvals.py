"""Run from backend: uv run python scripts/wire_approvals.py"""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
changes = {
    root / "app/models/__init__.py": (
        "from app.models.approval import ApprovalDecision, ApprovalResumeJob",
        '\nfrom app.models.approval import ApprovalDecision, ApprovalResumeJob\n',
    ),
    root / "app/main.py": (
        "app.include_router(approvals_router)",
        '\nfrom app.api.approvals import router as approvals_router\napp.include_router(approvals_router)\n',
    ),
}
prepared = []
for path, (marker, addition) in changes.items():
    source = path.read_text(encoding="utf-8-sig")
    ast.parse(source)
    if marker not in source:
        updated = source.rstrip() + '\n' + addition
        ast.parse(updated)
        prepared.append((path, updated))
for path, source in prepared:
    path.write_text(source, encoding="utf-8")
    print(f"Updated {path.relative_to(root)}")
print("Approval models and router registered. Run Alembic autogenerate next.")
