---
description: How to share this project with a "Run in Codespaces" link
---

To share this project so others can run it with one click:

1.  **Ensure your code is pushed to GitHub.**
    ```bash
    git push origin main
    ```

2.  **Share the Codespaces Link:**
    Copy and send this link to your professor or teammates:
    `https://codespaces.new/ZiyaoZzz/cogs187a_A3b_autograder`

3.  **Instructions for them:**
    - Click the link.
    - Wait for the environment to build (takes ~1-2 mins).
    - Once the terminal is ready, run:
      ```bash
      npm start
      ```
    - The app will start and open in a preview window.

**Note:** They may need to provide their own `GEMINI_API_KEY` in the `.env` file if yours is not included (which is good practice!).
