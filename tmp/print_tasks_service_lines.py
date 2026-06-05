import pathlib

p = pathlib.Path("crmks/backend/services/tasks_service.py")
lines = p.read_text(encoding="utf-8").splitlines()

start = 150
end = 190
for i in range(start, min(end, len(lines))):
    print(f"{i+1}: {lines[i]}")
