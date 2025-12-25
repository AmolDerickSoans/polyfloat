# PolyCLI: Product Guidelines

## Visual Identity & Tone
- **"Bloomberg for Prediction Markets":** The interface should prioritize high information density and professional-grade performance.
- **Color Palette:** 
    - **Neutral:** Dark background (terminal standard) with high-contrast white/gray text.
    - **Actionable:** Traditional financial color-coding (Green for Bids/Gains, Red for Asks/Losses).
    - **Highlight:** Distinctive accent color (e.g., Bloomberg Orange or Cyber Blue) for active focus and command bar input.
- **Tone:** Direct, technical, and objective. Avoid fluff; prioritize clarity and speed.

## User Experience & Interface
- **Command-Driven Navigation:** A persistent command bar is the primary entry point for navigation and trade execution.
- **Multi-Pane Layout:** Use a grid system (powered by Textual) to display simultaneous views of orderbooks, tickertapes, and agent status.
- **Keyboard-First Design:**
    - Single-key hotkeys for common trading actions (Buy, Sell, Cancel).
    - Tab/Number navigation for switching between market views.
    - Focus management: Ensure the command bar is always one keystroke away.
- **Error Handling:** Errors must be highly visible and actionable, providing specific error codes and suggested resolutions.

## Agent Transparency & Communication
- **Succinct Action Logs:** Agent logs should be structured and quantitative.
    - *Format:* `[TIMESTAMP] [ACTION] [MARKET]: [DETAILS] [TRIGGER/SIGNAL]`
    - *Example:* `14:02:10 EXECUTE BUY POLY:TRUMP-WINS 100@0.45 [SIGNAL: SENTIMENT>0.8]`
- **Status Dashboard:** A dedicated pane to monitor agent health, current exposure, and "Safety Rail" status (e.g., % of daily risk limit used).
