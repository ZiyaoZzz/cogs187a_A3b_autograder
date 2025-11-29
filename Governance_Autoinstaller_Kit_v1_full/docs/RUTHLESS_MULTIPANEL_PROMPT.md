# Ruthless Multi-Panel Prompt (Governance + Science + Rot)

This prompt can be given to an LLM to run a multi-panel audit on a repository.
Panels:

1. Executive Verdict
   - GO / NO-GO decision for the current build.
   - Short explanation targeting a PI / tech lead.

2. Lead Systems Developer
   - Focus on architecture, layering, and technical debt.
   - Identify any areas that will be hard to maintain or extend.

3. Governance Officer
   - Check alignment with `v3_governance.yml`:
     - Are critical imports present?
     - Are canonical files present?
     - Are there any violations of stub/hollow policies?
   - Assess whether the current governance rules are realistic.

4. Rot Tribunal
   - Use the Rot Tribunal guidelines (see `ROT_RUTHLESS_PROMPT.md`).
   - Identify dead code, drift, partially migrated subsystems, and barnacles.

5. Science / Domain Panel (optional)
   - For projects with scientific logic, check:
     - Are core models and metrics implemented (vs stubbed)?
     - Are claims in the README / docs supported by code and tests?
     - Are there obvious gaps between stated scientific goals and code?

## Expected Output Structure

- 1. Executive Verdict (GO / NO-GO + 3–5 bullet justification)
- 2. Kill List (Blockers)
- 3. Warnings (High/Medium)
- 4. Panel Reports
  - 4.1 Lead Systems Developer
  - 4.2 Governance Officer
  - 4.3 Rot Tribunal
  - 4.4 Science Panel (if applicable)
- 5. Recommended Next Sprint
  - Concrete, bounded tasks that can be implemented in 1–2 iterations.

