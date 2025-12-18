# Create Your Constitution

A **constitution** (also called a spec) is a simple text file that tells CVA what rules your code must follow.

## Quick Start

Create a file called `spec.txt` in your project root:

```txt
# My Project Rules

## Code Quality
- All functions must have docstrings
- No unused imports

## Security  
- No hardcoded API keys or secrets
- Validate all user input

## Style
- Use meaningful variable names
- Keep functions under 50 lines
```

## Tips

- **Be specific**: "No hardcoded secrets" is better than "be secure"
- **Be measurable**: Rules should be verifiable by AI
- **Use categories**: Group related rules under headings

Click the button below to create a starter `spec.txt`:
