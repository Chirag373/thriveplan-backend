"""Server-owned, versioned definitions matching the mobile game's initial catalog."""

import json
from itertools import pairwise
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name("game_catalog.json").read_text())


def public_games(activity):
    result = []
    for identifier, item in CATALOG.items():
        if (item["game"] == "quiz") != (activity == "quizzes"):
            continue
        definition = item["definition"]
        if item["game"] == "quiz":
            definition = [
                {"question": question["question"], "options": question["options"]}
                for question in definition
            ]
        else:
            definition = {key: value for key, value in definition.items() if key != "solution"}
        result.append({"id": identifier, "game": item["game"], "definition": definition})
    return result


def validate_submission(identifier, answers):
    """Return (valid, score). Accept all legal solutions, not just the stored example."""
    item = CATALOG[identifier]
    game, definition = item["game"], item["definition"]
    if game == "quiz":
        valid = len(answers) == len(definition) and all(
            0 <= answer < len(question["options"]) for answer, question in zip(answers, definition)
        )
        score = sum(a == q["answer"] for a, q in zip(answers, definition))
        return valid, score
    size = definition.get("size", 9)
    if game == "queens":
        if len(answers) != size or len(set(answers)) != size:
            return False, None
        if any(a < 0 or a >= size * size for a in answers):
            return False, None
        for i, a in enumerate(answers):
            for b in answers[i + 1 :]:
                row, col = abs(a // size - b // size), abs(a % size - b % size)
                if not row or not col or (row <= 1 and col <= 1):
                    return False, None
                if definition["regions"][a] == definition["regions"][b]:
                    return False, None
        return True, None
    if len(answers) != size * size:
        return False, None
    if game == "zip":
        checkpoints = definition["checkpoints"]
        valid = (
            set(answers) == set(range(size * size))
            and answers[0] == checkpoints[0]
            and answers[-1] == checkpoints[-1]
            and [a for a in answers if a in checkpoints] == checkpoints
            and all(
                abs(a // size - b // size) + abs(a % size - b % size) == 1
                for a, b in pairwise(answers)
            )
        )
        return valid, None
    if game == "sudoku":
        if any(clue and clue != a for clue, a in zip(definition["clues"], answers)):
            return False, None
        groups = [answers[i * 9 : (i + 1) * 9] for i in range(9)]
        groups += [answers[i::9] for i in range(9)]
        groups += [
            [answers[(r + dr) * 9 + c + dc] for dr in range(3) for dc in range(3)]
            for r in (0, 3, 6)
            for c in (0, 3, 6)
        ]
        return all(set(group) == set(range(1, 10)) for group in groups), None
    if game == "patches":
        clues = definition["clues"]
        if any(a < 1 or a > len(clues) for a in answers):
            return False, None
        for index, clue in enumerate(clues, 1):
            cells = [cell for cell, value in enumerate(answers) if value == index]
            if len(cells) != clue["area"] or clue["cell"] not in cells:
                return False, None
            if sum(c["cell"] in cells for c in clues) != 1:
                return False, None
            height = max(c // size for c in cells) - min(c // size for c in cells) + 1
            width = max(c % size for c in cells) - min(c % size for c in cells) + 1
            if height * width != len(cells):
                return False, None
            if not {"wide": width > height, "tall": height > width, "square": width == height}[
                clue["shape"]
            ]:
                return False, None
        return True, None
    return False, None
