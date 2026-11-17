# chatstats plugin

See how much you use each AI: chats, messages, rough token counts, busiest months and common topics.

## What you can ask

- "How much do I use ChatGPT compared to Claude?" (attach your exports)
- "Which months did I chat the most?"
- "What would these chats cost through the API?" (give each AI's price per million tokens)

## What it can't do

Token counts are estimates (about 4 characters per token) and only text is counted, so real usage is higher. It works from the export files you give it and cannot log in to your accounts. Prices change, so none are built in: you give them or Claude looks them up.

Project: https://github.com/spencerrios64/chatstats

## Install

In Claude Code:

```
/plugin marketplace add spencerrios64/chatstats
/plugin install chatstats@chatstats
```

In the Claude app, download the `plugin` folder as a zip, rename it to `.plugin` and open it in a chat.
