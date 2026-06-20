# Migration governance

This document defines evidence required before renaming, deprecating, merging, splitting, or retiring this skill.

## Rename
- Record old name, new name, reason, routing compatibility plan, package path impact, registry impact, and references checked.

## Deprecate
- Record deprecation reason, replacement skill or fallback workflow, effective date, removal date, user-facing notice, rollback condition, and eval impact.

## Merge
- Record source skills, target skill, boundary rationale, trigger conflict resolution, follow-through policy conflict resolution, eval migration, and wrapper updates.

## Split
- Record original skill, new target skills, routing boundary, handoff rules, eval redistribution plan, and compatibility aliases.

## Compatibility
- Check package paths, skill names, aliases, catalog entries, README links, registry entries, wrappers, local references, and benchmark workspaces.

## Migration Evidence
- Keep migration_type, from, to, effective_date, compatibility_policy, references_checked, evals_updated, wrappers_updated, and release_gate_result.
