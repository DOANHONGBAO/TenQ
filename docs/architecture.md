# Architecture

> Status: **Draft placeholder.** To be completed after `product-spec.md` is agreed.

## Intended topology

```
Browser ──HTTPS──> Vercel (React + Vite static app)
   │
   └──HTTPS──> Nginx (Oracle Cloud VM)
                 └──> FastAPI container ──> Ollama Cloud API
                          ├──> Redis   (game state, judgement cache; internal network only)
                          └──> SQLite  (durable records, e.g. leaderboard history; volume)
```

Sections to write: components, request flow for a question, data model, identity/session, failure modes, environments.
