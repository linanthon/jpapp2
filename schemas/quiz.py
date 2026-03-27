from dataclasses import dataclass, field
from typing import List

@dataclass
class QuizDistractors:
    """Stores distractor choices for JP and EN quiz directions.
    The jp and en lists should have the same length."""
    jp: List[str] = field(default_factory=list)
    en: List[str] = field(default_factory=list)
