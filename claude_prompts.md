# Prompt Template

<rewrite_this>

### The Prompt

````prompt
I concur to your suggestions.

You are a senior software architect and technical writer.

Before we proceed to the implementation, draft a concise yet complete implementation plan for the proposed changes in **CLAUDE.md**.

Operational Constraints
1. Execution will be delegated to **Sonnet**; the plan must be fully self-contained so Sonnet can resume work even after a lost connection.
2. Embed a lightweight task tracker (Markdown table with columns *Task ▸ Owner ▸ Status*) at the very top of the document.
3. Include all context required for Sonnet, but keep prose tight—no unnecessary verbiage.
4. When presenting code, restrict yourself to public interfaces only and provide a one-sentence responsibility statement for every unit.
5. Delete any obsolete or already-implemented content in **CLAUDE.md** to reduce context-token load.
6. Ignore backward-compatibility concerns. Remove dead or dangling code to prevent future runtime errors and failing tests.

Required Output Structure
```markdown
## Task Tracker
| Task | Owner | Status |
|------|-------|--------|
| Fill in tasks here |   |   |

## Implementation Plan
### 1. High-Level Overview
*A short paragraph (≤5 sentences) describing the overall goal.*

### 2. Detailed Steps
- [ ] Step 1 – …
- [ ] Step 2 – …
*(Use check-boxes so Sonnet can mark progress.)*

### 3. Code Stubs / Public Interfaces
```language
# show only outward-facing APIs, explain the purpose and responsibilities of each unit clearly
````

### 4. Cleanup Actions

_A bullet list of files/sections to delete._

### 5. Acceptance Criteria

_A numbered list of conditions that prove the refactor is complete._

```

Quality Bar
• The plan must be executable without additional clarification.
• All tables, lists and code blocks must render correctly in Markdown.
• No reference to private thoughts or reasoning—output only the final answer.

On completion, hand control back to me.
```

### Implementation Notes

- **Role-Setting & Perspective**: Declares the assistant as a senior software architect to anchor expertise.
- **Explicit Constraints**: Lists six clear rules so the model knows exactly what to honor (few-shot constraint setting).
- **Output Format Specification**: Gives a concrete Markdown scaffold, reducing ambiguity and post-processing effort.
- **Lightweight Task Tracker**: Ensures resilience against connection loss and progress visibility.
- **Backward-Compatibility Waiver**: Explicitly instructs removal of dead code to avoid future runtime/test failures.
- **Self-contained & Token-Efficient**: Encourages brevity and removal of obsolete sections to stay within context limits.

Expected Outcomes

- Sonnet receives a ready-to-execute, well-structured plan.
- Fewer follow-up clarifications required, accelerating implementation.
- Eliminates historical errors caused by dangling code and unclear ownership.

````

```prompt
Please go ahead and implement the refactoring suggestions based on the plan.
Use @agent-python-pro. Think deep.
````
