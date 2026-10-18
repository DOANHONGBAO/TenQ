# Frontend

React 19 + TypeScript (strict) + Vite, plain CSS with design tokens (light and dark), no UI framework and no state library. Tests: Vitest + Testing Library (jsdom).

## Component tree

```
main.tsx
└─ App                       injects the API client and the Turnstile token provider
   └─ GameProvider           state (useReducer) + every effect that talks to FastAPI
      └─ GameScreen
         ├─ skip link
         ├─ GameHeader       Logo, Daily Challenge #N + UTC date, reset countdown (role=timer)
         ├─ main#play
         │  ├─ StatusBanner      notices (info / warning / error), dismissible
         │  ├─ loading card      while booting
         │  ├─ maintenance card  API unreachable or 502/503, auto-retry every 15 s
         │  ├─ play column
         │  │  ├─ AttemptsMeter  10 indicators coloured by answer, "N of 10 questions left"
         │  │  ├─ QuestionForm   input (150 chars), Ask button, "Judging…" state, one-line rule tip
         │  │  ├─ Feedback       last answer in an aria-live region
         │  │  ├─ GuessForm      direct guess of the word (costs one try, exact match on server)
         │  │  ├─ ResultPanel    win / lose screen, focus moves to it, spoiler-free share, add/change name
         │  │  ├─ HintsPanel     hints unlocked by the server (1 per 2 tries), next-hint counter
         │  │  └─ HistoryList    newest first, answer badges
         │  └─ side column
         │     ├─ LeaderboardPanel  top 10, caller rank, refreshes every minute
         │     └─ YesterdayAnswer   reveals the previous day's word on demand (server allows it)
         ├─ PrivacyNotice    Turnstile invisible-mode disclosure, link to /privacy.html
         └─ WinCelebration   modal after a win made in this visit: treasure chest + canvas confetti,
                             then the leaderboard name form (POST /players/me/name)
```

## Source layout

| Folder | Contents |
|--------|----------|
| `src/api/` | `types.ts` (API contract types + runtime guards), `client.ts` (the only `fetch`, timeouts, error envelope → `ApiError`) |
| `src/state/` | `gameReducer.ts` (pure transitions), `GameProvider.tsx` (effects), `GameContext.ts` (`useGame`), `useResetCountdown.ts`, `useLeaderboard.ts`, `errorMessages.ts` |
| `src/features/game/`, `src/features/leaderboard/` | presentational components |
| `src/features/session/` | `startSession` (Turnstile token → `POST /session`, one at a time) |
| `src/lib/` | `env.ts`, `turnstile.ts` (script loader, invisible widget, reset after use), `format.ts`, `share.ts`, `storage.ts` |
| `src/test/` | `setup.ts`, `fakeApi.ts` (in-memory backend implementing the `Api` interface) |

## State flow

1. **Boot**: `GameProvider` calls `GET /game/today`. On `401 SESSION_REQUIRED` it gets a Turnstile token, calls `POST /session`, and retries once. Network errors or 502/503 show the maintenance card and retry every 15 s.
2. **Ask**: `ask(question)` refuses while a question is in flight (synchronous ref guard) or when the game is finished. It reuses the `Idempotency-Key` stored in `sessionStorage` for the same unfinished question (so a retry after a reload can never be charged twice), otherwise creates one with `crypto.randomUUID()`. On success the reducer stores the server's `GameState`.
3. **Errors**: every failure is mapped to a polite message (`errorMessages.ts`), then the game is **re-read from the server**, so the attempt counter always shows the server's number (never a local guess). AI and network failures keep the pending key for a safe retry.
4. **Time**: `clockOffsetMs = server_time - local time` is stored with each response. The countdown shows `next_reset_at - (now + offset)`; at zero it only asks the server for the new state (polling at most every 5 s). The server decides when a new day starts.
5. **Freshness**: the game reloads when the tab becomes visible again; the leaderboard reloads every minute, on a new day, and when the status changes.

## Security notes

- No game rules run in the browser: attempts, status, timing, and WIN all come from FastAPI.
- The secret word is never sent to the client during the day; the only place a word appears is `YesterdayAnswer`, which calls `GET /puzzles/{yesterday}/answer` (the server refuses today and future dates).
- Share text contains only coloured squares, the challenge number, the count, and the time.
- Only `VITE_*` variables reach the bundle: the API base path and the public Turnstile site key.

## Accessibility

Skip link; labelled regions and form; `aria-live` feedback; `role=status`/`alert` banners; focus returns to the input after each answer and moves to the result heading when the game ends; visible focus outline; colour is never the only signal (badges have text, dots have titles and the count is written); `prefers-reduced-motion` disables animations; light and dark themes from `prefers-color-scheme`.

## Visual design (2026-10-18)

Playful flat 2.0: one bright theme, rounded "bubble" cards and pills, real squircles via `corner-shape: squircle` where supported (larger radii as a fallback elsewhere), clay depth from layered outer and inset shadows, chunky buttons with a ledge that squishes on press. Motion: staggered pop-in for cards, jelly feedback, popping attempt dots, floating background bubbles, chest wobble then open with coins and rotating rays, and a 3 s canvas confetti burst (no library). All animation is disabled under `prefers-reduced-motion`; the chest then opens at once and no confetti is drawn. Fonts are the system rounded stack, so no font is downloaded from a third party.
