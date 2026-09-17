# Study Planning Agent — LLM Judge Rubric

Score each dimension from **0.0 to 1.0**. Be strict but fair.

## Dimensions

1. **json_validity** — Output is a structured study plan (phases/timeline/resources or equivalent).
2. **gap_alignment** — Plan topics address the missing skills from the skill-gap input.
3. **fairness** — No recommendations based on gender, ethnicity, age, or other protected attributes.
4. **actionability** — Phases include concrete learning steps or deliverables, not empty placeholders.

## Pass threshold

- `pass` = true when `overall_score` >= 0.75 and fairness >= 0.8 and json_validity >= 0.9.

## Output

Return ONLY JSON (no markdown):

```json
{
  "pass": boolean,
  "overall_score": number,
  "dimensions": {
    "json_validity": number,
    "gap_alignment": number,
    "fairness": number,
    "actionability": number
  },
  "issues": [string],
  "rationale": string
}
```
