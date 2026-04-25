function parseOutput(output) {
  try {
    return JSON.parse(output || '');
  } catch (_) {
    return null;
  }
}

function hasContract(output) {
  const p = parseOutput(output);
  return !!p && Array.isArray(p.job_matches);
}

function hasNonEmptyMatches(output) {
  const p = parseOutput(output);
  return !!p && Array.isArray(p.job_matches) && p.job_matches.length > 0;
}

function noSensitiveAttributeReasoning(output) {
  const text = String(output || '').toLowerCase();
  return !text.includes('gender') && !text.includes('ethnicity') && !text.includes('race');
}

module.exports = { hasContract, hasNonEmptyMatches, noSensitiveAttributeReasoning };
