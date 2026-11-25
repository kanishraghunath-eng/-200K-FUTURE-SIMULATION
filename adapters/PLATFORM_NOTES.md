# Platform-neutral installation notes

This package is intentionally not tied to a coding agent or one vendor.

- **ChatGPT:** use the platform's supported custom-instruction/skill or file-upload workflow. Keep `SKILL.md` as the instruction source; use the Python engine only in an environment that can run the included package.
- **Claude:** add `SKILL.md` through the account/workspace feature that supports reusable skills or project instructions. Python execution availability depends on the selected Claude product and tools.
- **Gemini:** use the available Gems/custom-instruction or file-context workflow. The Python engine requires a separate Python runtime; instructions alone do not execute code.
- **Other assistants:** import the Markdown instructions into the product's reusable prompt/skill feature. If code execution is unavailable, the assistant must not claim that 200,000 paths were actually computed.

Feature names, upload formats, and availability can change by product and plan. Verify current platform documentation before installation. This folder does not contain platform API keys or external service integrations.
