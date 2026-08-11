# AI and privacy

## Compatible APIs

The template uses OpenAI-compatible Chat Completions. Collect provider, full Base URL, current model ID, and a short-lived test key.

Known examples:

- Step Plan Base URL: `https://api.stepfun.com/step_plan/v1`
- Step Plan Chat Completions: `https://api.stepfun.com/step_plan/v1/chat/completions`
- Step vision-capable example: `step-3.7-flash`
- DeepSeek Base URL: `https://api.deepseek.com`

Treat model availability as changeable. Verify provider documentation or a connection test instead of assuming an old model ID still exists.

## Secret rules

- Never write a real key into code, `.env.example`, tests, screenshots, documentation, shell history, commits, or Skill resources.
- Never repeat a full key in commentary or final output.
- Configure the key through the running app's settings UI, which stores it with Windows DPAPI for the current user.
- Use obvious fake values such as `temporary-test-key` in automated tests.
- Before commit or packaging, scan staged text for the known key prefix and common credential patterns.
- If a key was posted in a public place or committed, tell the user to revoke it immediately; deleting it from the newest commit is not sufficient.

## Screen and keyboard privacy

- Require explicit opt-in for periodic screen observation and allow 5–240 minute intervals.
- Hide pet, tether, and bubbles before capture; keep the compressed screenshot in memory only.
- Never capture, reconstruct, store, or transmit typed content. Keyboard hooks may emit only a key label/category needed for local animation and short timing statistics.
- Keep text AI and vision AI independently switchable.
