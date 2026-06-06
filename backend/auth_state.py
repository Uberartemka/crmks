"""
Единое хранилище in-memory токенов.

Вынесено в отдельный файл чтобы избежать дублирования при
множественном импорте main.py (например __main__ vs main при --reload).
"""
from typing import Dict

# token -> user_id
active_tokens: Dict[str, int] = {}
