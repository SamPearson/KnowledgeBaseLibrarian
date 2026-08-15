---
name: todo
description: A persistent to-do list stored in a JSON file inside this folder. Use it to create, list, complete, and remove tasks.
---

# todo

A small persistent to-do list. Backed by `todos.json` kept in this same folder,
so items survive restarts.

Use this tool when the user asks to track tasks, make a to-do list, mark
something as done, or see what is still outstanding.

Available functions:

- `todo_list()` — return every task with its id, text, and done state.
- `todo_add(text)` — add a new task; returns the new task id.
- `todo_done(task_id)` — mark a task as done by id.
- `todo_remove(task_id)` — delete a task by id.

Id values are small integers. Prefer `todo_list` first to confirm what exists
before using a task id in `todo_done` or `todo_remove`. When the user rephrases
an existing task, update it by removing the old one and adding the new text.