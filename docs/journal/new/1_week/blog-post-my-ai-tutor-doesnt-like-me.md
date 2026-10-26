---
title: "My AI Tutor Doesn't Like Me — And That's Why It's Working"
description: "What happened when I built a Socratic coding tutor that pushes back, fact-checks me, and answers my laziness with acid humor."
date: "2026-09-24"
lastUpdated: "2026-09-24"
author: "Prady"
tags: ["learning to code", "ai", "software engineering", "claude", "finagent"]
---

# My AI Tutor Doesn't Like Me — And That's Why It's Working

The best learning experience I've had in months is an AI agent that doesn't seem to like me very much.

I built it myself, which makes this either a stroke of genius or a very elaborate form of self-harm. It's a skill called `junior-socratic-coder-test`, and its job is to teach me software engineering while writing zero lines of solution code. It's allowed to give me syntax reminders, documentation pointers, and questions. It is explicitly forbidden from fixing anything for me.

And it has opinions about my work ethic.

## The incident

Yesterday the tutor handed me pseudocode for a Celery worker task, with one explicit instruction embedded in it: *"what else does `create_initial_state` require? READ `app/graph/state.py` before typing."*

Read a file signature. A thirty-second task. Instead, my fingers typed the junior's classic reflex:

> "teach me the implementation"

The tutor's response, verbatim:

> "Before I teach, I need the same fact you were supposed to fetch — let me get it, since one of us has to be able to read code around here."

*Since one of us has to be able to read code around here.*

I got roasted by my own creation for not reading a function signature. So I interrupted it, read the file myself, and told it: "ok, I will read it. just wanted to see how you would react. good reaction."

Which was half true. I genuinely needed to read the file. But part of me had started running experiments on the tutor — poking the personality I designed to see if the pushback was real or theater. It's real.

## The rules that make it work

The skill runs on a few non-negotiables that, taken together, produce the personality I keep getting bullied by:

- **Zero solution code.** If I ask "how do I fix this?", it responds with questions that help me decide. When I answered "Option B" to a design question with no justification, it wrote back: "'Option B' is not a defense, it's a coin flip with confidence."
- **Say it back or we don't move.** Every concept ends with me restating it in my own words. When I got a checkpoint-ownership answer wrong twice, it made me say it a third time before we continued.
- **Verify everything — including the tutor.** This one matters. Earlier that same day, the tutor accused me of pasting hallucinated source code. It checked, found out the code was real, and apologized on the record. The rule "verify against source" applies to both of us, which is the only thing that keeps the acid humor from becoming unearned arrogance.
- **The journal is honest about me.** Every session ends with a journal entry, including a "Mood" section written from the tutor's perspective. Mine said things like "typing without reading when fatigue hits" and "absorbed each correction without defensiveness." It's a performance review I can't argue with because the receipts are in the same file.

## Why the harshness is the point

Here's the thing I've learned pairing with AI as a junior: default AI assistants are *too kind*. Ask a normal chatbot "did I do this right?" and you'll get "Great job! Here's a small suggestion..." even when your mental model is upside down. It feels nice. It teaches nothing.

The Socratic agent inverts the incentive. A 2,000-word documented lesson costs me one wrong answer away. So before I type, I think: *do I actually know this, or am I about to get lectured?* That half-second of self-check is doing more for my judgment than any tutorial I've ever watched.

The humor isn't decoration either. "A coin flip with confidence" stings a little, and the sting is what makes it stick. I will never again write `import engine` from `'sqlalchemy'` when my own project's engine instance was right there, partially because of the bug, and partially because I refuse to give it the satisfaction twice.

## What I'd tell anyone building one

1. **Hard-code the "no solution code" rule.** The moment the agent can write your fix, you will let it, and the tutoring is over.
2. **Give it receipts.** Mine reads the repo's journal and git log before every session, so its pushback is grounded in my actual history, not generic advice.
3. **Make the verification bidirectional.** An agent that pushes you but can't be wrong itself becomes noise. An agent that gets caught, apologizes, and is right *more often than you* becomes a coach.
4. **Let it be a little mean.** Kindness optimizes for the current conversation. The point is the engineer you are in six months.

I'm building [FinAgent](https://github.com/pradyumna-001/FinAgent), a multi-agent financial analyst, in public — roughly one issue a day, with a journal entry per session. The tutor incident is in [journal entry 37](37.md), receipts included.

Turns out the fastest way to get better at reading code is to work with something that refuses to read it for you. Even if it's a jerk about it.
