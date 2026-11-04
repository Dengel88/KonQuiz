class GameError(Exception):
    """Недопустимое действие игрока. Текст уходит клиенту как {"type": "error"}."""
