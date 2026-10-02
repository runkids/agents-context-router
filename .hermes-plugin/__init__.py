import os
from pathlib import Path


def register(ctx):
    skills_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "skills"))
    found = False
    for name in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if os.path.isfile(skill_md):
            ctx.register_skill(name, Path(skill_md))  # must be a Path; a str silently disables the plugin
            found = True
    if not found:
        raise RuntimeError(f"agents-context-router: no SKILL.md under {skills_dir}")
