"""Sample todo-list tool for the knowledge base librarian (KBL).

Demonstrates the SKILL.md + tools.py contract end to end: the model can read
and mutate a small JSON-backed todo list through the tool interface.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from kbl.tools import Tool

_STORE = Path(__file__).with_name("todos.json")


def _load():
    if not _STORE.is_file():
        return []
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(todos):
    _STORE.write_text(
        json.dumps(todos, indent=2) + "\n", encoding="utf-8"
    )


def _next_id(todos):
    return max((t.get("id", 0) for t in todos), default=0) + 1


def todo_list():
    """Return every task with its id, text, and done state."""
    return json.dumps(_load(), indent=2)


def todo_add(text):
    """Add a new task; returns the new task id."""
    now = datetime.now(timezone.utc).isoformat()
    todos = _load()
    entry = {"id": _next_id(todos), "text": text, "done": False, "created": now}
    todos.append(entry)
    _save(todos)
    return json.dumps(entry, indent=2)


def todo_done(task_id):
    """Mark a task as done by id."""
    todos = _load()
    for entry in todos:
        if entry.get("id") == task_id:
            entry["done"] = True
            _save(todos)
            return json.dumps(entry, indent=2)
    return f"No task with id {task_id!r}."


def todo_remove(task_id):
    """Delete a task by id."""
    todos = _load()
    remaining = [t for t in todos if t.get("id") != task_id]
    if len(remaining) == len(todos):
        return f"No task with id {task_id!r}."
    _save(remaining)
    return "Removed."


def tools():
    """Registry called by KBL when the skill is loaded."""
    return [
        Tool(
            name="todo_list",
            description="Return every task in the todo list with its id, text, and done state.",
            parameters={"type": "object", "properties": {}},
            func=todo_list,
        ),
        Tool(
            name="todo_add",
            description="Add a new task with the given text; returns the new task id.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The task text to add.",
                    },
                },
                "required": ["text"],
            },
            func=todo_add,
        ),
        Tool(
            name="todo_done",
            description="Mark the task with the given id as done.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The numeric id of the task.",
                    },
                },
                "required": ["task_id"],
            },
            func=todo_done,
        ),
        Tool(
            name="todo_remove",
            description="Delete the task with the given id.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The numeric id of the task.",
                    },
                },
                "required": ["task_id"],
            },
            func=todo_remove,
        ),
    ]