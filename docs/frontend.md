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
         │  │  ├─ RulesPanel     <details>, open until the first question
         │  │  ├─ AttemptsMeter  10 indicators coloured by answer, "N of 10 questions left"
         │  │  ├─ QuestionForm   input (150 chars), Ask button, "Judging…" state
         │  │  ├─ Feedback       last answer in an aria-live region
         │  │  ├─ ResultPanel    win / lose screen, focus moves to it, spoiler-free share
         │  │  └─ HistoryList    newest first, answer badges
         │  └─ side column
         │     ├─ LeaderboardPanel  top 10, caller rank, refreshes every minute
         │     └─ YesterdayAnswer   reveals the previous day's word on demand (server allows it)
         └─ PrivacyNotice    Turnstile invisible-mode disclosure, link to /privacy.html
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
