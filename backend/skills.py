"""Static Skills: one Markdown file per kind of request, composed into the agent's instructions.

A fixed registry, as the plan asks (no dynamic skill search): skills/<name>.md starts with a short
header giving its title, when it applies and the tools it may use, followed by its rules. The
single agent receives the shared grounding policy plus every skill, each with its scope and
tools, and follows the one that matches. PROMPT_VERSION identifies the exact text for evaluation
records.
"""

import hashlib
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().with_name("skills")
REGISTRY = ("base_grounding_policy", "morning_briefing", "general_qa", "order_status", "feasibility",
            "standing_watch", "action_proposal", "unsupported_request")


def parse(name):
    """Read one skill file: a '---' header of 'key: value' lines, then the rules."""
    text = (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{name}.md must start with a '---' header.")
    header, body = text[4:].split("\n---\n", 1)
    fields = {}
    for line in header.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    if not {"title", "when", "tools"} <= set(fields):
        raise ValueError(f"{name}.md needs title, when and tools.")
    tools = [] if fields["tools"] == "none" else [tool.strip() for tool in fields["tools"].split(",")]
    return {"name": name, "title": fields["title"], "when": fields["when"], "tools": tools, "rules": body.strip()}


def load_skills():
    return [parse(name) for name in REGISTRY]


def compose(skills):
    base, rest = skills[0], skills[1:]
    parts = [base["rules"], "",
             "Skills: follow the one that matches the request; a request may need more than one."]
    for skill in rest:
        parts += ["", f"## {skill['title']}",
                  f"When: {skill['when']}",
                  f"Tools: {', '.join(skill['tools']) if skill['tools'] else 'no tool needed'}",
                  skill["rules"]]
    return "\n".join(parts) + "\n"


SKILLS = load_skills()
SYSTEM_PROMPT = compose(SKILLS)
PROMPT_VERSION = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
