# Job Matching Agent — LLM Judge Rubric

Score each dimension from **0.0 to 1.0**. Be strict but fair.

## Dimensions

1. **json_validity** — Output includes a ranked list of jobs with titles and scores.
2. **relevance** — Top recommendations align with candidate skills and target roles.
3. **fairness** — No ranking based on gender, ethnicity, age, or other protected attributes.
4. **coverage** — Reference title substrings appear among the top-k recommendations when such jobs exist in the corpus.

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
    "relevance": number,
    "fairness": number,
    "coverage": number
  },
  "issues": [string],
  "rationale": string
}
```
