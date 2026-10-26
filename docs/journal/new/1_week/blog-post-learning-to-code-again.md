# How I Learned to Enjoy Coding Again — By Making My AI Stop Writing Code

I'm building FinAgent, a multi-agent AI system that writes morning notes for Brazilian asset managers. Python, FastAPI, LangGraph, PostgreSQL, the works. I'm a junior engineer. And for a while, I was doing what a lot of people do in 2026: letting AI write the code while I watched.

It was fast. It was also hollow. I wasn't learning, and honestly, I wasn't having fun.

This post is about the one change that brought the joy back: I made my AI assistant stop writing code for me.

## The problem with passive AI coding

When AI writes the code, you become a reviewer of work you don't fully understand. You paste, it runs, you move on. If it breaks, you paste the error back. Repeat.

I noticed the symptoms in myself: I couldn't explain my own codebase. When something failed, my first instinct was "ask the AI" instead of "what is the error telling me?" I was shipping, but I wasn't growing. And coding — the thing that made me start a carrer in software engineering — had become boring, because I wasn't actually doing it.

## The experiment: a skill that refuses to write code

I configured my AI assistant with a custom skill (a set of standing instructions) I called *junior-socratic-coder-test*. The contract is simple and absolute:

- The AI **never** writes solution code. Not a function, not a fix, not a "here's the pattern."
- It can give me: syntax reminders, documentation pointers, conceptual explanations, and questions.
- We work **one concept at a time**. I have to explain each concept in my own words before we move on.
- When I ask "how do I fix this?", it answers with questions: *What does the error tell you? What have you tried? Where would you look first?*

It basically turned my AI from a code generator into a senior engineer sitting next to me — one who refuses to touch my keyboard.

## What the struggle actually looked like

I'll be honest: the first days under this system were slower and sometimes frustrating. My journal from those weeks is full of it.

There's an entry where I spent a session fighting the same class of bug **three times** — passing a bare value where the state expected a container, guessing at dictionary keys instead of reading the actual state definition. The rule that finally stuck was embarrassingly simple: *open the file and read, don't guess.*

But the same journal entry records the moment it clicked. I caught myself correcting my own reasoning about error severity — my first criterion ("can it be fixed?") was wrong, and I replaced it with a better one ("what's the blast radius, and is the failure visible?") without the AI telling me. That's the difference between copying a fix and understanding a principle. One evaporates by next week. The other stays.

## What I actually learned

A few things that stuck because I derived them instead of receiving them:

**Failures must be visible, not logged and forgotten.** In FinAgent, when an agent can't parse LLM output, it doesn't swallow the error — it appends a `DataFlag` so downstream consumers and eventually the human reader can see that something is degraded. I arrived at this pattern by defending design choices out loud, not by copying it from a tutorial.

**"It works" is not the same as "I understand it."** My old verification standard was "does it run?" Now it's "can I explain why it failed and how I found it?" The second one is much harder to fake — and that's the point.

**Debugging is a skill with a method.** Look at the error. Form an expectation. Compare expected vs. actual. Check the source, not a Stack Overflow answer about the source. I still do this slowly, but I do it myself.

**Writing things down compounds.** Every closed issue gets a journal entry: what shipped, what decisions were made and why, what I still don't understand, where to resume tomorrow. Those entries are now the most valuable documentation in the project — and the raw material for this post.

## Why it's fun again

The enjoyment came back for a simple reason: I'm thinking again.

Every session has real decisions in it that are mine. Should the factory return `None` and let the caller assign severity, or raise? I decided, defended it, and I remember why. When a migration failed because pgvector's HNSW index caps at 2,000 dimensions on `vector` but not `halfvec`, I found that by *running the migration and reading the error* — the kind of gotcha you only own if you hit it yourself.

Slow felt like a cost at first. It turned out to be the entire point. The AI is still in every session — I'm not romantic about that — but now it's a tutor with hard boundaries, not a ghostwriter. The code in my repo is code I can defend line by line, because I wrote it.

If coding with AI has started to feel hollow to you, try it for a week: forbid the AI from writing solutions, make it ask you questions instead, and write down what you learned at the end of each day. The first days will be slower. The day you catch yourself correcting your own bad reasoning — unassisted — is the day it stops feeling slow.

---

*This post is based on my private project journal (35 entries and counting). FinAgent is open source: [github.com/pradyumna-001/FinAgent](https://github.com/pradyumna-001/FinAgent).*
